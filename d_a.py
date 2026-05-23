import json
import math
import subprocess
import time
import re
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

AREA_NAME = "달서A"

DALSEO_T_RIDERS = [
    "김민승", "윤창근", "김병국", "신호준", "김영빈",
    "김용우", "박지원", "김탁기", "김병철", "정영훈",
    "김태광", "배재현", "김형민", "문승수", "이상민",
    "정성훈", "이주철", "박기홍", "정판호", "나미영",
    "황호용", "김영철", "남승훈", "남수현", "김민서",
    "신진관", "임선미", "여재환", "정주현", "김기현",
    "김범준", "이윤석", "양혜진", "김민우", "김혜성",
    "김기헌", "조대영", "정승덕", "임상완", "김우진"
]

AREA_CONFIG = {
    "달서A": {
        "소닉팀": 7,
        "달서팀": 1,
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
    return "달서팀" if name in DALSEO_T_RIDERS else "소닉팀"


def to_int(value):
    try:
        return int(str(value).replace(",", "").strip())
    except:
        return 0


def set_page_number(url, page_no):
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)

    qs["page"] = [str(page_no)]
    if "size" not in qs:
        qs["size"] = ["100"]

    new_query = urlencode(qs, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def parse_clipboard_text(text):
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    riders = []

    i = 0
    while i < len(lines):
        name = lines[i]

        if i + 34 >= len(lines):
            i += 1
            continue

        phone = lines[i + 1]

        if not phone.startswith("010-"):
            i += 1
            continue

        complete = to_int(lines[i + 2])
        reject = to_int(lines[i + 3])
        cancel = to_int(lines[i + 4])
        rider_fault = to_int(lines[i + 5])

        morning = to_int(lines[i + 6])
        afternoon = to_int(lines[i + 7])
        evening = to_int(lines[i + 8])
        midnight = to_int(lines[i + 9])

        hourly = []
        for h in range(24):
            hourly.append(to_int(lines[i + 10 + h]))

        user_id = lines[i + 34]

        riders.append({
            "name": name,
            "phone": phone,
            "userId": user_id,
            "team": team_of(name),
            "status": "",
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

        i += 35

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
<title>SUPERSONIC 달서A 관제판</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
:root{--red:#e60012;--black:#111;--green:#00e676}
*{box-sizing:border-box}
body{margin:0;background:#fff;font-family:Arial,sans-serif;color:#111}
.wrap{max-width:560px;margin:0 auto;padding:14px}
.top-btn{border:3px solid #111;background:#fff;padding:8px 30px;font-weight:900;font-size:16px}
.logo{text-align:center;margin-top:-6px}
.logo-mark{font-size:58px;color:var(--red);font-weight:900;line-height:1}
.logo-title{color:var(--red);font-size:28px;font-weight:900}
.logo-sub{font-weight:800;font-size:16px}
.area-now{text-align:center;margin:18px 0 10px;font-weight:900}
.time{text-align:center;color:#555;font-size:13px;margin:8px 0}
.area-tabs{display:flex;gap:6px;margin:12px 0}
.area-tabs button{flex:1;padding:9px 0;border:2px solid #111;background:#fff;font-weight:900}
.area-tabs button.active{background:var(--red);color:#fff;border-color:var(--red)}
.summary-box{border:4px solid var(--red);border-radius:18px;padding:10px;margin:12px 0 24px}
.grid-3{display:grid;grid-template-columns:repeat(3,1fr)}
.sum-cell{text-align:center;padding:10px 4px;border-bottom:1px solid var(--red)}
.sum-cell:nth-child(3n+2){border-left:1px solid var(--red);border-right:1px solid var(--red)}
.sum-title{font-size:12px;font-weight:900}
.sum-val{font-size:17px;font-weight:900;margin-top:5px}
.team-goals{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:20px 0}
.goal-card{border:3px solid var(--red);border-radius:16px;padding:10px}
.section-title{text-align:center;font-size:14px;font-weight:900;margin-bottom:8px}
.goal-row{display:grid;grid-template-columns:48px 1fr 52px;gap:6px;align-items:center;margin:8px 0;font-size:13px;font-weight:900}
.bar{height:14px;background:#eee;border-radius:999px;overflow:hidden}
.fill{height:100%;background:var(--red);border-radius:999px}
.filter-row{display:flex;gap:8px;margin:22px 0 14px}
.filter-row button{flex:1;border:1px solid #111;background:#fff;padding:6px 0;font-weight:900}
.filter-row button.active{background:#111;color:#fff}
.rider-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.rider-card{border:3px solid #111;border-radius:14px;padding:10px;position:relative}
.rider-card.green{border-color:var(--green)}
.rider-name{font-size:21px;font-weight:900;margin-bottom:8px}
.warn{position:absolute;right:8px;top:8px;font-size:12px;background:#fff3cd;border:1px solid #ffd666;padding:2px 6px;border-radius:999px}
.rider-stats{display:grid;grid-template-columns:repeat(3,1fr);text-align:center;font-size:12px;gap:4px}
.rider-stats b{display:block;font-size:15px}
.periods{display:grid;grid-template-columns:repeat(4,1fr);text-align:center;margin-top:10px;font-size:12px}
.weekly{border:3px solid #111;border-radius:16px;padding:10px;margin:20px 0}
.weekly table{width:100%;border-collapse:collapse;font-size:12px}
.weekly th,.weekly td{border-bottom:1px solid #ddd;padding:6px;text-align:center}
@media(max-width:420px){.rider-grid{grid-template-columns:1fr}.team-goals{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="wrap">
<button class="top-btn">권역이동</button>
<div class="logo">
<div class="logo-mark">S</div>
<div class="logo-title">SUPERSONIC</div>
<div class="logo-sub">배민 | 쿠팡블럭사</div>
</div>
<div class="area-now" id="areaNow"></div>
<div class="time" id="timeNow"></div>
<div class="area-tabs" id="areaTabs"></div>
<div class="summary-box">
<div class="grid-3">
<div class="sum-cell"><div class="sum-title">주간 총완료</div><div class="sum-val" id="weekComplete">0</div></div>
<div class="sum-cell"><div class="sum-title">주간 거절/취소</div><div class="sum-val" id="weekReject">0/0</div></div>
<div class="sum-cell"><div class="sum-title">주간수락률/여유거절</div><div class="sum-val" id="weekRate">0% / 0</div></div>
<div class="sum-cell"><div class="sum-title">당일 완료</div><div class="sum-val" id="dayComplete">0</div></div>
<div class="sum-cell"><div class="sum-title">당일 거절/취소</div><div class="sum-val" id="dayReject">0/0</div></div>
<div class="sum-cell"><div class="sum-title">당일수락률</div><div class="sum-val" id="dayRate">0%</div></div>
<div class="sum-cell"><div class="sum-title">현재구간</div><div class="sum-val" id="currentPeriod">-</div></div>
<div class="sum-cell"><div class="sum-title">소닉팀</div><div class="sum-val" id="sonicTotal">0</div></div>
<div class="sum-cell"><div class="sum-title">달서팀</div><div class="sum-val" id="dalseoTotal">0</div></div>
</div>
</div>
<div class="team-goals" id="teamGoals"></div>
<div class="filter-row">
<button onclick="setFilter('전체')" id="f전체">전체</button>
<button onclick="setFilter('소닉팀')" id="f소닉팀">소닉</button>
<button onclick="setFilter('달서팀')" id="f달서팀">달서</button>
<button onclick="setSort()" id="sortBtn">완료순</button>
</div>
<div class="rider-grid" id="riderGrid"></div>
<div class="weekly">
<h3>주간 마감 실적</h3>
<table>
<thead><tr><th>날짜</th><th>완료</th><th>거절</th><th>수락률</th><th>여유</th></tr></thead>
<tbody id="weeklyTable"></tbody>
</table>
</div>
</div>
<script>
let DATA=null;let FILTER="전체";let SORT_DESC=true;
function pct(now,target){if(!target||target<=0)return 0;return Math.min(100,Math.round((now/target)*100));}
function setFilter(v){FILTER=v;render();}
function setSort(){SORT_DESC=!SORT_DESC;render();}
async function loadData(){const res=await fetch("data.json?time="+Date.now());DATA=await res.json();render();}
function render(){
 const d=DATA;if(!d)return;
 document.getElementById("areaNow").innerText=`(${d.area} 보고있는 권역)`;
 document.getElementById("timeNow").innerText=`마지막 업데이트 ${d.updatedAt} | 영업일 ${d.businessDate}`;
 document.getElementById("areaTabs").innerHTML=d.areas.map(a=>`<button class="${a===d.area?'active':''}">${a}</button>`).join("");
 const wc=d.weekly.reduce((s,x)=>s+x.totalComplete,0);
 const wr=d.weekly.reduce((s,x)=>s+x.totalReject,0);
 const wcan=d.weekly.reduce((s,x)=>s+x.totalCancel,0);
 const wrate=wc+wr===0?100:Math.round((wc/(wc+wr))*1000)/10;
 const wspare=Math.floor(wc*2/98)-wr;
 document.getElementById("weekComplete").innerText=wc;
 document.getElementById("weekReject").innerText=`${wr}/${wcan}`;
 document.getElementById("weekRate").innerText=`${wrate}% / ${wspare}`;
 document.getElementById("dayComplete").innerText=d.total.complete;
 document.getElementById("dayReject").innerText=`${d.total.reject}/${d.total.cancel}`;
 document.getElementById("dayRate").innerText=`${d.total.acceptRate}%`;
 document.getElementById("currentPeriod").innerText=d.currentPeriodLabel;
 document.getElementById("sonicTotal").innerText=d.teams["소닉팀"]?d.teams["소닉팀"].summary.complete:0;
 document.getElementById("dalseoTotal").innerText=d.teams["달서팀"]?d.teams["달서팀"].summary.complete:0;
 document.getElementById("teamGoals").innerHTML=Object.entries(d.teams).map(([team,obj])=>{
  const s=obj.summary;const t=obj.targets;
  return `<div class="goal-card"><div class="section-title">${team} 구간 실적 / 목표</div>
  ${["morning","afternoon","evening","midnight"].map(p=>`
  <div class="goal-row"><div>${p==="morning"?"오전":p==="afternoon"?"오후":p==="evening"?"저녁":"심야"}</div>
  <div class="bar"><div class="fill" style="width:${pct(s[p],t[p])}%"></div></div><div>${s[p]}/${t[p]}</div></div>`).join("")}</div>`;
 }).join("");
 document.querySelectorAll(".filter-row button").forEach(b=>b.classList.remove("active"));
 document.getElementById("f"+FILTER).classList.add("active");
 let riders=[...d.riders];if(FILTER!=="전체")riders=riders.filter(r=>r.team===FILTER);
 riders.sort((a,b)=>SORT_DESC?b.complete-a.complete:a.complete-b.complete);
 document.getElementById("riderGrid").innerHTML=riders.map(r=>`
 <div class="rider-card ${r.complete>0?'green':''}">
 ${r.warning?'<div class="warn">⚠ 수락률</div>':''}
 <div class="rider-name">${r.name}</div>
 <div class="rider-stats"><div>완료<b>${r.complete}</b></div><div>거절/취소<b>${r.reject}/${r.cancel}</b></div><div>수락률<b>${r.acceptRate}%</b></div></div>
 <div class="periods"><div>오전<br>${r.morning}</div><div>오후<br>${r.afternoon}</div><div>저녁<br>${r.evening}</div><div>심야<br>${r.midnight}</div></div>
 </div>`).join("");
 document.getElementById("weeklyTable").innerHTML=d.weekly.slice().reverse().map(w=>`
 <tr><td>${w.businessDate}</td><td>${w.totalComplete}</td><td>${w.totalReject}</td><td>${w.acceptRate}%</td><td>${w.spareRejects}</td></tr>`).join("");
}
loadData();setInterval(loadData,30000);
</script>
</body>
</html>
"""
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)


def git_push():
    if not AUTO_GIT_PUSH:
        return

    subprocess.run(["git", "add", "data.json", "index.html", "d_a.py"], cwd=BASE_DIR)

    if WEEKLY_FILE.exists():
        subprocess.run(["git", "add", "weekly.json"], cwd=BASE_DIR)

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
        print("확인: 기사페이지인지, 표가 보이는지, 100개 보기가 적용됐는지 확인하세요.")
        return

    data = make_data(riders)
    save_weekly_if_close(data)
    data["weekly"] = load_weekly()

    save_json(data)
    save_html()
    git_push()

    print(f"업로드 완료: {data['updatedAt']}")
    print(f"전체 기사 수: {data['total']['count']}")
    print(f"전체 완료: {data['total']['complete']}")
    print(f"수락률: {data['total']['acceptRate']}%")


def main():
    print("SUPERSONIC 달서A 자동 수집기")
    print("")

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(BASE_DIR / "chrome_profile"),
            headless=False,
            viewport={"width": 1400, "height": 900},
        )

        page = browser.new_page()
        page.goto("https://deliverycenter.baemin.com/delivery/history?page=0&size=100&orderName=name&orderBy=asc&name=&userId=&phoneNumber=&riderStatus=")

        print("1. 열린 배민비즈 창에서 로그인하세요.")
        print("2. 기사 실적 페이지로 이동하세요.")
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
