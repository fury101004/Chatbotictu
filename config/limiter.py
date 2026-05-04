# limiter.py - nhẹ, không cần Redis
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",    # dùng RAM, đủ cho < 500 user cùng lúc
    strategy="fixed-window"
)
