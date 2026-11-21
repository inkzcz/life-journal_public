"""Local operator-only Admin grants. No web API can promote its own user."""
import argparse
from sqlalchemy import select
from .db import engine, SessionLocal
from .migrations import require_current_schema
from .models import User, AdminUser


def grant_admin(username):
    require_current_schema(engine)
    with SessionLocal.begin() as db:
        # Serialize repeated grants for this user without rewriting credentials.
        user = db.scalar(select(User).where(User.username == username).with_for_update())
        if user is None:
            raise ValueError('用户不存在；没有修改任何密码或数据')
        if db.get(AdminUser, user.id) is None:
            db.add(AdminUser(user_id=user.id))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['grant'])
    parser.add_argument('username')
    args = parser.parse_args()
    grant_admin(args.username)
    print('管理员授权已确认。')


if __name__ == '__main__':
    main()
