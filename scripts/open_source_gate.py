"""Fail closed on unsafe tracked files or an explicit no-history source snapshot.

Reports locations and categories only. This complements Gitleaks and owner review;
it does not claim to recognize arbitrary encodings, personal names or all secrets.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

# A snapshot scan must not modify the snapshot it is about to verify.
sys.dont_write_bytecode=True
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.image_private_keys import has_private_pem
from scripts.release_authorization import RELEASES, read_authorization

FORBIDDEN_SUFFIXES = frozenset({'.db','.sqlite','.sqlite3','.sql','.dump','.backup','.bak',
    '.pyc','.pyo','.key','.pem','.p12','.pfx','.tar','.tgz','.gz','.zip','.7z',
    '.jpg','.jpeg','.png','.webp','.gif','.heic','.tif','.tiff','.woff','.woff2','.ttf','.otf',
    '.exe','.dll','.so','.o','.a','.wasm','.class','.jar','.whl','.mp3','.mp4','.mov','.avi'})
SECRET_SHAPES = {
    'github-token': re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b'),
    'openai-token': re.compile(rb'\bsk-(?:proj-)?[A-Za-z0-9_-]{30,}\b'),
    'tailscale-key': re.compile(rb'\btskey-(?:auth|api)-[A-Za-z0-9_-]{15,}\b'),
    'aws-access-id': re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
}
EMAIL = re.compile(rb'(?<![\w.+-])[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![\w.-])')
ASSIGNMENT = re.compile(rb'''(?im)\b(?:password|passwd|api[_-]?key|setup[_-]?key|jwt[_-]?secret|session[_-]?secret)\s*["']?\s*[:=]\s*["']([A-Za-z0-9_./+=-]{16,})["']''')
MAX_BYTES = 8 * 1024 * 1024
GPL_SHA256 = '3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986'
PHASE_A_SCOPE = 'phase-a-original-source-license-only'
ORIGINAL_RIGHTS_SCOPE = 'owner-controlled-protectable-original-source-and-original-increments'


def license_proposal_confirmed(data):
    """Only phase A original-source authorization; never publication approval."""
    try:
        proposal=json.loads(data)
        return (isinstance(proposal,dict) and proposal.get('state')=='owner-confirmed'
                and proposal.get('owner_authorization') is True
                and proposal.get('original_rights_confirmed') is True
                and proposal.get('source_third_party_review_complete') is True
                and proposal.get('selected_spdx')=='GPL-3.0-or-later'
                and proposal.get('owner_authorization_scope')==PHASE_A_SCOPE
                and proposal.get('original_rights_scope')==ORIGINAL_RIGHTS_SCOPE)
    except (ValueError,TypeError):
        return False


def license_materials_confirmed(root):
    """Check the actual grant/text and recorded phase A statement, not just flags."""
    root=Path(root)
    try:
        paths=['LICENSE','COPYRIGHT.md','licensing/GPL-3.0.txt',
               'licensing/proposal.json','licensing/PHASE_A_AUTHORIZATION.json']
        for name in paths:
            path=root/name
            if (not path.is_file() or path.is_symlink() or path.stat().st_size>MAX_BYTES
                    or any(p.is_symlink() for p in path.parents)):
                return False
        proposal=json.loads((root/'licensing/proposal.json').read_bytes())
        if not license_proposal_confirmed(json.dumps(proposal)):
            return False
        raw=(root/'LICENSE').read_bytes()
        if (hashlib.sha256(raw).hexdigest()!=GPL_SHA256
                or raw!=(root/'licensing/GPL-3.0.txt').read_bytes()
                or proposal.get('license_text_sha256')!=GPL_SHA256):
            return False
        authority=json.loads((root/'licensing/PHASE_A_AUTHORIZATION.json').read_bytes())
        if (proposal.get('owner_authorization_record')!='licensing/PHASE_A_AUTHORIZATION.json'
                or authority.get('phase')!='A' or authority.get('approved') is not True
                or authority.get('selected_spdx')!=proposal['selected_spdx']
                or authority.get('authorization_scope')!=PHASE_A_SCOPE
                or authority.get('original_rights_scope')!=ORIGINAL_RIGHTS_SCOPE):
            return False
        notice=' '.join((root/'COPYRIGHT.md').read_text().split())
        credit=proposal.get('copyright_notice')
        return (isinstance(credit,str) and bool(credit) and credit in notice
                and authority.get('copyright_notice')==credit and 'DRAFT' not in notice
                and 'either version 3 of the License, or (at your option) any later version' in notice
                and 'Third-party' in notice)
    except (OSError,ValueError,KeyError,TypeError):
        return False


def snapshot_checksums(root):
    """Canonical source tree hash input shared by receipts and the phase B gate."""
    root=Path(root)
    manifest=json.loads((root/'EXPORT_MANIFEST.json').read_bytes())
    names=sorted([entry['path'] for entry in manifest['files']]+['EXPORT_MANIFEST.json'])
    if len(names)!=len(set(names)) or any(not valid_path(name) for name in names):
        raise ValueError('Invalid or duplicate source paths')
    return ''.join(hashlib.sha256((root/name).read_bytes()).hexdigest()+'  '+name+'\n'
                   for name in names).encode('utf-8')


def publication_approval_failure(root, approval_file, repository):
    """Phase B operation guard. An external owner record binds immutable bytes.

    This governs this preparation workflow, not recipients' rights under GPL.
    No repository creation or upload is implemented here.
    """
    root=Path(root).absolute()
    if not license_materials_confirmed(root):
        return 'phase-a-license-required'
    if not approval_file or not repository:
        return 'separate-phase-b-record-and-destination-required'
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+',repository):
        return 'phase-b-destination-invalid'
    path=Path(approval_file).absolute()
    if root in path.parents:
        return 'phase-b-record-must-be-outside-snapshot'
    try:
        if (not path.is_file() or path.is_symlink() or path.stat().st_size>MAX_BYTES
                or any(p.is_symlink() for p in path.parents)):
            return 'phase-b-record-missing-or-unsafe'
        approval=json.loads(path.read_bytes())
        if (approval.get('format')!='life-journal-publication-approval-v1'
                or approval.get('phase')!='B' or approval.get('publication_approved') is not True):
            return 'phase-b-owner-approval-pending'
        if (approval.get('scope')!='clean-source-snapshot-only'
                or approval.get('hash_definition')!='sha256sums-lf-includes-export-manifest-v1'
                or not isinstance(approval.get('owner_confirmation_reference'),str)
                or not approval['owner_confirmation_reference'].strip()):
            return 'phase-b-scope-or-confirmation-reference-invalid'
        raw=(root/'EXPORT_MANIFEST.json').read_bytes();manifest=json.loads(raw)
        if (manifest.get('format')!='life-journal-public-source-v1'
                or not isinstance(manifest.get('source_commit'),str)
                or not re.fullmatch(r'[0-9a-f]{40}',manifest['source_commit'])):
            return 'phase-b-snapshot-identity-invalid'
        if (manifest.get('target_repository')!=repository or approval.get('repository')!=repository
                or manifest.get('distribution_scope')!='source-only'
                or manifest.get('original_git_history_included') is not False
                or manifest.get('binary_artifacts_included') is not False):
            return 'phase-b-destination-or-source-scope-mismatch'
        if approval.get('source_commit')!=manifest.get('source_commit'):
            return 'phase-b-commit-mismatch'
        if approval.get('manifest_sha256')!=hashlib.sha256(raw).hexdigest():
            return 'phase-b-manifest-mismatch'
        if approval.get('source_tree_sha256')!=hashlib.sha256(snapshot_checksums(root)).hexdigest():
            return 'phase-b-source-tree-mismatch'
        return None
    except (OSError,ValueError,KeyError,TypeError):
        return 'phase-b-record-or-snapshot-invalid'


def git(root, *parts):
    return subprocess.check_output(['git','-C',str(root),*parts], stderr=subprocess.DEVNULL)


def valid_path(name):
    path=PurePosixPath(name)
    return (bool(name) and not path.is_absolute() and '\\' not in name and ':' not in name
            and not any(ord(character)<32 for character in name)
            and all(p not in ('','.','..') for p in name.split('/')))


def scan_bytes(name, data, *, reviewed_copyright=False, binary_workflow_scope=None):
    """Only public rule IDs, path and line numbers leave this function."""
    findings=[]
    def add(kind, position=0):
        findings.append({'type':kind,'path':name,'line':data.count(b'\n',0,position)+1})
    parts=PurePosixPath(name).parts
    basename=parts[-1] if parts else ''
    if not valid_path(name):add('invalid-path');return findings
    if '.git' in parts or '.gitmodules' in parts:add('git-history-or-submodule')
    if basename.startswith('.env') and basename not in ('.env.example','.env.nas.example'):
        add('private-environment-file')
    if any(p.lower() in {'media','postgres','pgdata','backups','backup','__pycache__','node_modules'} for p in parts[:-1]):
        add('runtime-data-or-dependencies')
    if PurePosixPath(name).suffix.lower() in FORBIDDEN_SUFFIXES:add('binary-database-archive-or-key-file')
    if re.search(r'\.so(?:\.\d+)+$',basename,re.I):add('binary-database-archive-or-key-file')
    if len(data)>MAX_BYTES:add('oversized-unreviewed-file');return findings
    if b'\0' in data:add('unreviewed-binary')
    for category,pattern in SECRET_SHAPES.items():
        for match in pattern.finditer(data):add(category,match.start())
    if has_private_pem(io.BytesIO(data)):add('private-key-material')
    for match in EMAIL.finditer(data) if not reviewed_copyright else ():
        domain=match.group(1).lower()
        if not (domain in {b'example.com',b'example.org',b'example.net',b'openai.com'}
                or domain.endswith((b'.test',b'.invalid',b'.example',b'.localhost',b'.noreply.github.com'))):
            add('personal-email-needs-review',match.start())
    for match in ASSIGNMENT.finditer(data):
        if not match.group(1).lower().startswith((b'synthetic',b'example',b'placeholder',b'not-a-real',b'test-only',b'dummy')):
            add('hardcoded-secret-assignment',match.start())
    if basename in ('.env.example','.env.nas.example'):
        for offset,line in enumerate(data.splitlines(),1):
            key, separator,value=line.strip().partition(b'=')
            if separator and re.search(rb'(PASSWORD|SECRET|TOKEN|SETUP_KEY)',key,re.I) and value.strip():
                findings.append({'type':'nonempty-secret-example','path':name,'line':offset})
    if name.startswith('.github/workflows/'):
        patterns={
            'unsafe-pr-target':rb'pull_request_target',
            'excessive-token-permission':rb'permissions:\s*write-all|contents:\s*write|packages:\s*write',
            'environment-dump':rb'(?m)^\s*(?:run:.*)?(?:printenv|env\s*\||set\s+-x)',
            'publishing-or-sensitive-artifact':rb'upload-artifact@|docker\s+push|gh\s+release\s+(?:create|upload)|gh\s+repo\s+create',
        }
        # A separately recorded owner release instruction now permits the two
        # exact, technically reviewed workflows. Unknown paths/bytes retain the
        # original denial. PR-target, environment dumps, packages:write and
        # Registry/repository publishing are never exempted.
        if binary_workflow_scope in ('candidate-artifacts','v5.1.9-release','v5.1.10-release','v5.1.11-release','v5.1.12-release'):
            patterns['publishing-or-sensitive-artifact']=rb'docker\s+push|gh\s+repo\s+create'
            if binary_workflow_scope=='candidate-artifacts':
                patterns['publishing-or-sensitive-artifact']+=rb'|gh\s+release\s+(?:create|upload)'
            else:
                patterns['excessive-token-permission']=rb'permissions:\s*write-all|packages:\s*write'
        for kind,pattern in patterns.items():
            for match in re.finditer(pattern,data):add(kind,match.start())
    return findings


def orchestration_workflow_reviews(root,version,authorization_name,authorization_bytes):
    # This is an operator technical supplement, never a replacement owner grant.
    # Accept only this immutable v5.1.11 application's CI bytes, not new publishing
    # permissions/targets. Runtime preflight still compares tagged business files.
    if version!='v5.1.11':return {}
    path=root/'licensing/v5.1.11-release-orchestration-review.json'
    if not path.exists():return {}
    if (path.is_symlink() or not path.is_file() or path.stat().st_size>MAX_BYTES
            or any(p.is_symlink() for p in path.parents)):return {}
    record=json.loads(path.read_bytes())
    if (record.get('format')!='life-journal-release-orchestration-review-v1'
            or record.get('repository')!='inkzcz/life-journal_public'
            or record.get('version')!=version
            or record.get('original_authorization')!=authorization_name
            or record.get('original_authorization_sha256')!=hashlib.sha256(authorization_bytes).hexdigest()
            or record.get('application_source_commit')!='3c3a465e5ba1dd353a3886b6394907311e972865'
            or record.get('annotated_tag_sha')!='953a945b48dd8c11639f90ac62c2361b421469ab'
            or record.get('application_pull_request')!=5
            or record.get('technical_review_only') is not True
            or record.get('application_source_unchanged') is not True
            or record.get('original_owner_authorizations_unchanged') is not True
            or not record.get('owner_confirmation_reference')
            or set(record.get('workflows',{}))!={'.github/workflows/ci.yml'}):return {}
    return record['workflows']


def reviewed_binary_workflows(root):
    product=(root/'VERSION').read_text().strip() if (root/'VERSION').is_file() else '5.1.9'
    if product not in ('5.1.9','5.1.10','5.1.11','5.1.12'):return {}
    version='v'+product
    name=RELEASES[version][0]
    path=root/name
    try:
        if (not path.is_file() or path.is_symlink() or any(p.is_symlink() for p in path.parents)
                or path.stat().st_size>MAX_BYTES):
            return {}
        authority=read_authorization(root,version)
        if (authority.get('format')!='life-journal-binary-release-authorization-v1'
                or authority.get('binary_publication_approved') is not True
                or authority.get('repository')!='inkzcz/life-journal_public'
                or authority.get('version')!=version
                or authority.get('registry_push_approved') is not False
                or authority.get('nas_access_approved') is not False
                or not authority.get('owner_confirmation_reference')):
            return {}
        reviews=dict(authority.get('technically_reviewed_workflows',{}))
        reviews.update(orchestration_workflow_reviews(root,version,name,path.read_bytes()))
        result={}
        for name,scope in {'.github/workflows/ci.yml':'candidate-artifacts',
                           '.github/workflows/release.yml':version+'-release'}.items():
            record=reviews.get(name,{})
            source=root/name
            if (record.get('scope')==scope and source.is_file() and not source.is_symlink()
                    and record.get('sha256')==hashlib.sha256(source.read_bytes()).hexdigest()):
                result[name]=scope
        return result
    except (OSError,ValueError,TypeError):
        return {}


def scan(root, *, snapshot=False, changed_since=None, require_license=False,
         require_publication=False, approval_file=None, publication_repository=None):
    require_license=require_license or require_publication
    root=Path(root).absolute()
    findings=[]
    binary_workflows=reviewed_binary_workflows(root)
    public_notices={}
    notice_index=root/'third_party/notice-index.json'
    if notice_index.exists():
        try:
            if notice_index.is_symlink() or any(p.is_symlink() for p in notice_index.parents) or notice_index.stat().st_size>MAX_BYTES:
                raise ValueError('Invalid copyright notice index')
            document=json.loads(notice_index.read_text())
            if document['format']!='life-journal-reviewed-notices-v1':raise ValueError('Invalid format')
            for entry in document['files']:
                path,value=entry['path'],entry['sha256']
                if (not valid_path(path) or not path.startswith('third_party/licenses/')
                        or path in public_notices or not re.fullmatch('[0-9a-f]{64}',value)):
                    raise ValueError('Invalid notice registration')
                public_notices[path]=value
        except (OSError,ValueError,KeyError,TypeError):
            findings.append({'type':'invalid-public-notice-index','path':'third_party/notice-index.json','line':1})
            public_notices={}
    if snapshot:
        names=[]
        for directory,dirs,files in os.walk(root,followlinks=False):
            for name in list(dirs):
                path=Path(directory)/name
                if name=='.git' or path.is_symlink():
                    findings.append({'type':'git-history-or-symlink','path':path.relative_to(root).as_posix(),'line':1})
                    dirs.remove(name)
            names.extend((Path(directory)/name).relative_to(root).as_posix() for name in files)
    else:
        if changed_since:
            if not re.fullmatch('[0-9a-f]{40}',changed_since):raise ValueError('Expected a full base commit SHA')
            names=git(root,'diff','--diff-filter=ACMRT','--name-only','-z',changed_since,'HEAD').decode().split('\0')[:-1]
        else:names=git(root,'ls-files','-z').decode().split('\0')[:-1]
    for name in sorted(names):
        path=root/name
        if path.is_symlink() or any(p.is_symlink() for p in path.parents if p!=root.parent):
            findings.append({'type':'symlink','path':name,'line':1});continue
        if not path.is_file():
            findings.append({'type':'missing-or-special-file','path':name,'line':1});continue
        if path.stat().st_size>MAX_BYTES:
            findings.append({'type':'oversized-unreviewed-file','path':name,'line':1});continue
        content=path.read_bytes()
        reviewed=name in public_notices and hashlib.sha256(content).hexdigest()==public_notices[name]
        if name in public_notices and not reviewed:
            findings.append({'type':'changed-public-copyright-notice','path':name,'line':1})
        # Preserve verified third-party public author credits verbatim. This
        # exact path+hash exception applies only to the personal-email heuristic;
        # Token, private-key, binary, workflow and secret checks still run.
        findings.extend(scan_bytes(name,content,reviewed_copyright=reviewed,
                                   binary_workflow_scope=binary_workflows.get(name)))
    if require_license and not (root/'LICENSE').is_file():
        findings.append({'type':'owner-license-decision-pending','path':'LICENSE','line':1})
    proposal_path=root/'licensing/proposal.json'
    if require_license and proposal_path.exists():
        if (proposal_path.is_symlink() or any(p.is_symlink() for p in proposal_path.parents)
                or proposal_path.stat().st_size>MAX_BYTES
                or not license_proposal_confirmed(proposal_path.read_bytes())):
            findings.append({'type':'owner-rights-confirmation-pending','path':'licensing/proposal.json','line':1})
        elif not license_materials_confirmed(root):
            findings.append({'type':'original-license-materials-invalid','path':'COPYRIGHT.md','line':1})
    elif require_license and (root/'LICENSE').is_file():
        findings.append({'type':'owner-rights-confirmation-pending','path':'licensing/proposal.json','line':1})
    manifest_path=root/'EXPORT_MANIFEST.json'
    if snapshot and manifest_path.is_file():
        try:
            manifest=json.loads(manifest_path.read_text())
            entries=manifest['files'];expected={item['path']:item['sha256'] for item in entries}
            if len(expected)!=len(entries) or any(not valid_path(name) for name in expected):
                raise ValueError('Invalid manifest paths')
            for name in set(names)-set(expected)-{'EXPORT_MANIFEST.json'}:
                findings.append({'type':'unlisted-export-file','path':name,'line':1})
            for name,digest in expected.items():
                path=root/name
                if (not path.is_file() or path.is_symlink() or path.stat().st_size>MAX_BYTES
                        or hashlib.sha256(path.read_bytes()).hexdigest()!=digest):
                    findings.append({'type':'export-hash-mismatch','path':name,'line':1})
        except (OSError,ValueError,KeyError,TypeError):
            findings.append({'type':'invalid-export-manifest','path':'EXPORT_MANIFEST.json','line':1})
    if require_publication:
        reason=('publication-requires-pristine-snapshot' if not snapshot else
                publication_approval_failure(root,approval_file,publication_repository))
        if reason:
            findings.append({'type':'phase-b-publication-not-approved','path':'publication-approval',
                             'line':1,'reason':reason})
    return {'passed':not findings,'files_checked':len(names),'findings':findings[:100],
            'finding_count':len(findings),'scope':'snapshot' if snapshot else 'changed-tracked' if changed_since else 'tracked',
            'limitations':'Known formats only; owner review and a separate Gitleaks scan remain required.'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path.cwd());parser.add_argument('--snapshot',action='store_true')
    parser.add_argument('--changed-since');parser.add_argument('--require-license',action='store_true')
    parser.add_argument('--require-publication',action='store_true',
                        help='Separate phase B workflow guard; does not create or publish anything')
    parser.add_argument('--approval-file',type=Path);parser.add_argument('--publication-repository')
    args=parser.parse_args(argv)
    try:report=scan(args.root,snapshot=args.snapshot,changed_since=args.changed_since,require_license=args.require_license,
                    require_publication=args.require_publication,approval_file=args.approval_file,
                    publication_repository=args.publication_repository)
    except (OSError,ValueError,subprocess.SubprocessError):
        print('Source gate could not inspect the requested source.',file=sys.stderr);return 2
    print(json.dumps(report,indent=2,ensure_ascii=True))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
