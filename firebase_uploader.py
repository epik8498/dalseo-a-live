import json
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, db

BASE_DIR = Path(__file__).parent
KEY_FILE = BASE_DIR / "firebase_key.json"
DATABASE_URL = "https://supersonic-l-default-rtdb.asia-southeast1.firebasedatabase.app/"

_app = None


def init_firebase():
    global _app
    if _app is None:
        cred = credentials.Certificate(str(KEY_FILE))
        _app = firebase_admin.initialize_app(cred, {
            "databaseURL": DATABASE_URL
        })
    return _app


def upload_json(path, firebase_path):
    init_firebase()

    file_path = BASE_DIR / path
    if not file_path.exists():
        print(f"Firebase 업로드 실패: 파일 없음 {file_path}")
        return

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    db.reference(firebase_path).set(data)
    print(f"Firebase 업로드 완료: {firebase_path}")
