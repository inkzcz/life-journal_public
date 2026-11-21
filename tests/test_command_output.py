import io
import subprocess
import sys
import threading
import pytest
from scripts.command_output import run_streamed


@pytest.mark.parametrize('ending', ['\n', '\r\n'])
def test_live_output_precedes_exit(ending):
    seen = threading.Event()
    class Stream(io.StringIO):
        def flush(self):
            seen.set()
    output = Stream()
    errors = []
    def run():
        try:
            run_streamed([sys.executable, '-u', '-c', "import sys,time; sys.stdout.buffer.write(" + repr(('ready'+ending).encode()) + "); sys.stdout.flush(); time.sleep(1)"], stream=output)
        except Exception as error:
            errors.append(error)
    thread = threading.Thread(target=run)
    thread.start()
    assert seen.wait(5)
    assert thread.is_alive()
    thread.join(5)
    assert not errors and output.getvalue() == 'ready\n'


def test_split_secret_stderr_and_exit_code():
    output = io.StringIO()
    code = "import sys,time; sys.stdout.write('PASSWORD=sec'); sys.stdout.flush(); time.sleep(.05); print('ret'); print('failure',file=sys.stderr); sys.exit(7)"
    with pytest.raises(subprocess.CalledProcessError) as caught:
        run_streamed([sys.executable, '-u', '-c', code], stream=output)
    assert caught.value.returncode == 7
    assert 'secret' not in output.getvalue()
    assert 'PASSWORD=[REDACTED]' in output.getvalue()
    assert 'failure' in caught.value.stderr


def test_timeout_has_sanitized_tail():
    output = io.StringIO()
    with pytest.raises(subprocess.TimeoutExpired) as caught:
        run_streamed([sys.executable, '-u', '-c', "import time; print('token=hidden'); time.sleep(30)"], timeout=.5, stream=output)
    assert 'hidden' not in caught.value.stderr
    assert '[REDACTED]' in caught.value.stderr


def test_overlong_record_is_omitted_and_tail_bounded():
    output = io.StringIO()
    with pytest.raises(subprocess.CalledProcessError) as caught:
        run_streamed([sys.executable, '-c', "print('token='+'x'*40000); print('ok\\n'*2000); raise SystemExit(2)"], stream=output)
    assert 'xxxx' not in output.getvalue()
    assert 'overlong output record omitted' in output.getvalue()
    assert len(caught.value.stderr) <= 4000


def child(code):
    return [sys.executable, '-u', '-c', code]


@pytest.mark.parametrize('size', [4001, 8000, 16384])
@pytest.mark.parametrize('ending', ['', '\n', '\r\n'])
def test_complete_normal_records_are_not_implicitly_truncated(size,ending):
    record='start '+('x'*(size-10))+' end'+ending
    output=io.StringIO()
    run_streamed(child('import sys; sys.stdout.buffer.write('+repr(record.encode())+')'),stream=output)
    assert output.getvalue()==record.replace('\r\n','\n')


def test_long_record_credentials_at_both_ends_are_removed():
    record='Password=synthetic-first '+('x'*10000)+' Authorization: token synthetic-last\r\n'
    output=io.StringIO()
    run_streamed(child('import sys; sys.stdout.buffer.write('+repr(record.encode())+')'),stream=output)
    assert output.getvalue().startswith('Password=[REDACTED] ')
    assert 'x'*10000 in output.getvalue()
    assert output.getvalue().endswith('Authorization=[REDACTED]\n')
    assert 'synthetic-first' not in output.getvalue() and 'synthetic-last' not in output.getvalue()


@pytest.mark.parametrize('newline', [False,True])
def test_overlong_credentials_wholly_omitted_and_following_record_preserved(newline):
    from scripts.command_output import OMITTED
    output=io.StringIO()
    # The command itself stays small even for the Windows CreateProcess limit.
    code="import sys; sys.stdout.buffer.write(b'Password=synthetic-first '+b'x'*65536+b' Bearer synthetic-last'"+ ("+b'\\nnext\\n'" if newline else '')+")"
    run_streamed(child(code),stream=output)
    assert output.getvalue()==OMITTED+('next\n' if newline else '')


def test_utf8_and_secrets_split_across_actual_fixed_pipe_reads():
    # 4096-byte reads split both the labelled value and a multibyte character.
    prefix=b'x'*4090+b'Token='
    record=prefix+b'synthetic-split '+('中🙂文'*600).encode()+b' end\r\n'
    output=io.StringIO()
    code="import sys,time; data="+repr(record)+"; sizes=[4096,4100,4101,len(data)]; start=0\nfor end in sizes:\n sys.stdout.buffer.write(data[start:end]);sys.stdout.flush();time.sleep(.03);start=end"
    run_streamed(child(code),stream=output)
    assert output.getvalue()=='x'*4090+'Token=[REDACTED] '+('中🙂文'*600)+' end\n'


def test_continuous_unterminated_output_is_bounded_and_times_out():
    import time,tracemalloc
    from scripts.command_output import OMITTED
    output=io.StringIO()
    code="import sys\nwhile True: sys.stdout.buffer.write(b'x'*4096);sys.stdout.flush()"
    tracemalloc.start()
    started=time.monotonic()
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            run_streamed(child(code),timeout=1,stream=output)
        peak=tracemalloc.get_traced_memory()[1]
    finally:tracemalloc.stop()
    assert time.monotonic()-started<10
    assert output.getvalue()==OMITTED
    assert peak<2*1024*1024
    assert not any(t.name=='life-journal-output-reader' for t in threading.enumerate())


