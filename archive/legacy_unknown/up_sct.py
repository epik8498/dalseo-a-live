from firebase_uploader import init_firebase
from firebase_admin import db

init_firebase()

BDMJ_TEAM_RIDERS = [
    "정병준", "정을갑", "석정균", "황재상", "정철민",
    "홍찬윤", "임미영", "강상기", "오명준", "김용철",
    "이동수", "김근식", "이태원", "신정현", "정성원",
    "강현기", "김기억", "김경훈", "김영철", "신순미",
    "송윤미", "이승재", "김도식", "이슬기", "손영빈",
    "이상구", "강석진", "김성우", "조정민", "장재근",
    "이재정", "오세현", "송한솔", "황호진", "손효상",
    "천기준", "김형민", "박민욱", "강성모", "김초혜",
    "정인기", "김준상", "김경환", "이현동", "김동현",
    "김효용", "오세출", "정병철", "손자수", "한용규",
    "장대식", "김민찬", "오강식", "이준원", "이상철",
    "이상운", "이동협", "우상수", "송정자", "박준민",
    "김진흥", "김우주", "김상훈", "김복룡", "김명현",
    "김명일", "강철구",
]

team_map = {}

for name in BDMJ_TEAM_RIDERS:
    team_map[name] = "BDMJ팀"

db.reference("/settings/suseongc/teamMap").update(team_map)

print("수성C teamMap 업로드 완료")
print(f"업로드 기사 수: {len(team_map)}명")
