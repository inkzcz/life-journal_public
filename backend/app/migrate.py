"""Explicit CLI: python -m app.migrate preflight|check|upgrade. Never logs connection URLs."""
import argparse
from .db import engine
from .migrations import upgrade, require_current_schema, preflight


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['preflight', 'check', 'upgrade'])
    args = parser.parse_args()
    if args.action == 'preflight':
        state = preflight(engine)
        print(f'只读结构预检通过：{state}。')
        return
    if args.action == 'upgrade':
        upgrade(engine)
    require_current_schema(engine)
    print('数据库版本检查通过。')


if __name__ == '__main__':
    main()
