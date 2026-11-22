import os
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

_key = os.getenv("ENCRYPTION_KEY")
if not _key:
    raise RuntimeError("ENCRYPTION_KEY is missing in .env")

cipher = Fernet(_key.encode("utf-8"))

def encrypt_text(plain_text: str) -> str:
    return cipher.encrypt(plain_text.encode("utf-8")).decode("utf-8")

def decrypt_text(token: str) -> str:
    return cipher.decrypt(token.encode("utf-8")).decode("utf-8")