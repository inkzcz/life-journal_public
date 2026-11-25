"""Bind verified binary, exact sources, notices and replacement receipts.

Creates an exclusive delivery directory; no tag, Release, Registry or NAS access.
Only the single approved business TAR and explicit source/deployment files enter
the output. Synthetic database directories and raw test logs are never copied.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import corresponding_sources as sources
from scripts.release_authorization import read_authorization, release_version, validate_authorization


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def safe_relative(name):
    return (bool(name) and not name.startswith('/') and '\\' not in name
            and all(p not in ('','.','..') for p in name.split('/'))
            and not any(ord(c)<32 for c in name))


def read(path):
    return json.loads(Path(path).read_text())


def require_receipts(installation,pillow,layers,debian):
    if not (installation.get('four_container_health')=='passed'
            and installation.get('ordinary_backup_and_independent_restore')=='passed'
            and installation.get('restart_and_database_persistence')=='passed'
            and installation.get('restored_login')=='passed'
            and installation.get('production_or_nas_accessed') is False
            and installation.get('lgpl_replacement',{}).get('modified_library_loaded') is True
            and installation['lgpl_replacement'].get('interface_compatible_query')=='passed'
            and pillow.get('modified_lgpl_shim_loaded') is True
            and pillow.get('library_relinked_from_source') is True
            and pillow.get('pillow_api_compatible') is True
            and layers.get('passed') is True and layers.get('finding_count')==0
            and debian.get('preserved_legal_texts')==410 and debian.get('browser_packages',0)>0
            and 'libpq.so.5' in debian.get('psycopg_c_linkage','')):
        raise ValueError('Required installation/source replacement/layer receipt failed or missing')


def require_sources(inventory,source_report,browser):
    records=source_report['records']
    installed={sources.source_identity(p) for p in inventory['packages'] if p['ecosystem']=='deb'}
    supplied={(p['name'],p['version']) for p in records if p['ecosystem']=='deb'}
    if not installed <= supplied:
        raise ValueError('Installed Debian/PGDG corresponding source missing')
    python={(p['name'].lower().replace('_','-'),p['version']) for p in inventory['packages'] if p['ecosystem']=='pypi'}
    supplied_python={(p['name'].lower().replace('_','-'),p['version']) for p in records if p['ecosystem']=='pypi'}
    if not python <= supplied_python or any(name=='psycopg-binary' for name,_ in python):
        raise ValueError('Python source missing or opaque psycopg-binary bundle still installed')
    if not any(name=='psycopg-c' for name,_ in python):
        raise ValueError('Expected source-built database accelerator')
    if any('psycopg_binary' in p for p in inventory['bundled_native_libraries']):
        raise ValueError('Unreviewed bundled database libraries remain')
    needed={(p['name'],p['version']) for p in browser['packages']}
    supplied_browser={(p['name'],p['version']) for p in records if p['ecosystem']=='browser-preferred-source'}
    if not needed <= supplied_browser:
        raise ValueError('Browser preferred source is incomplete')
    if not any(p['ecosystem']=='cpython' for p in records) or not any(p['ecosystem']=='go-runtime' for p in records):
        raise ValueError('Runtime source/checksum receipt missing')
    for module in inventory['go_modules']:
        if module['version']=='(devel)':
            if module['name']!='caddy':
                raise ValueError('Unreviewed generated Go root')
        elif not module.get('retained_source_archive') or module.get('status')!='verified-module-notices':
            raise ValueError('Actual Go module source/notice missing')


def verify_source_files(root,report):
    expected={'sources.json'}
    for package in report['records']:
        for record in package['files']:
            name=record['path']
            if not safe_relative(name) or not name.startswith('sources/'):
                raise ValueError('Invalid source receipt path')
            path=root/name
            if path.is_symlink() or not path.is_file() or digest(path)!=record['sha256']:
                raise ValueError('Source receipt checksum mismatch: '+name)
            expected.add(name)
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() or p.is_symlink()}
    if actual!=expected:
        raise ValueError('Unlisted or missing source artifact; nothing may be published')


def verify_evidence_files(root,inventory):
    expected={'inventory.json'}
    records=list(inventory['notices'])
    for entry in [*inventory['packages'],*inventory['go_modules']]:
        if entry.get('retained_source_archive'):
            records.append({'path':entry['retained_source_archive'],'sha256':entry['retained_source_sha256']})
    for record in records:
        if not safe_relative(record['path']):
            raise ValueError('Invalid evidence receipt path')
        path=root/record['path']
        if path.is_symlink() or not path.is_file() or digest(path)!=record['sha256']:
            raise ValueError('Evidence source/notice checksum mismatch')
        expected.add(record['path'])
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() or p.is_symlink()}
    if actual!=expected:
        raise ValueError('Unlisted artifact in license evidence')


def verify_python_receipt(evidence,source_report):
    path=evidence/'image/usr/share/doc/life-journal/python-install-report.json'
    report=read(path)
    lookup={(p['name'].lower().replace('_','-'),p['version']):p
            for p in source_report['records'] if p['ecosystem']=='pypi'}
    for package in report['install']:
        key=package['metadata']['name'].lower().replace('_','-'),package['metadata']['version']
        receipt=lookup.get(key)
        info=package['download_info'];url=info['url']
        sources.checked_url(url)
        filename=url.rsplit('/',1)[-1]
        expected=info['archive_info']['hashes']['sha256']
        if not receipt or receipt['published_artifacts'].get(filename)!=expected:
            raise ValueError('Installed Python artifact is not bound to exact publisher release: '+key[0])
        if key[0]=='psycopg-c' and not filename.endswith('.tar.gz'):
            raise ValueError('Database accelerator was not built from the provided source')


def copy_tree(source,target):
    for path in sorted(source.rglob('*')):
        if path.is_symlink():
            raise ValueError('Evidence tree contains a symlink')
        if path.is_file():
            relative=path.relative_to(source);dest=target/relative
            dest.parent.mkdir(parents=True,exist_ok=True)
            try:os.link(path,dest)
            except OSError:shutil.copyfile(path,dest)


def write_deployment_zip(root,orchestration,target):
    """Keep tagged deployment inputs/legal bytes and reviewed publisher guides."""
    with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ('compose.yaml','.env.example','LICENSE','COPYRIGHT.md'):
            archive.write(root/name,name)
        for name in ('install','upgrade','backup-restore','known-limitations','upgrade-001'):
            path='docs/'+name+'.md'
            archive.write(orchestration/path,path)


def require_release_authorization(authority,version):
    return validate_authorization(authority,version)


def require_upgrade_receipt(report,version,revision):
    current=release_version(version);previous={'v5.1.10':'5.1.9','v5.1.11':'5.1.10'}.get(current)
    if previous is None:raise ValueError('Unknown same-schema upgrade route')
    if (report.get('synthetic_same_schema_upgrade')!='passed'
            or report.get('from_version')!=previous or report.get('to_version')!=current[1:]
            or report.get('image_tag')!=version or report.get('source_commit')!=revision
            or report.get('schema_before')!='0021_anniversary_calendar'
            or report.get('schema_after')!='0021_anniversary_calendar'
            or report.get('old_backup_created_and_verified') is not True
            or report.get('existing_article_fields_cards_media_itinerary')!='preserved'
            or report.get('new_default_type_and_travel_toggles')!='passed'
            or report.get('candidate_restart_persistence')!='passed'
            or report.get('production_or_nas_accessed') is not False):
        raise ValueError('Exact same-schema upgrade receipt missing or failed')
    if current=='v5.1.11' and (report.get('old_business_tar_sha256')!='ac766b4619db3bb5883de1bf18289993c07d3c452cbfea2ea175af16fbabef7a' or report.get('legacy_get_notification_configuration_and_logs')!='preserved' or report.get('six_historical_card_kinds')!='preserved' or report.get('old_template_binding_and_explicit_daily_mode')!='preserved'):
        raise ValueError('Historical v5.1.10 cards/notification receipt missing')


def require_candidate_identity(version,product_version,revision):
    if (not re.fullmatch(r'\d+\.\d+\.\d+',product_version)
            or not re.fullmatch(r'[0-9a-f]{40}',revision)
            or not re.fullmatch('v'+re.escape(product_version)+r'-candidate\.[0-9a-f]{7,40}',version)
            or not revision.startswith(version.rsplit('.',1)[1])):
        raise ValueError('Validation-only requires an exact source-bound development candidate')


def package(args):
    root=args.root.resolve();bundle=args.bundle.resolve()
    revision=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
    orchestration=(args.orchestration_root or root).resolve()
    orchestration_revision=subprocess.check_output(['git','-C',str(orchestration),'rev-parse','HEAD'],text=True).strip()
    if subprocess.check_output(['git','-C',str(orchestration),'status','--porcelain','--untracked-files=no']):
        raise ValueError('Publication orchestration source changed during verification')
    if subprocess.check_output(['git','-C',str(root),'status','--porcelain','--untracked-files=no']):
        raise ValueError('Tracked source changed during verification')
    delivery=read(bundle/'manifest.json');version=delivery['version']
    validation_only=getattr(args,'validate_only',False)
    if validation_only:
        require_candidate_identity(version,(root/'VERSION').read_text().strip(),revision)
    else:
        require_release_authorization(read_authorization(root,version),version)
    if delivery['source']['revision']!=revision or delivery['source']['revision_verified'] is not True:
        raise ValueError('Business image/source commit mismatch')
    expected_name='life-journal-app-'+version+'-amd64.tar'
    if (set(delivery['images'])!={'app'} or set(delivery['tar_sha256'])!={expected_name}
            or digest(bundle/expected_name)!=delivery['tar_sha256'][expected_name]):
        raise ValueError('Expected one intact business image TAR')
    with tarfile.open(bundle/expected_name) as archive:
        rows=json.load(archive.extractfile('manifest.json'))
        if len(rows)!=1 or rows[0]['RepoTags']!=['life-journal:'+version]:
            raise ValueError('Business TAR must contain exactly one approved image')
    inventory=read(args.evidence/'inventory.json');source_report=read(args.sources/'sources.json')
    if (inventory['image']['archive_sha256']!=delivery['tar_sha256'][expected_name]
            or 'sha256:'+inventory['image']['config_sha256']!=delivery['images']['app']['config_digest']
            or inventory['image']['architecture']!='amd64' or inventory['image']['os']!='linux'):
        raise ValueError('Source/license inventory belongs to another binary')
    browser=read(args.evidence/'image/srv/legal/browser-notices.json')
    installation,pillow,layers,debian=map(read,[args.installation,args.pillow,args.layers,args.debian])
    require_receipts(installation,pillow,layers,debian)
    upgrade=getattr(args,'upgrade',None)
    if version in ('v5.1.10','v5.1.11') or version.startswith(('v5.1.10-candidate.','v5.1.11-candidate.')):
        if not upgrade:raise ValueError('Same-schema upgrade receipt required')
        require_upgrade_receipt(read(upgrade),version,revision)
    if installation.get('image_tag')!=version or debian.get('image_tag')!=version:
        raise ValueError('Runtime validation belongs to another image tag')
    require_sources(inventory,source_report,browser)
    verify_source_files(args.sources,source_report)
    verify_evidence_files(args.evidence,inventory)
    verify_python_receipt(args.evidence,source_report)
    paths={p['path'] for p in browser['packages']}
    selected=[p for p in inventory['packages'] if p['ecosystem']!='npm' or p['package_path'] in paths]
    actual_browser={p['package_path'] for p in selected if p['ecosystem']=='npm'}
    if actual_browser!=paths or any(not p.get('retained_source_archive') or not p.get('notice_files')
            for p in selected if p['ecosystem']=='npm'):
        raise ValueError('Actual bundled browser source/notices incomplete')
    if validation_only:
        print(json.dumps({'validation_only':True,'source_commit':revision,'version':version,
            'business_tar_sha256':delivery['tar_sha256'][expected_name],
            'runtime_source_notice_and_replacement_checks':'passed',
            'distribution_package_created':False,'publication_authorized':False},indent=2))
        return
    if args.output.exists() or args.output.is_symlink():
        raise ValueError('New output directory required; nothing overwritten')
    args.output.mkdir(mode=0o700)
    work=Path(tempfile.mkdtemp(prefix='lj-corresponding-source-',dir=args.output.parent))
    copy_tree(args.sources,work)
    # Keep runtime browser packages only. General-purpose compiler/tool packages
    # are not in the emitted chunks; do not redistribute unreviewed dev archives.
    allowed_archives={p['retained_source_archive'] for p in selected
                      if p.get('retained_source_archive')}
    allowed_archives.update(m['retained_source_archive'] for m in inventory['go_modules']
                            if m.get('retained_source_archive'))
    for source in sorted(args.evidence.rglob('*')):
        if source.is_symlink():
            raise ValueError('Symlink in legal evidence')
        if not source.is_file():
            continue
        name=source.relative_to(args.evidence).as_posix()
        if name=='inventory.json':
            continue
        if name.startswith('sources/') and name not in allowed_archives:
            continue
        target=work/'notices-and-verified-modules'/name
        target.parent.mkdir(parents=True,exist_ok=True)
        try:os.link(source,target)
        except OSError:shutil.copyfile(source,target)
    for p in selected:
        if p.get('retained_source_archive') and digest(args.evidence/p['retained_source_archive'])!=p['retained_source_sha256']:
            raise ValueError('npm source receipt checksum mismatch')
    for m in inventory['go_modules']:
        if m.get('retained_source_archive') and digest(args.evidence/m['retained_source_archive'])!=m['retained_source_sha256']:
            raise ValueError('Go source receipt checksum mismatch')
    inventory['packages']=selected
    inventory['notices']=[n for n in inventory['notices'] if (work/'notices-and-verified-modules'/n['path']).is_file()]
    for notice in inventory['notices']:
        if (not safe_relative(notice['path'])
                or digest(work/'notices-and-verified-modules'/notice['path'])!=notice['sha256']):
            raise ValueError('Current upstream notice integrity mismatch')
    (work/'notices-and-verified-modules/inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
    app=work/'application';app.mkdir()
    subprocess.run(['git','-C',str(root),'archive','--format=tar.gz','--prefix=life-journal/',
        '-o',str(app/'life-journal-source.tar.gz'),revision],check=True)
    if orchestration_revision!=revision:
        target=work/'build-orchestration';target.mkdir()
        subprocess.run(['git','-C',str(orchestration),'archive','--format=tar.gz',
            '--prefix=life-journal-orchestration/','-o',str(target/'source.tar.gz'),orchestration_revision],check=True)
    for name in ('LICENSE','COPYRIGHT.md'):
        shutil.copyfile(root/name,work/name)
    for name,path in [('installation.json',args.installation),('pillow-relink.json',args.pillow),
                      ('layer-scan.json',args.layers),('runtime-probe.json',args.debian)]:
        target=work/'validation'/name;target.parent.mkdir(exist_ok=True);shutil.copyfile(path,target)
    if upgrade:shutil.copyfile(upgrade,work/'validation/same-schema-upgrade.json')
    shutil.copyfile(root/'third_party/BINARY_NOTICE.md',work/'NOTICE.md')
    shutil.copyfile(orchestration/'third_party/SOURCE_BUILD.md',work/'BUILD_AND_REPLACE.md')
    receipt={'format':'life-journal-binary-corresponding-source-v1','version':version,
        'source_commit':revision,'platform':'linux/amd64','business_tar':expected_name,
        'build_orchestration_commit':orchestration_revision,
        'business_tar_sha256':delivery['tar_sha256'][expected_name],
        'business_image_config_digest':delivery['images']['app']['config_digest'],
        'source_archive_records':source_report['records'],
        'binary_redistribution_obligations_completed':True,
        'scope':'Exact enumerated software; original GPL grant and all upstream grants preserved. Same-place source delivery; no written source offer.',
        'windows_and_z4s':'待本地验收; owner accepts as post-release checks',
        'UPGRADE-001':'Known historical issue, not reproduced or claimed fixed; migration safeguards retained',
        'files':[{'path':str(p.relative_to(work)),'sha256':digest(p)} for p in sorted(work.rglob('*')) if p.is_file()]}
    (work/'DISTRIBUTION_MANIFEST.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    source_name='life-journal-source-and-licenses-'+version+'.tar.gz'
    with tarfile.open(args.output/source_name,mode='x:gz') as archive:
        archive.add(work,arcname='life-journal-source-and-licenses')
    try:os.link(bundle/expected_name,args.output/expected_name)
    except OSError:shutil.copyfile(bundle/expected_name,args.output/expected_name)
    delivery['corresponding_source']={'file':source_name,'sha256':digest(args.output/source_name),
        'obligations_completed':True,'source_commit':revision,
        'source_manifest':'life-journal-source-and-licenses/DISTRIBUTION_MANIFEST.json'}
    delivery['build_orchestration_commit']=orchestration_revision
    (args.output/'manifest.json').write_text(json.dumps(delivery,ensure_ascii=False,indent=2)+'\n')
    shutil.copyfile(bundle/'images.json',args.output/'images.json')
    for name,path in {'INSTALL.md':'docs/install.md','UPGRADE.md':'docs/upgrade.md',
                       'KNOWN_LIMITATIONS.md':'docs/known-limitations.md','RELEASE_NOTES.md':'docs/release-notes-'+release_version(version)+'.md'}.items():
        shutil.copyfile(orchestration/path,args.output/name)
    write_deployment_zip(root,orchestration,args.output/('life-journal-deploy-'+version+'.zip'))
    sums=''.join(digest(p)+'  '+p.name+'\n' for p in sorted(args.output.iterdir()) if p.is_file())
    if any(p.stat().st_size>=2*1024**3 for p in args.output.iterdir()):
        raise ValueError('Release asset exceeds GitHub 2GiB limit; no publication allowed')
    (args.output/'SHA256SUMS.txt').write_text(sums)
    print(json.dumps({'source_commit':revision,'version':version,'output_files':len(list(args.output.iterdir())),
        'business_tar_sha256':delivery['tar_sha256'][expected_name],
        'source_and_licenses_sha256':digest(args.output/source_name),
        'binary_distribution_obligations_completed':True},indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('root','bundle','evidence','sources','installation','pillow','layers','debian','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--orchestration-root',type=Path)
    parser.add_argument('--upgrade',type=Path)
    parser.add_argument('--validate-only',action='store_true',help='Verify development candidate receipts; create no distributable assets or authorization')
    args=parser.parse_args()
    package(args)


if __name__=='__main__':
    main()
