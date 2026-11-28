"""Delete only a verified, current formal-run artifact after public-byte checks.

No repository-wide retention sweep, release-asset deletion, NAS or data access.
"""
import argparse
import json
import re
import subprocess

REPOSITORY='inkzcz/life-journal_public'

def validate_artifact(metadata,*,artifact_id,run_id,name,version,revision):
    if (version not in {'v5.1.11','v5.1.12'}
            or not re.fullmatch('[0-9a-f]{40}',revision)
            or type(artifact_id) is not int or artifact_id<=0 or type(run_id) is not int or run_id<=0
            or name!='life-journal-delivery-'+version+'-'+revision
            or metadata.get('id')!=artifact_id or metadata.get('name')!=name
            or metadata.get('expired') is not False
            or metadata.get('workflow_run',{}).get('id')!=run_id
            or metadata.get('workflow_run',{}).get('head_sha')!=revision):
        raise ValueError('Artifact does not match this verified formal run; nothing deleted')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repository',required=True);p.add_argument('--artifact-id',type=int,required=True)
    p.add_argument('--run-id',type=int,required=True);p.add_argument('--name',required=True)
    p.add_argument('--version',required=True);p.add_argument('--revision',required=True)
    p.add_argument('--publication-verified',choices=['true'],required=True)
    a=p.parse_args()
    if a.repository!=REPOSITORY:raise ValueError('Unexpected repository; nothing deleted')
    path='repos/'+REPOSITORY+'/actions/artifacts/'+str(a.artifact_id)
    metadata=json.loads(subprocess.check_output(['gh','api','--method','GET',path],text=True))
    validate_artifact(metadata,artifact_id=a.artifact_id,run_id=a.run_id,name=a.name,version=a.version,revision=a.revision)
    subprocess.run(['gh','api','--method','DELETE',path],check=True)
    print(json.dumps({'deleted_artifact_id':a.artifact_id,'verified_formal_run':a.run_id,'release_assets_untouched':True}))

if __name__=='__main__':main()
