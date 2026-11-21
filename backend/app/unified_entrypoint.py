"""One image, exactly one service process. Reuse existing safe privilege drop.

Custom one-off CLI commands require an explicit api/maintenance role, preserving
backup/restore operations. No shell evaluation or multi-process supervisor.
"""
import os
import sys
from . import container_entrypoint

COMMANDS={
    'web':['caddy','run','--config','/etc/caddy/Caddyfile','--adapter','caddyfile'],
    'api':['uvicorn','app.main:app','--host','0.0.0.0','--port','8000','--proxy-headers','--forwarded-allow-ips','*','--no-access-log'],
    'maintenance':['python','-m','app.maintenance_worker'],
}


def resolve(args,configured=None):
    if not args:raise ValueError('缺少业务角色或显式维护命令')
    if args[0] in COMMANDS:
        if len(args)!=1:raise ValueError('业务角色不接受额外启动参数；独立维护命令请显式配置CONTAINER_ROLE')
        role=args[0]
        if configured and configured!=role:raise ValueError('启动角色与CONTAINER_ROLE冲突，拒绝启动')
        return role,list(COMMANDS[role])
    if configured not in ('api','maintenance'):raise ValueError('独立命令必须指定api或maintenance角色，Web禁止执行维护命令')
    return configured,list(args)


def main():
    try:role,command=resolve(sys.argv[1:],os.environ.get('CONTAINER_ROLE'))
    except ValueError as exc:raise SystemExit(str(exc)) from None
    os.environ['CONTAINER_ROLE']=role
    sys.argv=[sys.argv[0],*command]
    container_entrypoint.main()


if __name__=='__main__':main()
