import subprocess
from scripts.command_errors import describe


def test_command_failure_preserves_step_exit_and_redacts_secrets():
    error=subprocess.CalledProcessError(23,['docker','save','-o','private/path'],stderr='failed token=abc password="hello world" postgresql://user:pass@host/db Authorization: Bearer abcdef')
    message=describe(error)
    assert 'step=save' in message and 'command=docker save' in message and 'exit_code=23' in message and 'failed' in message
    for secret in ['abc','hello world','user:pass','abcdef','private/path']:assert secret not in message


def test_inspection_failure_retains_its_underlying_exit_code():
    try:
        try:raise subprocess.CalledProcessError(7,['docker','image','inspect','private'],stderr='daemon unavailable')
        except subprocess.CalledProcessError as cause:raise RuntimeError('Cannot assume tag absent') from cause
    except RuntimeError as error:message=describe(error)
    assert 'exit_code=7' in message and 'daemon unavailable' in message


def test_git_source_failure_keeps_captured_stderr_for_redacted_cli_diagnostics(tmp_path,monkeypatch):
    from scripts import source_identity
    (tmp_path/'.git').mkdir()
    def fail(args,**kwargs):
        assert kwargs['capture_output'] is True and kwargs['check'] is True
        raise subprocess.CalledProcessError(128,args,stderr='fatal: repository unavailable token=private-token')
    monkeypatch.setattr(source_identity.subprocess,'run',fail)
    try:source_identity.identify(tmp_path)
    except subprocess.CalledProcessError as error:message=describe(error)
    assert 'exit_code=128' in message and 'fatal: repository unavailable' in message
    assert 'private-token' not in message


def test_common_prefixed_secret_keys_and_basic_authorization_are_redacted():
    from scripts.command_errors import redact
    for raw,secret in [('Authorization: Basic YWJjOnNlY3JldA==','YWJjOnNlY3JldA=='),('GH_TOKEN=opaque-private-value','opaque-private-value'),('PGPASSWORD=database-private-value','database-private-value'),('"client_secret": "quoted private value"','quoted private value')]:
        assert secret not in redact(raw)


def test_cli_translation_keeps_native_step_command_and_exit_code(monkeypatch,capsys):
    from scripts import release_local
    def fail(*args,**kwargs):
        raise subprocess.CalledProcessError(42,['docker','buildx','build'],stderr='builder does not support linux/amd64 token=private-value')
    monkeypatch.setattr(release_local,'deliver',fail)
    assert release_local.main(['--version','v5.1.7','--output-dir','/synthetic-no-output'])==1
    message=capsys.readouterr().err
    assert 'step=build' in message and 'command=docker buildx build' in message and 'exit_code=42' in message
    assert 'private-value' not in message


def test_redaction_does_not_truncate_live_records_but_summary_is_bounded():
    from scripts.command_errors import redact, summarize, SUMMARY_LIMIT
    record='first '+('x'*12000)+' last password=synthetic-secret'
    safe=redact(record)
    assert safe.startswith('first ') and len(safe)>12000
    assert 'synthetic-secret' not in safe
    assert len(summarize(record))<=SUMMARY_LIMIT
    assert 'omitted' in summarize(record)
    error=subprocess.CalledProcessError(9,['docker','buildx','build','token=synthetic-argument'],stderr=record)
    message=describe(error)
    assert message.startswith('step=build; command=docker buildx build; exit_code=9;')
    assert len(message)<=SUMMARY_LIMIT and 'synthetic-secret' not in message


def test_known_authentication_forms_are_synthetic_and_redacted():
    from scripts.command_errors import redact
    cases=[('auth=synthetic-docker-auth','synthetic-docker-auth'),
           ('Token synthetic-header','synthetic-header'),
           ('docker login --password synthetic-cli-password','synthetic-cli-password'),
           ('Bearer synthetic-bearer','synthetic-bearer'),
           ('Basic c3ludGhldGljOm9ubHk=','c3ludGhldGljOm9ubHk='),
           ('Token: synthetic-token','synthetic-token'),
           ('Password="synthetic password"','synthetic password'),
           ('Authorization: token synthetic-authorization','synthetic-authorization'),
           ('Proxy-Authorization: Negotiate synthetic-proxy','synthetic-proxy'),
           ('https://synthetic-user:synthetic-pass@example.invalid/repo','synthetic-pass'),
           ('ghp_synthetic0123456789','ghp_synthetic0123456789'),
           ('github_pat_synthetic0123456789','github_pat_synthetic0123456789')]
    for record, secret in cases:
        assert secret not in redact(record)


def test_unknown_secret_format_is_explicitly_outside_redactor_contract():
    from scripts.command_errors import redact
    assert redact('unlabelled synthetic opaque value')=='unlabelled synthetic opaque value'


def test_escaped_or_unclosed_quoted_credentials_do_not_expose_suffixes():
    from scripts.command_errors import redact
    records=[r'Password="synthetic \" quoted tail"',
             r"token='synthetic \' quoted tail'",
             'Password="synthetic quoted tail',
             r'--password "synthetic \" quoted tail"']
    for record in records:
        safe=redact(record)
        for fragment in ('synthetic','quoted','tail'):
            assert fragment not in safe


def test_bounded_chained_error_preserves_underlying_command_metadata():
    cause=subprocess.CalledProcessError(17,['docker','image','inspect','synthetic'],stderr='x'*12000+' Password=synthetic-last')
    error=RuntimeError('cannot assume tag absent')
    error.__cause__=cause
    message=describe(error)
    assert len(message)<=4000
    assert 'step=inspect' in message and 'exit_code=17' in message
    assert 'synthetic-last' not in message


def test_small_summary_budgets_are_honored():
    from scripts.command_errors import summarize
    for limit in (0,1,20,100,4000):
        assert len(summarize('x'*12000,limit))<=limit
