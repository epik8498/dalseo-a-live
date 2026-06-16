from firebase_uploader import init_firebase
from firebase_admin import db

init_firebase()

NUMBER_TEAM_RIDERS = [
    "한창목", "구민성", "석윤미", "조영웅", "류창우",
    "이경은", "이경림", "김광미", "정용운", "지덕곤",
    "김우중", "김시곤", "천재원", "조정래", "이금형",
    "최종용", "최문호", "이정미", "염용범", "김성주",
    "이창원", "채기후", "손성기", "박진수", "김병찬",
    "지덕근", "최중용",
]

team_map = {name: "넘버팀" for name in NUMBER_TEAM_RIDERS}

db.reference("/settings/junggua/teamMap").update(team_map)

print("중구A teamMap 업로드 완료")
print(f"업로드 기사 수: {len(team_map)}명")
