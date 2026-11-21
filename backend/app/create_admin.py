import getpass
from argon2 import PasswordHasher
from sqlalchemy import select
from .db import SessionLocal, engine
from .migrations import require_current_schema
from .models import User, AdminUser
from .passwords import validate_password

def main():
    require_current_schema(engine)
    from .services.write_barrier import writer
    with writer(engine), SessionLocal() as db:
        if engine.dialect.name=='postgresql':
            from sqlalchemy import text
            db.execute(text('SELECT pg_advisory_xact_lock(721934012)'))
        if db.scalar(select(User.id).limit(1)) is not None:
            raise SystemExit('管理员已存在。为避免意外覆盖，初始化操作已停止。')
        username=input('管理员用户名: ').strip()
        password=getpass.getpass('管理员密码（至少8字符）: ')
        if not 1 <= len(username) <= 100:
            raise SystemExit('用户名须为1至100字符。')
        try:validate_password(password)
        except ValueError as exc:raise SystemExit(str(exc)) from None
        user=User(username=username,password_hash=PasswordHasher().hash(password))
        db.add(user);db.flush()
        db.add(AdminUser(user_id=user.id))
        db.commit()
    print('管理员已创建。')
if __name__=='__main__':main()
