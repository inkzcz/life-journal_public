import hashlib
from collections import deque
from threading import Lock
from time import monotonic
from argon2 import PasswordHasher

ph=PasswordHasher()
# A single-admin deployment uses one Uvicorn process. Bound total password
# verification work rather than trusting potentially spoofed proxy IP headers.
login_attempts = deque()
login_lock = Lock()

def allow_login():
    now = monotonic()
    with login_lock:
        while login_attempts and login_attempts[0] <= now - 60:
            login_attempts.popleft()
        if len(login_attempts) >= 10:
            return False
        login_attempts.append(now)
        return True

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def cookie(response, name, value, max_age, httponly, secure):
    response.set_cookie(name,value,max_age=max_age,httponly=httponly,
                        secure=secure,samesite='strict',path='/')
