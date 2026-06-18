from firebase_uploader import init_firebase
from firebase_admin import db

init_firebase()

NUMBER_TEAM_RIDERS = [
    "한창목",
    "석윤미",
    "조영웅",
    "류창우",
    "이경은",
    "이경림",
    "김광미",
    "지덕곤",
    "김시곤",
    "천재원",
    "조정래",
    "이금형",
    "최종용",
    "최문호",
    "이정미",
    "염용범",
    "김성주",
    "이창원",
    "채기후",
    "손성기",
    "박진수",
    "김병찬",
    "최중용",
]

MAEUM_TEAM_RIDERS = [
    "김태현",
    "김정현",
    "이승용",
    "김우중",
    "김태우",
    "정용운",
    "양창훈",
    "정지욱",
    "지덕근",
    "차순석",
    "구민성",
]

team_map = {}

for name in NUMBER_TEAM_RIDERS:
    team_map[name] = "넘버팀"

for name in MAEUM_TEAM_RIDERS:
    team_map[name] = "마음팀"

db.reference("/settings/junggua/teamMap").set(team_map)

print("중구A teamMap 업로드 완료")
print(f"넘버팀: {len(NUMBER_TEAM_RIDERS)}명")
print(f"마음팀: {len(MAEUM_TEAM_RIDERS)}명")
print(f"총 업로드: {len(team_map)}명")
