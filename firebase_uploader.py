import json
import os
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, db

BASE_DIR = Path(__file__).parent

SECRETS_DIR = Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "SUPERSONIC" / "secrets"
PROD_KEY_FILE = SECRETS_DIR / "firebase_key.json"
PROD_DATABASE_URL = "https://supersonic-l-default-rtdb.asia-southeast1.firebasedatabase.app/"

DEV_KEY_FILE = BASE_DIR / "firebase_key_dev.json"
DEV_DATABASE_URL = os.getenv("SUPERSONIC_DEV_FIREBASE_URL", "").strip()

_app = None
_app_environment = None


def init_firebase(environment="PROD"):
    global _app, _app_environment

    env = str(environment or "PROD").strip().upper()
    if env not in {"PROD", "DEV"}:
        raise RuntimeError(f"지원하지 않는 Firebase 환경입니다: {env}")

    if env == "PROD":
        key_file = PROD_KEY_FILE
        database_url = PROD_DATABASE_URL
    else:
        if os.getenv("SUPERSONIC_DEV_FIREBASE", "").strip() != "1":
            raise RuntimeError("DEV_FIREBASE_DISABLED")
        if not DEV_DATABASE_URL:
            raise RuntimeError("DEV_FIREBASE_URL_MISSING")
        if not DEV_KEY_FILE.exists():
            raise RuntimeError(f"DEV_FIREBASE_KEY_MISSING: {DEV_KEY_FILE}")
        key_file = DEV_KEY_FILE
        database_url = DEV_DATABASE_URL

    if _app is not None:
        if _app_environment != env:
            raise RuntimeError("FIREBASE_ENVIRONMENT_MISMATCH")
        return _app

    if not key_file.exists():
        raise RuntimeError(f"FIREBASE_KEY_MISSING: {key_file}")

    cred = credentials.Certificate(str(key_file))
    _app = firebase_admin.initialize_app(cred, {"databaseURL": database_url})
    _app_environment = env
    return _app


def upload_json(path, firebase_path, environment="PROD"):
    init_firebase(environment=environment)

    file_path = BASE_DIR / path
    if not file_path.exists():
        print(f"Firebase 업로드 실패: 파일 없음 {file_path}")
        return

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    db.reference(firebase_path).set(data)
    print(f"Firebase 업로드 완료: {firebase_path}")
