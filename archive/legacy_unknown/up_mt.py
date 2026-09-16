from firebase_uploader import init_firebase
from firebase_admin import db

init_firebase()

MAEUM3_TEAM_RIDERS = [
    "김리현", "김민웅", "김원제", "김익한", "김재준",
    "남현우", "문재훈", "박명규", "박정현", "성동훈",
    "오세원", "윤종홍", "이우훈", "이정석", "이정호",
    "전재욱", "정은경", "정장훈", "정재균", "최영섭",
    "최종광", "최홍석", "추진태", "함영국", "현승희",
    "전재옥", "김래현", "김제헌", "이낙철",
]

team_map = {}

for name in MAEUM3_TEAM_RIDERS:
    team_map[name] = "마음3"

db.reference("/settings/maeuma/teamMap").set(team_map)

print("마음 달서A teamMap 업로드 완료")
print(f"업로드 기사 수: {len(team_map)}명")
