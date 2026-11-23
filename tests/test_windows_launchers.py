"""Native Windows entrypoint checks; no Docker, private config or real data."""
import base64
import os
from pathlib import Path
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]
pytestmark=pytest.mark.skipif(os.name!='nt',reason='Native Windows launcher acceptance runs in the windows-toolchain CI job')


def powershell(code):
    encoded=base64.b64encode(code.encode('utf-16-le')).decode('ascii')
    return subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',encoded],
        input='\n',capture_output=True,text=True,errors='replace',timeout=45)


def test_native_powershell_parser_accepts_launcher_without_executing_it():
    script=str(ROOT/'scripts/release-local.ps1').replace("'","''")
    result=powershell("$tokens=$null; $errors=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('"+script+"',[ref]$tokens,[ref]$errors); if ($errors.Count -gt 0) { exit 1 }; exit 0")
    assert result.returncode==0,result.stderr


@pytest.mark.parametrize('entry',['cmd','powershell'])
def test_windows_entrypoint_preserves_failure_exit_before_any_docker_access(entry):
    # An impossible product version is rejected before Git/network/Docker. Run
    # the actual entrypoints with their real Python launcher and child exit.
    if entry=='cmd':
        result=subprocess.run(['cmd.exe','/d','/c',str(ROOT/'scripts/release-local.cmd'),'-Version','v0.0.0'],
            input='\n',capture_output=True,text=True,errors='replace',timeout=45)
    else:
        path=str(ROOT/'scripts/release-local.ps1').replace("'","''")
        result=powershell("& '"+path+"' -Version 'v0.0.0'; exit $LASTEXITCODE")
    assert result.returncode==1,(result.returncode,result.stdout,result.stderr)
