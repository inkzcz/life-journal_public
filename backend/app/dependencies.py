from datetime import datetime, timezone
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession
from .db import SessionLocal
from .models import User, Session, AdminUser
from .security import digest


def db_dep():
    with SessionLocal() as db:
        yield db


def get_settings(request: Request):
    return request.app.state.settings


def current_user(request:Request,db:DBSession=Depends(db_dep)):
    token=request.cookies.get('life_session')
    if not token: raise HTTPException(401,'请先登录')
    session=db.scalar(select(Session).where(Session.token_hash==digest(token),Session.expires_at>datetime.now(timezone.utc)))
    if not session: raise HTTPException(401,'登录已过期')
    user=db.get(User,session.user_id)
    if not user: raise HTTPException(401,'用户不存在')
    return user

def require_admin(user: User = Depends(current_user), db: DBSession = Depends(db_dep)):
    if db.get(AdminUser, user.id) is None:
        raise HTTPException(403, '需要管理员权限')
    return user


def require_dynamic_blog(user: User = Depends(require_admin), settings=Depends(get_settings)):
    """Compatibility dependency name; unified content now requires Admin only."""
    return user
