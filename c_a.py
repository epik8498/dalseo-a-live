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
DATA_FILE = BASE_DIR / "data.json"
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
    html = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>SUPERSONIC 중구A 관제판</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
:root{--red:#e60012;--blue:#006fd6;--green:#00c853;--text:#111;--muted:#777;--line:#e6e6e6;--card:#fff;--bg:#fff}
body.dark{--text:#fff;--muted:#cfcfcf;--line:#333;--card:#151515;--bg:#080808}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Arial,'Noto Sans KR',sans-serif}
body.dark{background:linear-gradient(135deg,rgba(0,0,0,.92),rgba(15,15,15,.96)),url('logo.png') right 60px top 90px / 380px auto no-repeat}.wrap{max-width:760px;margin:0 auto;padding:16px 14px 40px}.top{position:relative;text-align:center;padding-top:6px}.move,.mode{border:1px solid var(--line);background:var(--card);color:var(--text);border-radius:10px;padding:10px 14px;font-weight:900}.move{position:absolute;left:0;top:4px}.mode{position:absolute;right:0;top:4px;cursor:pointer}.logo-img{width:96px}.brand{color:var(--red);font-size:30px;font-weight:1000;font-style:italic;margin-top:4px}.sub{font-size:15px;font-weight:900}.area{margin:10px 0 16px;text-align:center;font-size:16px;font-weight:900}.area b{color:var(--red)}.summary{border:2px solid var(--red);border-radius:16px;background:rgba(255,255,255,.82);overflow:hidden;margin-bottom:20px}body.dark .summary{background:rgba(15,15,15,.78)}.summary-grid{display:grid;grid-template-columns:repeat(5,1fr)}.sum{padding:15px 6px;text-align:center;border-right:1px solid var(--line)}.sum:nth-child(5n){border-right:0}.sum.topline{border-bottom:1px solid var(--line)}.sum-title{font-size:12px;font-weight:900}.sum-val{margin-top:6px;font-size:22px;font-weight:1000}.sum-val.red{color:var(--red)}.section-title{margin:22px 0 12px;display:flex;align-items:center;gap:8px;font-size:21px;font-weight:1000}.section-title .icon{color:var(--red)}.period-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:22px}.period-card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;box-shadow:0 6px 18px rgba(0,0,0,.06)}body.dark .period-card{box-shadow:none;background:rgba(20,20,20,.9)}.period-head{font-size:18px;font-weight:1000;margin-bottom:4px}.period-sub{font-size:12px;color:var(--muted);font-weight:900}.period-total{margin:14px 0 12px;text-align:center;font-size:24px;font-weight:1000}.period-total span:first-child{color:var(--red)}.total-bar{height:12px;background:#e9e9e9;border-radius:999px;overflow:hidden;margin-bottom:14px}body.dark .total-bar{background:#333}.total-fill{height:100%;background:var(--red);border-radius:999px}.team-line{display:grid;grid-template-columns:36px 1fr auto;align-items:center;gap:8px;font-size:13px;font-weight:900;margin:8px 0}.team-name{font-size:14px}.team-num .done{color:var(--red)}.team-num .goal{color:var(--blue)}.small-bar{height:10px;background:#ececec;border-radius:999px;overflow:hidden}body.dark .small-bar{background:#333}.small-fill.red{height:100%;background:var(--red)}.small-fill.blue{height:100%;background:var(--blue)}.controls{display:flex;justify-content:space-between;align-items:center;gap:10px;margin:20px 0 14px}.filters{display:flex;gap:10px}.filters button{min-width:82px;border:1px solid var(--line);background:var(--card);color:var(--text);border-radius:8px;padding:11px 14px;font-weight:900;cursor:pointer}.filters button.active{background:var(--red);border-color:var(--red);color:#fff}.sort{display:flex;align-items:center;gap:8px;font-weight:900}.sort select{border:1px solid var(--line);background:var(--card);color:var(--text);border-radius:8px;padding:11px 16px;font-weight:900}.riders{display:grid;grid-template-columns:1fr 1fr;gap:12px}.rider{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;box-shadow:0 4px 14px rgba(0,0,0,.05)}.rider.active{border:2px solid var(--green)}body.dark .rider{background:rgba(18,18,18,.92);box-shadow:none}.rider-top{display:flex;justify-content:space-between;align-items:center}.rider-name{font-size:22px;font-weight:1000}.dot{display:inline-block;width:10px;height:10px;border-radius:999px;background:#bbb;margin-right:8px}.rider.active .dot{background:var(--green)}.status{font-size:11px;font-weight:900;padding:4px 7px;border-radius:999px;background:#eee;color:#555}.rider.active .status{background:#d9ffe8;color:#006b2c}.warn{color:#ff9f00;font-size:12px;font-weight:900;margin-left:4px}.stats{display:grid;grid-template-columns:repeat(3,1fr);margin-top:14px;text-align:center}.stat{border-right:1px solid var(--line)}.stat:last-child{border-right:0}.stat small{display:block;font-size:12px;font-weight:900}.stat b{display:block;margin-top:4px;font-size:18px}.stat b.red{color:var(--red)}.times{display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid var(--line);margin-top:12px;padding-top:10px;text-align:center}.times div{border-right:1px solid var(--line);font-size:12px;font-weight:900}.times div:last-child{border-right:0}.times b{display:block;color:var(--red);font-size:16px;margin-top:3px}.footer{text-align:center;color:var(--muted);font-weight:900;padding:24px 0 4px}@media(max-width:720px){.summary-grid{grid-template-columns:repeat(3,1fr)}.sum:nth-child(5n){border-right:1px solid var(--line)}.sum:nth-child(3n){border-right:0}.period-grid{grid-template-columns:1fr 1fr}}@media(max-width:520px){.move,.mode{position:static;margin:4px}.summary-grid{grid-template-columns:repeat(3,1fr)}.period-grid{grid-template-columns:1fr}.riders{grid-template-columns:1fr}.controls{flex-direction:column;align-items:stretch}.filters{display:grid;grid-template-columns:repeat(3,1fr)}.filters button{min-width:0}.sort{justify-content:flex-end}}
</style></head><body><div class="wrap"><div class="top"><button class="move">권역이동</button><button class="mode" onclick="toggleMode()" id="modeBtn">🌙 다크 모드</button><img src="logo.png" class="logo-img"><div class="brand">SUPERSONIC</div><div class="sub">배민 | 쿠팡협력사</div><div class="area">현재 권역 : <b id="areaText">중구A</b></div></div><div class="summary"><div class="summary-grid"><div class="sum topline"><div class="sum-title">총 물량</div><div class="sum-val" id="totalVolume">0</div></div><div class="sum topline"><div class="sum-title">총 발주량</div><div class="sum-val" id="totalOrder">0</div></div><div class="sum topline"><div class="sum-title">총 완료량</div><div class="sum-val" id="totalComplete">0</div></div><div class="sum topline"><div class="sum-title">총 수락률</div><div class="sum-val" id="totalRate">0%</div></div><div class="sum topline"><div class="sum-title">총 여유거절</div><div class="sum-val red" id="totalSpare">0</div></div><div class="sum"><div class="sum-title">당일 완료</div><div class="sum-val red" id="dayComplete">0</div></div><div class="sum"><div class="sum-title">당일 발주량</div><div class="sum-val" id="dayOrder">0</div></div><div class="sum"><div class="sum-title">당일 수락률</div><div class="sum-val" id="dayRate">0%</div></div><div class="sum"><div class="sum-title">전체 접속</div><div class="sum-val red" id="onlineCount">0명</div></div><div class="sum"><div class="sum-title">접속중(소닉/넘버)</div><div class="sum-val red" id="teamCount">0/0</div></div></div></div><div class="section-title"><span class="icon">▮</span> 구간별 실적 <span style="font-size:14px;font-weight:900">(완료 / 발주량)</span></div><div class="period-grid" id="periodCards"></div><div class="controls"><div class="filters"><button onclick="setFilter('전체')" id="f전체">전체</button><button onclick="setFilter('소닉팀')" id="f소닉팀">소닉팀</button><button onclick="setFilter('넘버팀')" id="f넘버팀">넘버팀</button></div><div class="sort">정렬:<select id="sortSelect" onchange="render()"><option value="complete">완료순</option><option value="name">가나다순</option></select></div></div><div class="riders" id="riderGrid"></div><div class="footer" id="footerTime">마지막 업데이트 : -</div></div><script>
let DATA=null;let FILTER="전체";function n(v){return Number(v||0).toLocaleString()}function pct(a,b){return !b?0:Math.min(100,Math.round((a/b)*100))}function setFilter(v){FILTER=v;render()}function toggleMode(){document.body.classList.toggle("dark");const dark=document.body.classList.contains("dark");localStorage.setItem("mode",dark?"dark":"light");document.getElementById("modeBtn").innerText=dark?"☀ 라이트 모드":"🌙 다크 모드"}if(localStorage.getItem("mode")==="dark"){document.body.classList.add("dark")}async function loadData(){const res=await fetch("data.json?time="+Date.now());DATA=await res.json();render()}function render(){const d=DATA;if(!d)return;const sonic=d.teams["소닉팀"]||{summary:{},targets:{}};const number=d.teams["넘버팀"]||{summary:{},targets:{}};const totalOrder=(sonic.targets.total||0)+(number.targets.total||0);document.getElementById("modeBtn").innerText=document.body.classList.contains("dark")?"☀ 라이트 모드":"🌙 다크 모드";document.getElementById("areaText").innerText=d.area;document.getElementById("totalVolume").innerText=n(totalOrder);document.getElementById("totalOrder").innerText=n(totalOrder);document.getElementById("totalComplete").innerText=n(d.total.complete);document.getElementById("totalRate").innerText=d.total.acceptRate+"%";document.getElementById("totalSpare").innerText=n(d.total.spareRejects);document.getElementById("dayComplete").innerText=n(d.total.complete);document.getElementById("dayOrder").innerText=n(totalOrder);document.getElementById("dayRate").innerText=d.total.acceptRate+"%";document.getElementById("onlineCount").innerText=n(d.total.onlineCount)+"명";document.getElementById("teamCount").innerText=n(sonic.summary.onlineCount)+"/"+n(number.summary.onlineCount);document.getElementById("footerTime").innerText="↻ 마지막 업데이트 : "+d.updatedAt;const periods=[["morning","☀","오전 피크"],["afternoon","☀","오후 논피크"],["evening","🌇","저녁 피크"],["midnight","🌙","심야 논피크"]];document.getElementById("periodCards").innerHTML=periods.map(([key,icon,label])=>{const sonicDone=sonic.summary[key]||0;const numberDone=number.summary[key]||0;const sonicGoal=sonic.targets[key]||0;const numberGoal=number.targets[key]||0;const totalDone=sonicDone+numberDone;const totalGoal=sonicGoal+numberGoal;return `<div class="period-card"><div class="period-head">${icon} ${label}</div><div class="period-sub">완료 / 발주량</div><div class="period-total"><span>${n(totalDone)}</span> / <span>${n(totalGoal)}</span></div><div class="total-bar"><div class="total-fill" style="width:${pct(totalDone,totalGoal)}%"></div></div><div class="team-line"><div class="team-name">소닉</div><div class="small-bar"><div class="small-fill red" style="width:${pct(sonicDone,sonicGoal)}%"></div></div><div class="team-num"><span class="done">${n(sonicDone)}</span> / <span class="goal">${n(sonicGoal)}</span></div></div><div class="team-line"><div class="team-name">넘버</div><div class="small-bar"><div class="small-fill blue" style="width:${pct(numberDone,numberGoal)}%"></div></div><div class="team-num"><span class="done">${n(numberDone)}</span> / <span class="goal">${n(numberGoal)}</span></div></div></div>`}).join("");document.querySelectorAll(".filters button").forEach(b=>b.classList.remove("active"));document.getElementById("f"+FILTER).classList.add("active");let riders=[...(d.riders||[])];if(FILTER!=="전체")riders=riders.filter(r=>r.team===FILTER);const sort=document.getElementById("sortSelect").value;if(sort==="name")riders.sort((a,b)=>a.name.localeCompare(b.name,"ko"));else riders.sort((a,b)=>b.complete-a.complete);document.getElementById("riderGrid").innerHTML=riders.map(r=>`<div class="rider ${r.isOnline?'active':''}"><div class="rider-top"><div class="rider-name"><span class="dot"></span>${r.name}</div><div><span class="status">${r.isOnline?'접속중':'미접속'}</span>${r.warning?'<span class="warn">80%↓</span>':''}</div></div><div class="stats"><div class="stat"><small>완료</small><b class="red">${n(r.complete)}</b></div><div class="stat"><small>거절/취소</small><b>${n(r.reject)} / ${n(r.cancel)}</b></div><div class="stat"><small>수락률</small><b>${r.acceptRate}%</b></div></div><div class="times"><div>오전<b>${n(r.morning)}</b></div><div>오후<b>${n(r.afternoon)}</b></div><div>저녁<b>${n(r.evening)}</b></div><div>심야<b>${n(r.midnight)}</b></div></div></div>`).join("")}loadData();setInterval(loadData,30000);
</script></body></html>"""
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)


def git_push():
    if not AUTO_GIT_PUSH:
        return
    subprocess.run(["git", "add", "data.json", "index.html", "c_a.py", "logo.png"], cwd=BASE_DIR)
    if WEEKLY_FILE.exists():
        subprocess.run(["git", "add", "weekly.json"], cwd=BASE_DIR)
    commit = subprocess.run(["git", "commit", "-m", "auto update"], cwd=BASE_DIR, capture_output=True, text=True)
    if commit.returncode != 0:
        print("커밋할 변경사항 없음")
        return
    push = subprocess.run(["git", "push"], cwd=BASE_DIR, capture_output=True, text=True)
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
    save_html()
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
        page.goto("https://deliverycenter.baemin.com/delivery/history?page=0&size=100&orderName=name&orderBy=asc&name=&userId=&phoneNumber=&riderStatus=")
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
