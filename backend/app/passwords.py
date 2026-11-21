"""Shared policy for browser setup, account updates and recovery CLI.
Length counts Unicode code points, never UTF-8 bytes. No composition rules.
"""
import unicodedata

COMMON={'password','password1','password123','12345678','123456789','1234567890',
        'qwertyui','qwerty123','abcdefgh','87654321','admin123','admin12345',
        'iloveyou','letmein123','welcome1','changeme','lifejournal',
        'qwertyuiop','asdfghjk','asdfghjkl','passw0rd','adminadmin','abcd1234',
        '1234abcd','01234567','0123456789','password1234','password12345',
        'life journal','life-journal','一二三四五六七八','生日快乐生日快乐'}

def validate_password(value):
    if not 8 <= len(value) <= 1024:
        raise ValueError('密码须为8至1024个字符')
    normalized=unicodedata.normalize('NFKC',value).casefold()
    if normalized.strip() in COMMON or len(set(normalized))<3 or not value.strip():
        raise ValueError('密码过于常见或容易猜测，请使用不常见的密码或密码短语')
    return value
