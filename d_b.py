import json
import math
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import pyperclip
from playwright.sync_api import sync_playwright

AUTO_GIT_PUSH = True
REFRESH_SECONDS = 60
MAX_PAGES = 20
TARGET_ACCEPT_RATE = 98

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data_dalseob.json"
HTML_FILE = BASE_DIR / "index.html"
WEEKLY_FILE = BASE_DIR / "weekly.json"

AREA_NAME = "달서B"

SONIC_TEAM_RIDERS = [
    "최경민", "윤규범", "신성욱", "박무성", "송득근", "정우혁", "김경섭", "장근영", "조윤환", "조승래",
    "정기정", "정규태", "장재근", "최지나", "이종필", "이정민", "이재상", "이재관", "윤철훈", "유영멸",
    "엄정철", "심재득", "신진학", "배준호", "박정민", "김주동", "김재현", "김상엽", "김동규", "권휘재",
    "최지용", "김종차", "이상엽",
]

NUMBER_TEAM_RIDERS = [
    "유호성", "박세창", "강명원", "김수진", "배서후", "김요한", "김정근", "남승호", "이현재", "이윤재",
    "정수영", "장정석", "최영진", "임현석", "임승범", "이태훈", "이철우", "이재현", "이은성", "이영희",
    "이선노", "이동석", "우효상", "서강원", "한동훈", "마경민", "노재권", "남윤정", "남동욱", "김현준",
    "김태하", "김종희", "김용운", "김영천", "김명수", "김명한", "김동국", "권오현", "황홍섭", "강지은",
    "최윤호", "신명섭", "윤민석", "김애선", "이대경", "김대운",
]

MAEUM_TEAM_RIDERS = [
    "박성우", "임용우", "김강호", "김영우", "강지우", "이승훈", "박성림", "이영민", "손성곤", "구상훈",
    "박한울", "신가희", "박연호", "김형택", "김낙훈", "권영남", "이진복", "김석원", "길태빈", "김창범",
    "박광용", "성영길", "박원희", "최영우", "이전필", "이재현", "이강현", "김대한", "여세동", "신정하",
    "임지훈", "장민서", "임종현", "윤동근", "도수현", "김동현", "정동진", "정동수", "전한", "전하경",
    "전승욱", "전대명", "장예환", "장대웅", "임재백", "이진욱", "이진승", "최현준", "이승준", "이경태",
    "최현주", "안호식", "신원순", "서봉용", "박호일", "도인환", "노지훈", "김현진", "김지성", "김재훈",
    "황유경", "김성현", "김서현", "문영신", "곽봉수", "장민규", "김효겸", "송인섭", "김종서", "김종호",
    "남재화", "박남아", "구용태", "한대성", "윤정원", "손지수", "김숙자", "김현숙", "최종현", "김인수",
    "김일식", "신인호", "구자돈", "차무길", "차성원", "박지홍", "이예준", "위석훈", "피우덕", "소귀숙",
    "피우정", "백창열", "하태수", "명재규", "한희숙", "김동욱", "김도형",
]

TEAM_ORDER = ["소닉팀", "넘버팀", "마음팀"]

AREA_CONFIG = {
    "달서B": {
        "소닉팀": 2,
        "넘버팀": 5.5,
        "마음팀": 5.5,
    }
}

DAY_TARGETS = {
    0: [21, 20, 30, 29],
    1: [21, 20, 30, 29],
    2: [21, 20, 30, 29],
    3: [21, 20, 30, 29],
    4: [24, 21, 32, 33],
    5: [31, 22, 36, 31],
    6: [33, 22, 35, 30],
}

PERIODS = ["morning", "afternoon", "evening", "midnight"]
PERIOD_LABELS = {
    "morning": "오전피크",
    "afternoon": "오후논피크",
    "evening": "저녁피크",
    "midnight": "심야논피크",
}


def business_date(now):
    if now.hour < 6:
        return (now - timedelta(days=1)).date()
    return now.date()


def current_period(now):
    h = now.hour
    weekend = now.weekday() >= 5

    if weekend:
        if 6 <= h <= 13:
            return "morning"
        if 14 <= h <= 16:
            return "afternoon"
    else:
        if 6 <= h <= 12:
            return "morning"
        if 13 <= h <= 16:
            return "afternoon"

    if 17 <= h <= 19:
        return "evening"

    return "midnight"


def calc_accept_rate(complete, reject):
    total = complete + reject
    if total == 0:
        return 100
    return round((complete / total) * 100, 1)


def spare_rejects(complete, reject):
    if complete <= 0:
        return -reject
    max_reject = math.floor(complete * (100 - TARGET_ACCEPT_RATE) / TARGET_ACCEPT_RATE)
    return max_reject - reject


