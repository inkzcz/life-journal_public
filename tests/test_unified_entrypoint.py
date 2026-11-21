"""Role dispatch only; actual image/health/restore gates are separate."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'backend'))
from app.unified_entrypoint import resolve,COMMANDS

@pytest.mark.parametrize('role',['web','api','maintenance'])
def test_role_runs_exactly_one_existing_service(role):
    actual,command=resolve([role],role)
    assert actual==role and command==COMMANDS[role]
    assert all(arg not in ('sh','bash','supervisord') for arg in command)
    command.append('changed')
    assert 'changed' not in COMMANDS[role]

@pytest.mark.parametrize('args,role',[
    ([],None),(['unknown'],None),(['web','extra'],None),(['web'],'api'),
    (['python','-m','app.backup'],'web'),(['api'],'maintenance'),
])
def test_invalid_or_conflicting_role_is_rejected(args,role):
    with pytest.raises(ValueError):resolve(args,role)


def test_explicit_maintenance_cli_keeps_restore_commands_without_shell_parsing():
    args=['python','-m','app.backup','verify','/backups/synthetic']
    assert resolve(args,'maintenance')==('maintenance',args)
