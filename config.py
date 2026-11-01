import os
import secrets
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=False)


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{(BASE_DIR / 'instance' / 'resume_ats.sqlite3').as_posix()}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", str(BASE_DIR / "uploads"))
    MAX_CONTENT_LENGTH = 6 * 1024 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
    WTF_CSRF_TIME_LIMIT = 3600
    RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID")
    RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET")
    RAZORPAY_WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET")
    RAZORPAY_MODE = os.environ.get("RAZORPAY_MODE", "test").lower()
    RESUNOVA_ADMIN_EMAIL = os.environ.get("RESUNOVA_ADMIN_EMAIL", "")
    RESUNOVA_ADMIN_PASSWORD = os.environ.get("RESUNOVA_ADMIN_PASSWORD")
    RESUNOVA_ADMIN_REGISTRATION_KEY = os.environ.get("RESUNOVA_ADMIN_REGISTRATION_KEY")
