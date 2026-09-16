import firebase_admin
from firebase_admin import credentials, db
from datetime import datetime

cred = credentials.Certificate("firebase_key.json")

firebase_admin.initialize_app(cred, {
    "databaseURL": "https://supersonic-l-default-rtdb.asia-southeast1.firebasedatabase.app/"
})

ref = db.reference("/test")

ref.set({
    "message": "firebase 연결 성공",
    "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
})

print("Firebase 업로드 성공")