def team_of(name):
    if name in NUMBER_TEAM_RIDERS:
        return "넘버팀"
    if name in MAEUM_TEAM_RIDERS:
        return "마음팀"
    return "소닉팀"


def to_int(value):
    try:
        return int(str(value).replace(",", "").strip())
    except Exception:
        return 0


def set_page_number(url, page_no):
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    qs["page"] = [str(page_no)]
    qs["size"] = ["100"]
    qs.setdefault("orderName", ["name"])
    qs.setdefault("orderBy", ["asc"])
    qs.setdefault("name", [""])
    qs.setdefault("userId", [""])
    qs.setdefault("phoneNumber", [""])
    qs.setdefault("riderStatus", [""])
    new_query = urlencode(qs, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def parse_clipboard_text(text):
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    riders = []

    i = 0
    while i < len(lines):
        name = lines[i]

        if i + 35 >= len(lines):
            i += 1
            continue

        status = "미접속"

        if lines[i + 1].startswith("010-"):
            phone_idx = i + 1
        else:
            status = lines[i + 1]
            phone_idx = i + 2

        phone = lines[phone_idx]

        if not phone.startswith("010-"):
            i += 1
            continue

        complete = to_int(lines[phone_idx + 1])
        reject = to_int(lines[phone_idx + 2])
        cancel = to_int(lines[phone_idx + 3])
        rider_fault = to_int(lines[phone_idx + 4])

        morning = to_int(lines[phone_idx + 5])
        afternoon = to_int(lines[phone_idx + 6])
        evening = to_int(lines[phone_idx + 7])
        midnight = to_int(lines[phone_idx + 8])

        hourly = []
        for h in range(24):
            hourly.append(to_int(lines[phone_idx + 9 + h]))

        user_id = lines[phone_idx + 33]

        is_online = status in ["운행중", "운행 중", "온라인", "접속중"]

        riders.append({
            "name": name,
            "phone": phone,
            "userId": user_id,
            "team": team_of(name),
            "status": status,
            "isOnline": is_online,
            "complete": complete,
            "reject": reject,
            "cancel": cancel,
            "riderFault": rider_fault,
            "morning": morning,
            "afternoon": afternoon,
            "evening": evening,
            "midnight": midnight,
            "hourly": hourly,
            "acceptRate": calc_accept_rate(complete, reject),
            "warning": calc_accept_rate(complete, reject) < 80,
        })

        i = phone_idx + 34

    return riders


def copy_current_page_text(page):
    page.click("body")
    page.keyboard.press("Control+A")
    time.sleep(0.2)
    page.keyboard.press("Control+C")
    time.sleep(0.5)
    return pyperclip.paste()


def collect_all_pages_by_copy(page):
    base_url = page.url
    all_riders = []
    seen = set()

    for page_no in range(MAX_PAGES):
        target_url = set_page_number(base_url, page_no)
        print(f"{page_no + 1}페이지 이동: {target_url}")

        page.goto(target_url)
        page.wait_for_load_state("networkidle")
        time.sleep(1.5)

        text = copy_current_page_text(page)
        riders = parse_clipboard_text(text)

        print(f"{page_no + 1}페이지 읽은 기사 수: {len(riders)}")

        if len(riders) == 0:
            print("빈 페이지라서 수집 종료")
            break

        new_count = 0
        for r in riders:
            key = r["name"] + "_" + r["phone"]
            if key not in seen:
                seen.add(key)
                all_riders.append(r)
                new_count += 1

        print(f"{page_no + 1}페이지 신규 기사 수: {new_count}")

        if new_count == 0:
            print("새 기사 없음. 마지막 페이지로 판단하고 종료")
            break

    print(f"전체 수집 기사 수: {len(all_riders)}")
    return all_riders


def summary(rows):
    complete = sum(r["complete"] for r in rows)
    reject = sum(r["reject"] for r in rows)
    cancel = sum(r["cancel"] for r in rows)

    return {
        "complete": complete,
        "reject": reject,
        "cancel": cancel,
        "riderFault": sum(r["riderFault"] for r in rows),
        "morning": sum(r["morning"] for r in rows),
        "afternoon": sum(r["afternoon"] for r in rows),
        "evening": sum(r["evening"] for r in rows),
        "midnight": sum(r["midnight"] for r in rows),
        "count": len(rows),
        "onlineCount": sum(1 for r in rows if r.get("isOnline")),
        "acceptRate": calc_accept_rate(complete, reject),
        "spareRejects": spare_rejects(complete, reject),
    }


def team_targets(now):
    base = dict(zip(PERIODS, DAY_TARGETS[now.weekday()]))
    result = {}

    for team, sets in AREA_CONFIG[AREA_NAME].items():
        result[team] = {p: math.ceil(base[p] * sets) for p in PERIODS}
        result[team]["total"] = sum(result[team][p] for p in PERIODS)
        result[team]["sets"] = sets

    return result


def load_weekly():
    if WEEKLY_FILE.exists():
        with open(WEEKLY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_weekly_if_close(data):
    now = datetime.now()

    if not (now.hour == 3 and now.minute >= 30):
        return

    weekly = load_weekly()
    today_key = data["businessDate"]

    if any(x.get("businessDate") == today_key for x in weekly):
        return

    weekly.append({
        "businessDate": today_key,
        "closedAt": now.strftime("%Y-%m-%d %H:%M:%S"),
        "totalComplete": data["total"]["complete"],
        "totalReject": data["total"]["reject"],
        "totalCancel": data["total"]["cancel"],
        "acceptRate": data["total"]["acceptRate"],
        "spareRejects": data["total"]["spareRejects"],
    })

    weekly = weekly[-14:]

    with open(WEEKLY_FILE, "w", encoding="utf-8") as f:
        json.dump(weekly, f, ensure_ascii=False, indent=2)


def make_data(riders):
    now = datetime.now()
    riders.sort(key=lambda x: x["complete"], reverse=True)

    targets = team_targets(now)
    teams = {}

    for team in TEAM_ORDER:
        rows = [r for r in riders if r["team"] == team]
        teams[team] = {
            "summary": summary(rows),
            "targets": targets[team],
            "riders": rows,
        }

    return {
        "area": AREA_NAME,
        "areas": ["달서A", "달서B", "중구A"],
        "teamOrder": TEAM_ORDER,
        "updatedAt": now.strftime("%Y-%m-%d %H:%M:%S"),
        "businessDate": str(business_date(now)),
        "currentPeriod": current_period(now),
        "currentPeriodLabel": PERIOD_LABELS[current_period(now)],
        "targetAcceptRate": TARGET_ACCEPT_RATE,
        "total": summary(riders),
        "teams": teams,
        "riders": riders,
        "weekly": load_weekly(),
    }


def save_json(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_html():
    return


def git_push():
    if not AUTO_GIT_PUSH:
        return

    subprocess.run(
        ["git", "add", "data_dalseob.json", "index.html", "b_a.py", "logo.png"],
        cwd=BASE_DIR
    )

    if WEEKLY_FILE.exists():
        subprocess.run(
            ["git", "add", "weekly.json"],
            cwd=BASE_DIR
        )

    commit = subprocess.run(
        ["git", "commit", "-m", "auto update"],
        cwd=BASE_DIR,
        capture_output=True,
        text=True
    )

    if commit.returncode != 0:
        print("커밋할 변경사항 없음")
        return

    push = subprocess.run(
        ["git", "push"],
        cwd=BASE_DIR,
        capture_output=True,
        text=True
    )

    print(push.stdout)
    print(push.stderr)


def run_update(page):
    riders = collect_all_pages_by_copy(page)

    if len(riders) == 0:
        print("기사 데이터를 못 읽었습니다.")
        return

    data = make_data(riders)

    save_weekly_if_close(data)
    data["weekly"] = load_weekly()

    save_json(data)

    # save_html()

    git_push()

    print(f"업로드 완료: {data['updatedAt']}")
    print(f"전체 기사 수: {data['total']['count']}")
    print(f"접속중 기사 수: {data['total']['onlineCount']}")
    print(f"전체 완료: {data['total']['complete']}")
    print(f"수락률: {data['total']['acceptRate']}%")


def main():
    print("SUPERSONIC 달서B 자동 수집기")

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(BASE_DIR / "chrome_profile_dalseob"),
            headless=False,
            viewport={"width": 1400, "height": 900},
        )

        page = browser.new_page()

        page.goto(
            "https://deliverycenter.baemin.com/delivery/history?page=0&size=100&orderName=name&orderBy=asc&name=&userId=&phoneNumber=&riderStatus="
        )

        print("1. 열린 배민비즈 창에서 로그인하세요.")
        print("2. 달서B 기사 실적 페이지로 이동하세요.")
        print("3. 100개 보기로 맞추세요.")
        print("4. 준비되면 CMD에서 Enter 누르세요.")

        input("Enter 대기 중...")

        while True:
            print("")
            print("===================================")
            print("자동 수집 시작")
            print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

            try:
                run_update(page)

            except Exception as e:
                print("오류 발생:")
                print(e)

            print(f"{REFRESH_SECONDS}초 후 다시 자동 수집합니다.")
            time.sleep(REFRESH_SECONDS)


if __name__ == "__main__":
    main()
