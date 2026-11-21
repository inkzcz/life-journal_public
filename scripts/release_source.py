"""Fail-closed official ZIP content verification (stdlib; credentials never logged).

The downloaded builder is the trust boundary. A pinned historical release lock
permits offline verification; unknown releases require authenticated official API.
ZIP channel/origin cannot be inferred from extracted bytes. Git provenance and
content verification are intentionally separate, including in legacy v5 images.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import urllib.error
import urllib.request
from scripts.source_identity import identify
from scripts.release import SHA, REPOSITORY
from scripts.sync_version import product_version
from scripts.release_source_locks import LOCKS


class Unavailable(ValueError):
    pass


class AuthorityError(ValueError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise AuthorityError('GitHub身份接口出现非预期重定向，已停止；不会转发凭据')


class GitHub:
    def __init__(self):
        token=os.getenv('GH_TOKEN') or os.getenv('GITHUB_TOKEN')
        if not token and shutil.which('gh'):
            try:
                result=subprocess.run(['gh','auth','token','--hostname','github.com'],capture_output=True,text=True,timeout=10)
                if result.returncode==0:token=result.stdout.strip()
            except (OSError,subprocess.SubprocessError):pass
        self._token=token
        self._opener=urllib.request.build_opener(NoRedirect())

    def get(self, path):
        headers={'Accept':'application/vnd.github+json','User-Agent':'Life-Journal-verified-source','X-GitHub-Api-Version':'2022-11-28'}
        if self._token:headers['Authorization']='Bearer '+self._token
        request=urllib.request.Request('https://api.github.com/repos/'+REPOSITORY+'/'+path,headers=headers)
        try:
            with self._opener.open(request,timeout=10) as response:
                data=response.read(16*1024*1024+1)
            if len(data)>16*1024*1024:raise AuthorityError('GitHub身份响应过大，已停止')
            result=json.loads(data)
        except urllib.error.HTTPError as error:
            if error.code in (401,403,404,408,429) or error.code>=500:
                raise Unavailable('GitHub API不可达、限流或私有仓库未授权（HTTP '+str(error.code)+'）') from None
            raise AuthorityError('GitHub身份接口返回异常状态，已停止') from None
        except (urllib.error.URLError,TimeoutError,OSError):
            raise Unavailable('网络不可用或中断，无法在线读取官方Tag') from None
        except (ValueError,UnicodeError):
            raise AuthorityError('GitHub身份响应格式异常，已停止') from None
        if not isinstance(result,dict):raise AuthorityError('GitHub身份响应不是对象，已停止')
        return result


def oid(value):
    if not isinstance(value,str) or not SHA.fullmatch(value):raise AuthorityError('官方Git对象SHA格式异常')
    return value


def blob_hash(data):
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def valid_path(value):
    if not isinstance(value,str) or not value or '\\' in value or ':' in value or '\0' in value:raise AuthorityError('源码路径非法')
    p=PurePosixPath(value)
    if p.is_absolute() or p.as_posix()!=value or any(x in ('.','..','.git') or x.endswith((' ','.')) for x in value.split('/')):raise AuthorityError('源码路径越界或不规范')
    return value


def tree_oid(files):
    """Reconstruct Git's tree objects using official modes, not Windows chmod."""
    root={}
    for path,entry in files.items():
        parts=valid_path(path).split('/');node=root
        for part in parts[:-1]:
            if part in node and not isinstance(node[part],dict):raise AuthorityError('GitTree文件与目录冲突')
            node=node.setdefault(part,{})
        if parts[-1] in node:raise AuthorityError('GitTree重复路径')
        if entry['mode'] not in ('100644','100755'):raise AuthorityError('不支持符号链接或子模块，已停止')
        node[parts[-1]]=(entry['mode'],oid(entry['oid']))
    def digest(node):
        entries=[]
        for name,value in node.items():
            directory=isinstance(value,dict);mode='40000' if directory else value[0];sha=digest(value) if directory else value[1]
            encoded=name.encode('utf-8');entries.append((encoded+(b'/' if directory else b''),mode.encode()+b' '+encoded+b'\0'+bytes.fromhex(sha)))
        content=b''.join(v for _,v in sorted(entries))
        return hashlib.sha1(b'tree '+str(len(content)).encode()+b'\0'+content).hexdigest()
    return digest(root)


