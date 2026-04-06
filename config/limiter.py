# limiter.py - nháº¹, khĂ´ng cáº§n Redis
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",    # dĂ¹ng RAM, Ä‘á»§ cho < 500 user cĂ¹ng lĂºc
    strategy="fixed-window"
)
