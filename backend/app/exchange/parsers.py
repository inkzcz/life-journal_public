"""Bounded, non-executing adapters. Never extract archive paths to the filesystem."""
import io,json,stat,unicodedata,zipfile
from pathlib import PurePosixPath
import yaml
from .schemas import Exchange

MAX_TEXT=2*1024*1024
MAX_PACKAGE=50*1024*1024
MAX_TOTAL=100*1024*1024


def pairs(items):
    out={}
    for k,v in items:
        if k in out:raise ValueError('重复JSON字段')
        out[k]=v
    return out


def json_data(data):
    if len(data)>MAX_TEXT:raise ValueError('文本文件超限')
    try:return json.loads(data.decode('utf-8-sig'),object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('非有限JSON数值')))
    except (RecursionError,UnicodeError):raise ValueError('文本编码或嵌套无效') from None


def _yaml_data(text):
    # Deny aliases/anchors before construction, rather than trying to bound an
    # already-expanded graph. Bound depth and event count, too.
    depth=0
    for count,event in enumerate(yaml.parse(text),1):
        if count>10000 or isinstance(event,yaml.AliasEvent) or getattr(event,'anchor',None):raise ValueError('YAML别名、锚点或复杂度超限')
        if isinstance(event,(yaml.MappingStartEvent,yaml.SequenceStartEvent)):depth+=1
        if depth>30:raise ValueError('YAML嵌套超限')
        if isinstance(event,(yaml.MappingEndEvent,yaml.SequenceEndEvent)):depth-=1
    class Loader(yaml.SafeLoader):pass
    def mapping(loader,node):
        rows=loader.construct_pairs(node,deep=True)
        if any(not isinstance(k,str) for k,v in rows):raise ValueError('YAML字段名必须为文本')
        return pairs(rows)
    Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,mapping)
    # Keep YYYY-MM-DD as text so JSON and Markdown have identical semantics.
    Loader.add_constructor('tag:yaml.org,2002:timestamp',lambda loader,node:loader.construct_scalar(node))
    try:return yaml.load(text,Loader=Loader)
    except yaml.YAMLError:raise ValueError('YAML内容无效，不执行标签') from None


def yaml_data(text):
    try:return _yaml_data(text)
    except yaml.YAMLError:raise ValueError('YAML内容无效，不执行标签') from None


def markdown_raw(data):
    if len(data)>MAX_TEXT:raise ValueError('Markdown超限')
    try:text=data.decode('utf-8-sig').replace('\r\n','\n')
    except UnicodeError:raise ValueError('Markdown需UTF-8') from None
    lines=text.splitlines(keepends=True)
    if not lines or lines[0].strip()!='---':raise ValueError('Markdown缺少正式YAML Front Matter')
    end=next((i for i,line in enumerate(lines[1:],1) if line.strip()=='---'),None)
    if end is None:raise ValueError('Front Matter未结束')
    metadata=yaml_data(''.join(lines[1:end]));body=''.join(lines[end+1:])
    if not isinstance(metadata,dict) or set(metadata)-{'format','version','record','media','places','preferences'}:raise ValueError('Front Matter字段无效')
    record=metadata.get('record')
    if not isinstance(record,dict) or 'body' in record:raise ValueError('record无效，正文仅放在Front Matter后')
    return {'format':metadata.get('format'),'version':metadata.get('version'),'records':[record|{'body':body}],'media':metadata.get('media',[]),'places':metadata.get('places',[]),'preferences':metadata.get('preferences',{})}


def safe_path(path):
    if not isinstance(path,str) or not path or len(path)>240 or any(c in path for c in ('\\',':','\x00')) or unicodedata.normalize('NFC',path)!=path:raise ValueError('归档路径无效')
    p=PurePosixPath(path)
    if p.is_absolute() or any(x in ('','.','..') for x in path.split('/')):raise ValueError('归档路径不安全')
    return path


def package(data):
    if len(data)>MAX_PACKAGE:raise ValueError('ZIP压缩大小超限')
    try:z=zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:raise ValueError('ZIP文件无效') from None
    with z:
        entries=z.infolist()
        if len(entries)>250:raise ValueError('ZIP文件数量超限')
        files={};seen=set();total=0
        for e in entries:
            name=safe_path(e.filename[:-1] if e.is_dir() else e.filename);key=name.casefold()
            if key in seen:raise ValueError('ZIP路径重复或大小写冲突')
            seen.add(key)
            mode=e.external_attr>>16
            if stat.S_IFMT(mode) not in (0,stat.S_IFREG,stat.S_IFDIR) or e.flag_bits&1 or (stat.S_IFMT(mode)==stat.S_IFDIR and not e.is_dir()):raise ValueError('ZIP不能包含链接、设备或加密文件')
            if e.is_dir():continue
            total+=e.file_size
            if total>MAX_TOTAL or e.file_size>10*1024*1024 or e.file_size>max(4096,e.compress_size*200):raise ValueError('ZIP解压大小或压缩比超限')
            try:raw=z.read(e)
            except (zipfile.BadZipFile,RuntimeError):raise ValueError('ZIP内容或校验无效') from None
            if len(raw)!=e.file_size:raise ValueError('ZIP大小不符')
            files[name]=raw
        if 'manifest.json' not in files:raise ValueError('ZIP必须包含manifest.json')
        manifest=json_data(files['manifest.json'])
        if not isinstance(manifest,dict) or set(manifest)!={'format','version','documents'} or manifest['format']!='life-journal.package' or (type(manifest['version']) is not int or manifest['version']!=1):raise ValueError('ZIP Manifest版本或字段无效')
        docs=manifest['documents']
        if not isinstance(docs,list) or not 1<=len(docs)<=20 or any(not isinstance(x,str) for x in docs) or len(set(docs))!=len(docs):raise ValueError('documents需为不重复的内容路径列表')
        records=[];media=[];places=[];preferences=None;used={'manifest.json'}
        for name in docs:
            safe_path(name)
            if name not in files:raise ValueError('内容文件缺失')
            value=parse_raw(files[name],name)
            if not isinstance(value,dict) or set(value)-{'format','version','records','media','places','preferences'} or value.get('format')!='life-journal.exchange' or type(value.get('version')) is not int or value['version']!=1:raise ValueError('内容格式或版本无效')
            if any(not isinstance(value.get(k,[]),list) for k in ('records','media','places')):raise ValueError('内容集合需为列表')
            if preferences is not None and preferences!=value.get('preferences',{}):raise ValueError('同一ZIP的临时规则冲突，请分别预览')
            preferences=value.get('preferences',{})
            records+=value.get('records',[]);media+=value.get('media',[]);places+=value.get('places',[]);used.add(name)
        value=Exchange(format='life-journal.exchange',version=1,records=records,media=media,places=places,preferences=preferences or {})
        photos={}
        for m in value.media:
            if m.path:
                safe_path(m.path)
                if m.path not in files or m.path in used:raise ValueError('照片路径缺失或与内容文件冲突')
                photos[m.path]=files[m.path]
        if set(files)-used-set(photos):raise ValueError('ZIP含未声明文件，禁止执行或隐式导入')
        return value,photos


def parse_raw(data,name):
    if name.lower().endswith('.md'):return markdown_raw(data)
    if name.lower().endswith('.json'):return json_data(data)
    raise ValueError('内容仅支持.md或.json')


def parse(data,name):
    return Exchange.model_validate(parse_raw(data,name))