def test_error_summary_and_exception_command_never_contain_raw_credentials():
    from scripts.command_errors import SUMMARY_LIMIT
    output=io.StringIO()
    command=child("import sys; print('Password=synthetic-tail'); print('x'*12000); sys.exit(23)")
    command+=['Authorization=synthetic-command']
    with pytest.raises(subprocess.CalledProcessError) as caught:
        run_streamed(command,stream=output)
    assert caught.value.returncode==23
    assert len(caught.value.stderr)<=SUMMARY_LIMIT
    assert 'synthetic-command' not in str(caught.value) and 'synthetic-command' not in repr(caught.value.cmd)
    assert 'synthetic-tail' not in caught.value.stderr


@pytest.mark.parametrize('parent_exits', [False,True])
def test_timeout_terminates_tree_and_reader_even_after_parent_exit(tmp_path,parent_exits):
    import os,time
    pidfile=tmp_path/'child.pid'
    child_code="import os,time; from pathlib import Path; Path("+repr(str(pidfile))+").write_text(str(os.getpid()));time.sleep(30)"
    code="import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-u','-c',"+repr(child_code)+"]); print('parent-ready',flush=True); "+('time.sleep(.2)' if parent_exits else 'time.sleep(30)')
    output=io.StringIO()
    with pytest.raises(subprocess.TimeoutExpired):
        run_streamed(child(code),timeout=2,stream=output)
    assert pidfile.exists()
    pid=int(pidfile.read_text())
    def alive():
        if os.name=='nt':
            import ctypes
            from ctypes import wintypes as w
            api=ctypes.WinDLL('kernel32',use_last_error=True)
            api.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];api.OpenProcess.restype=w.HANDLE
            api.GetExitCodeProcess.argtypes=[w.HANDLE,ctypes.POINTER(w.DWORD)]
            api.CloseHandle.argtypes=[w.HANDLE]
            handle=api.OpenProcess(0x1000,False,pid)
            if not handle:return False
            try:
                status=w.DWORD();assert api.GetExitCodeProcess(handle,ctypes.byref(status));return status.value==259
            finally:api.CloseHandle(handle)
        try:
            os.kill(pid,0)
            # An orphan reaped asynchronously by init can briefly be a zombie.
            from pathlib import Path
            return Path('/proc/'+str(pid)+'/stat').read_text().split(') ')[1][0]!='Z'
        except (ProcessLookupError,FileNotFoundError):return False
    deadline=time.monotonic()+5
    while alive() and time.monotonic()<deadline:time.sleep(.02)
    assert not alive()
    assert not any(t.name=='life-journal-output-reader' for t in threading.enumerate())


def test_broken_output_sink_stops_child_without_raw_exception_message():
    class Broken:
        def write(self,value):raise OSError('Password=synthetic-sink-secret')
        def flush(self):pass
    with pytest.raises(RuntimeError) as caught:
        run_streamed(child("import time; print('hello',flush=True);time.sleep(30)"),timeout=2,stream=Broken())
    assert 'synthetic-sink-secret' not in str(caught.value)
    assert not any(t.name=='life-journal-output-reader' for t in threading.enumerate())


def test_pipe_read_failure_stops_process_and_does_not_expose_exception(monkeypatch):
    from scripts import command_output
    def reader(pipe):
        def fail():raise OSError('token=synthetic-pipe-secret')
        return fail
    monkeypatch.setattr(command_output,'_available_reader',reader)
    with pytest.raises(RuntimeError) as caught:
        run_streamed(child('import time;time.sleep(30)'),timeout=2,stream=io.StringIO())
    assert 'synthetic-pipe-secret' not in str(caught.value)
    assert not any(t.name=='life-journal-output-reader' for t in threading.enumerate())


def test_start_failure_has_safe_type_and_no_raw_exception_context(monkeypatch):
    from scripts import command_output
    def fail(*args,**kwargs):raise OSError(2,'token=synthetic-start-secret')
    monkeypatch.setattr(command_output.subprocess,'Popen',fail)
    with pytest.raises(RuntimeError) as caught:
        run_streamed(['synthetic-command','password=synthetic-argument'],stream=io.StringIO())
    assert 'errno=2' in str(caught.value)
    assert 'synthetic-start-secret' not in str(caught.value)
    assert caught.value.__context__ is None


def test_long_escaped_credential_is_redacted_before_live_output_and_summary():
    output=io.StringIO()
    record = 'Password="synthetic '+('x'*8000)+r' \" quoted tail"'+'\n'
    code="import sys; sys.stdout.buffer.write("+repr(record.encode())+");sys.exit(3)"
    with pytest.raises(subprocess.CalledProcessError) as caught:
        run_streamed(child(code),stream=output)
    assert output.getvalue()=='Password=[REDACTED]\n'
    assert 'synthetic' not in caught.value.stderr and 'quoted tail' not in caught.value.stderr


@pytest.mark.parametrize('character', ['中','🙂'])
@pytest.mark.parametrize('size', [8000,16384])
def test_multibyte_normal_character_limit_is_not_a_byte_limit(character,size):
    output=io.StringIO()
    code="import sys;sys.stdout.buffer.write(("+repr(character)+"*"+str(size)+"+'\\r\\n').encode())"
    run_streamed(child(code),stream=output)
    assert output.getvalue()==character*size+'\n'


def test_record_over_character_limit_is_wholly_omitted_before_redaction():
    from scripts.command_output import OMITTED
    output=io.StringIO()
    run_streamed(child("import sys;sys.stdout.buffer.write(('x'*16385).encode())"),stream=output)
    assert output.getvalue()==OMITTED
