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
DATA_FILE = BASE_DIR / "data_junggua.json"
HTML_FILE = BASE_DIR / "index.html"
WEEKLY_FILE = BASE_DIR / "weekly.json"

AREA_NAME = "중구A"

NUMBER_TEAM_RIDERS = [
    "한창목", "구민성", "석윤미", "조영웅", "류창우",
    "이경은", "이경림", "김광미", "정용운", "지덕곤",
    "김우중", "김시곤", "천재원", "조정래", "이금형",
    "최종용", "최문호", "이정미", "염용범", "김성주",
    "이창원", "채기후", "손성기", "박진수", "김병찬",
]

AREA_CONFIG = {
    "중구A": {
        "소닉팀": 4,
        "넘버팀": 1,
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
    return "넘버팀" if name in NUMBER_TEAM_RIDERS else "소닉팀"


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
        is_online = status not in ["미접속", "운행 종료", "운행종료", "종료", "오프라인", "-"]

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
    for team in AREA_CONFIG[AREA_NAME].keys():
        rows = [r for r in riders if r["team"] == team]
        teams[team] = {
            "summary": summary(rows),
            "targets": targets[team],
            "riders": rows,
        }
    return {
        "area": AREA_NAME,
        "areas": ["달서A", "달서B", "중구A"],
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
        ["git", "add", "data_junggua.json", "index.html", "c_a.py", "logo.png"],
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
    print("SUPERSONIC 중구A 자동 수집기")

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(BASE_DIR / "chrome_profile_junggu"),
            headless=False,
            viewport={"width": 1400, "height": 900},
        )

        page = browser.new_page()

        page.goto(
            "https://deliverycenter.baemin.com/delivery/history?page=0&size=100&orderName=name&orderBy=asc&name=&userId=&phoneNumber=&riderStatus="
        )

        print("1. 열린 배민비즈 창에서 로그인하세요.")
        print("2. 중구A 기사 실적 페이지로 이동하세요.")
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