def pinned(version):
    lock=LOCKS.get(version)
    if not lock:return None
    data=(Path(__file__).with_name('release_manifests')/(version+'.json')).read_bytes()
    if hashlib.sha256(data).hexdigest()!=lock['manifest_sha256']:raise AuthorityError('内置发布校验锁已损坏，禁止构建')
    result=json.loads(data)
    if (result['version'],result['commit'],result['tag_object'],result['tree'])!=(version,lock['commit'],lock['tag_object'],lock['tree']):raise AuthorityError('内置发布身份不匹配')
    if tree_oid(result['files'])!=lock['tree']:raise AuthorityError('内置GitTree校验失败')
    return result


def online(version, client, lock):
    ref=client.get('git/ref/tags/'+version)
    if ref.get('object',{}).get('type')!='tag':raise AuthorityError('官方版本必须是Annotated Tag，拒绝轻量Tag')
    tag_oid=oid(ref['object'].get('sha'));current=tag_oid
    for depth in range(4):
        tag=client.get('git/tags/'+current)
        if oid(tag.get('sha'))!=current or depth==0 and tag.get('tag')!=version:raise AuthorityError('官方Tag对象与版本不一致')
        target=tag.get('object',{});target_sha=oid(target.get('sha'))
        if target.get('type')=='commit':commit=target_sha;break
        if target.get('type')!='tag':raise AuthorityError('官方Tag未指向Commit')
        current=target_sha
    else:raise AuthorityError('官方Tag嵌套层数异常')
    obj=client.get('git/commits/'+commit)
    if oid(obj.get('sha'))!=commit:raise AuthorityError('官方Commit响应不一致')
    tree=oid(obj.get('tree',{}).get('sha'))
    if lock:
        if (commit,tag_oid,tree)!=(lock['commit'],lock['tag_object'],lock['tree']):raise AuthorityError('官方Tag与已批准固定版本冲突，禁止构建')
        return lock
    response=client.get('git/trees/'+tree+'?recursive=1')
    if oid(response.get('sha'))!=tree or response.get('truncated') is not False:raise AuthorityError('官方GitTree不完整，禁止构建')
    files={};casefold=set()
    entries=response.get('tree')
    if not isinstance(entries,list) or len(entries)>20000:raise AuthorityError('官方GitTree规模或格式异常')
    for entry in entries:
        path=valid_path(entry.get('path'));mode=entry.get('mode')
        if entry.get('type')=='tree' and mode=='040000':continue
        if entry.get('type')!='blob' or mode not in ('100644','100755'):raise AuthorityError('不支持符号链接或子模块')
        if path in files or path.casefold() in casefold:raise AuthorityError('源码路径重复或大小写冲突')
        casefold.add(path.casefold());files[path]={'mode':mode,'oid':oid(entry.get('sha'))}
    if tree_oid(files)!=tree:raise AuthorityError('官方GitTree内容与根SHA不匹配')
    return {'version':version,'commit':commit,'tag_object':tag_oid,'tree':tree,'files':files}


def no_reparse(path):
    path=Path(os.path.abspath(path))
    for part in [path,*path.parents]:
        if part.is_symlink() or part.exists() and getattr(part.lstat(),'st_file_attributes',0)&0x400:raise ValueError('源码不能经过符号链接或Windows重解析点')
    return path


