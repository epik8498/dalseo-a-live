from firebase_uploader import init_firebase
from firebase_admin import db

init_firebase()

dalseo_team_riders = [
    '김민승', '윤창근', '김병국', '신호준', '김영빈',
    '김용우', '박지원', '김탁기', '김병철', '정영훈',
    '김태광', '배재현', '김형민', '문승수', '이상민',
    '정성훈', '이주철', '박기홍', '정판호', '나미영',
    '황호용', '김영철', '남승훈', '남수현', '김민서',
    '신진관', '임선미', '여재환', '정주현', '김기현',
    '김범준', '이윤석', '양혜진', '김민우', '김혜성',
    '김기헌', '조대영', '정승덕', '임상완', '김우진',
    '신민규', '김진현', '김재석', '서창민',
]

team_map = {name: "달서팀" for name in dalseo_team_riders}

db.reference("/settings/dalseoa/teamMap").set(team_map)

print("달서A teamMap 업로드 완료")
print(f"업로드 기사 수: {len(team_map)}명")
