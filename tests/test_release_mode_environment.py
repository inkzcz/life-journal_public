"""Execute the real packaging shell routing with an isolated recorder, no Docker."""
import json,os,shutil,subprocess
from pathlib import Path
import pytest,yaml
ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.skipif(shutil.which('bash') is None,reason='Bash shell routing requires a Bash host')
@pytest.mark.parametrize('release,image,validation,ready',[
 ('','v5.1.11-candidate.'+'a'*7,True,False),
 ('v5.1.11','v5.1.11',False,True),
])
def test_real_package_step_inherits_release_input_without_changing_candidate_safety(tmp_path,release,image,validation,ready):
    doc=yaml.safe_load((ROOT/'.github/workflows/ci.yml').read_text())
    step=next(s for s in doc['jobs']['docker-installation']['steps'] if s.get('id')=='package')
    assert step['env']=={'RELEASE_VERSION':'${{ inputs.release_version }}'}
    bind=tmp_path/'bin';bind.mkdir();capture=tmp_path/'arguments.json';output=tmp_path/'outputs'
    recorder=bind/'python';recorder.write_text('#!/usr/bin/env python3\nimport os,json,sys\nfrom pathlib import Path\nPath(os.environ["SYNTHETIC_CAPTURE"]).write_text(json.dumps(sys.argv[1:]))\n');recorder.chmod(0o700)
    env={**os.environ,'PATH':str(bind)+os.pathsep+os.environ['PATH'],'IMAGE_TAG':image,
         'APP_ROOT':str(tmp_path/'tagged-app'),'RUNNER_TEMP':str(tmp_path),'GITHUB_OUTPUT':str(output),'SYNTHETIC_CAPTURE':str(capture)}
    # Resolve only the actual declared workflow input. Without that binding the
    # formal case must fail its expectation, as in run 45618008729.
    for key,value in step['env'].items():
        assert value=='${{ inputs.release_version }}';env[key]=release
    subprocess.run(['bash','-e','-c',step['run']],cwd=tmp_path,env=env,check=True,capture_output=True,text=True)
    args=json.loads(capture.read_text());assert args[0]=='scripts/prepare_distribution.py'
    assert ('--validate-only' in args) is validation
    assert '--upgrade' in args and args[args.index('--root')+1]==str(tmp_path/'tagged-app')
    assert output.read_text().strip()=='delivery_ready='+str(ready).lower()