def verify_tree(root, manifest):
    root=no_reparse(root);expected=manifest['files'];actual={};digests={}
    def scan(directory):
        for path in sorted(directory.iterdir()):
            rel=path.relative_to(root).as_posix()
            # Only the tool's top-level output is excluded, never build contexts.
            if directory==root and path.name=='release' and not any(x=='release' or x.startswith('release/') for x in expected):continue
            info=path.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:raise ValueError('源码含符号链接或重解析点：'+rel)
            if stat.S_ISDIR(info.st_mode):scan(path);continue
            if not stat.S_ISREG(info.st_mode) or rel not in expected:raise ValueError('源码包含非官方额外文件：'+rel+'；请重新解压官方ZIP，启动器放在源码文件夹外')
            entry=expected[rel];h=hashlib.sha1(b'blob '+str(info.st_size).encode()+b'\0');sha256=hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda:stream.read(1024*1024),b''):h.update(block);sha256.update(block)
            if h.hexdigest()!=entry['oid'] or entry.get('sha256') and sha256.hexdigest()!=entry['sha256']:raise ValueError('源码校验失败：'+rel+'（内容或换行已改变），未启动构建')
            actual[rel]=entry;digests[rel]=sha256.hexdigest()
    scan(root)
    missing=set(expected)-set(actual)
    if missing:raise ValueError('源码缺少官方文件：'+sorted(missing)[0])
    if tree_oid(actual)!=manifest['tree']:raise ValueError('本地源码GitTree不匹配')
    return hashlib.sha256(json.dumps(digests,sort_keys=True,separators=(',',':')).encode()).hexdigest()


@dataclass
class Proof:
    identity: dict
    recheck: object


def verify_source(root, revision=None, verification='auto', client=None):
    root=no_reparse(root)
    if verification not in ('auto','online','offline'):raise ValueError('源码验证模式非法')
    if (root/'.git').exists():
        source=identify(root,revision)
        tree=subprocess.run(['git','-C',str(root),'rev-parse','HEAD^{tree}'],check=True,capture_output=True,text=True,timeout=60).stdout.strip()
        identity=source|{'source_verified':True,'verification_method':'git-head-clean-worktree','git_tree_oid':oid(tree),'source_origin':'git-checkout'}
        def check():
            if identify(root,revision)!=source:raise ValueError('Source changed during build/export；源码已改变，停止交付')
        return Proof(identity,check)
    version='v'+product_version(root);lock=pinned(version);authority='github-api'
    if verification=='offline':
        if not lock:raise ValueError('该版本没有可信离线校验锁；请联网验证或使用官方更新的启动器，不接受手填SHA作为证明')
        manifest=lock;authority='pinned-release-lock'
    else:
        try:manifest=online(version,client or GitHub(),lock)
        except (KeyError,TypeError,AttributeError,IndexError):raise AuthorityError('GitHub身份响应字段异常，禁止构建') from None
        except Unavailable as error:
            if verification=='online' or not lock:raise ValueError(str(error)+'；可用已批准版本的离线启动器，或配置只读GitHub认证后重试') from None
            print('[源码] 在线身份确认不可用，明确使用内置固定版本离线锁；仍执行完整源码校验。',flush=True)
            manifest=lock;authority='pinned-release-lock'
    if revision and revision!=manifest['commit']:raise ValueError('指定SHA与官方Tag不一致，禁止构建')
    content=verify_tree(root,manifest);legacy=identify(root,manifest['commit'])
    identity=legacy|{'source_verified':True,'verification_method':'official-git-tree-content','verification_authority':authority,'git_tree_oid':manifest['tree'],'official_tag':version,'official_tag_object':manifest['tag_object'],'verified_file_count':len(manifest['files']),'verified_content_sha256':content,'source_origin':'archive-channel-not-inferred','verifier_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    print('[源码] 已逐文件验证 '+str(len(manifest['files']))+' 个文件；官方Commit '+manifest['commit'],flush=True)
    def check():
        if verify_tree(root,manifest)!=content or identify(root,manifest['commit'])!=legacy:raise ValueError('Source changed during build/export；源码已改变，停止交付')
    return Proof(identity,check)
