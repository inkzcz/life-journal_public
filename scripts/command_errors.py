"""Bounded, redacted command failures without exposing arguments or local configuration."""
import re
import subprocess


SUMMARY_LIMIT=4000
KNOWN_COMMAND_WORDS={'docker','git','gh','buildx','build','image','inspect','save','load','info','context','show','version','ls','rev-parse','status','diff','fetch','api'}
# Escaped quotes are part of a value. If quotes are malformed, hide the rest
# of that logical record instead of exposing a credential suffix.
_VALUE = r'''(?:"(?:\\.|[^"\\\r\n])*"|'(?:\\.|[^'\\\r\n])*'|["'][^\r\n]*|[^\s,;]+)'''


def redact(value):
    """Sanitize known credential forms; no truncation. Call only on bounded input.

    This is not a universal secret detector: unknown formats, arbitrary binary
    data and credentials split across logical records are outside its contract.
    """
    value=str(value or '')
    value=re.sub(r'(?i)\b(Bearer|Basic|Token)\s+[^\s]+',r'\1 [REDACTED]',value)
    value=re.sub(r'(?i)([a-z][a-z0-9+.-]*://)[^\s/@]+:[^\s/@]+@',r'\1[REDACTED]@',value)
    value=re.sub(r'(?i)\b([\w-]*(?:password|passwd|token|secret|auth|authorization|setup_key|credential|api[_-]?key)[\w-]*)\b[\"\']?\s*[:=]\s*'+_VALUE,r'\1=[REDACTED]',value)
    value=re.sub(r'(?i)(--(?:password|token|secret|credential|api-key)\s+)'+_VALUE,r'\1[REDACTED]',value)
    value=re.sub(r'(?i)(\b(?:Authorization|Proxy-Authorization)\s*[:=]\s*)[^\r\n]+',r'\1[REDACTED]',value)
    value=re.sub(r'\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)\b','[REDACTED]',value)
    value=re.sub(r'[\x00-\x08\x0b-\x1f\x7f]','?',value)
    return value


def summarize(value, limit=SUMMARY_LIMIT):
    """Redact before slicing: never retain a raw credential's truncated suffix."""
    if isinstance(value,bytes):value=value.decode('utf-8','replace')
    if limit<0:raise ValueError('Diagnostic limit cannot be negative')
    safe=redact(value)
    if len(safe)>limit:
        marker='[earlier diagnostic output omitted]\n'[:limit]
        remaining=limit-len(marker)
        return marker+(safe[-remaining:] if remaining else '')
    return safe


def safe_command(command):
    """Exceptions retain command type, never arbitrary arguments or secrets."""
    if isinstance(command,str):command=command.split()
    return [str(word) if word in KNOWN_COMMAND_WORDS else '[argument omitted]'
            for word in list(command)[:4]]


def describe(error, *, limit=SUMMARY_LIMIT):
    if not isinstance(error,subprocess.SubprocessError):
        if error.__cause__ is not None and isinstance(error.__cause__,subprocess.SubprocessError):
            context=summarize(str(error),min(500,limit//4))+'; '
            return context+describe(error.__cause__,limit=limit-len(context))
        return summarize(str(error),limit)
    args=safe_command(getattr(error,'cmd',()))
    kind=' '.join(a for a in args if a in KNOWN_COMMAND_WORDS) or 'subprocess'
    step=next((word for word in ('build','save','load','inspect','info','fetch','status') if word in args),'command')
    code=getattr(error,'returncode','timeout' if isinstance(error,subprocess.TimeoutExpired) else 'unknown')
    detail=getattr(error,'stderr',None) or getattr(error,'output',None) or 'No captured error output; inspect the preceding command log.'
    prefix=f'step={step}; command={kind}; exit_code={code}; error='
    return prefix+summarize(detail, limit-len(prefix))
