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
*{box-sizing:border-box}
body{
  margin:0;
  background:#f4f5f7;
  font-family:Arial,'Noto Sans KR',sans-serif;
  color:#111;
}
.wrap{
  max-width:760px;
  margin:0 auto;
  padding:16px;
}
.header{
  background:#111;
  color:#fff;
  border-radius:20px;
  padding:18px;
  margin-bottom:14px;
}
.logo{
  font-size:30px;
  font-weight:900;
  color:#ff1e1e;
}
.sub{
  font-size:13px;
  margin-top:4px;
  color:#ddd;
}
.time{
  margin-top:10px;
  font-size:12px;
  color:#aaa;
}
.tabs{
  display:grid;
  grid-template-columns:repeat(3,1fr);
  gap:8px;
  margin:14px 0;
}
.tabs button{
  border:2px solid #111;
  background:#fff;
  border-radius:12px;
  padding:10px;
  font-weight:900;
}
.tabs button.active{
  background:#e60012;
  color:#fff;
  border-color:#e60012;
}
.hero{
  display:grid;
  grid-template-columns:2fr 1fr 1fr;
  gap:10px;
  margin-bottom:12px;
}
.card{
  background:#fff;
  border-radius:18px;
  padding:16px;
  box-shadow:0 4px 12px rgba(0,0,0,.08);
}
.card.red{
  background:#e60012;
  color:#fff;
}
.card.black{
  background:#111;
  color:#fff;
}
.label{
  font-size:12px;
  font-weight:900;
  color:#777;
}
.red .label,.black .label{
  color:rgba(255,255,255,.75);
}
.value{
  font-size:30px;
  font-weight:900;
  margin-top:6px;
}
.big{
  font-size:52px;
}
.grid{
  display:grid;
  grid-template-columns:repeat(3,1fr);
  gap:10px;
  margin-bottom:12px;
}
.section{
  margin:24px 0 10px;
  font-size:20px;
  font-weight:900;
}
.team-grid{
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:12px;
}
.team-card{
  background:#fff;
  border:2px solid #111;
  border-radius:18px;
  padding:14px;
}
.team-title{
  font-size:18px;
  font-weight:900;
  margin-bottom:10px;
}
.row{
  margin:10px 0;
}
.row-top{
  display:flex;
  justify-content:space-between;
  font-size:13px;
  font-weight:900;
  margin-bottom:5px;
}
.bar{
  height:12px;
  background:#eee;
  border-radius:999px;
  overflow:hidden;
}
.fill{
  height:100%;
  background:#e60012;
}
.filters{
  display:grid;
  grid-template-columns:repeat(4,1fr);
  gap:8px;
  margin:14px 0;
}
.filters button{
  border:1px solid #111;
  background:#fff;
  border-radius:999px;
  padding:8px;
  font-weight:900;
}
.filters button.active{
  background:#111;
  color:#fff;
}
.riders{
  display:grid;
  grid-template-columns:repeat(2,1fr);
  gap:12px;
}
.rider{
  background:#111;
  color:#fff;
  border-radius:18px;
  padding:14px;
  border:3px solid #111;
  position:relative;
}
.rider.active{
  background:#f7fff9;
  color:#111;
  border-color:#00d26a;
}
.rider-name{
  font-size:22px;
  font-weight:900;
}
.team{
  display:inline-block;
  margin-top:5px;
  font-size:11px;
  font-weight:900;
  background:#333;
  color:#fff;
  border-radius:999px;
  padding:4px 8px;
}
.rider.active .team{
  background:#00d26a;
  color:#053818;
}
.warn{
  position:absolute;
  right:10px;
  top:10px;
  background:#ffe58f;
  color:#6b5200;
  border-radius:999px;
  padding:4px 7px;
  font-size:11px;
  font-weight:900;
}
.stats{
  display:grid;
  grid-template-columns:repeat(3,1fr);
  gap:6px;
  margin-top:12px;
}
.stat{
  background:rgba(255,255,255,.1);
  border-radius:10px;
  text-align:center;
  padding:8px 4px;
}
.rider.active .stat{
  background:#ececec;
}
.stat small{
  display:block;
  color:#aaa;
  font-weight:900;
}
.rider.active .stat small{
  color:#666;
}
.stat b{
  font-size:17px;
}
.periods{
  display:grid;
  grid-template-columns:repeat(4,1fr);
  gap:5px;
  margin-top:10px;
  font-size:12px;
  text-align:center;
}
.periods div{
  background:rgba(255,255,255,.1);
  border-radius:8px;
  padding:6px 2px;
}
.rider.active .periods div{
  background:#eef8f0;
}
.weekly{
  margin-top:24px;
  background:#fff;
  border-radius:18px;
  padding:14px;
}
table{
  width:100%;
  border-collapse:collapse;
  font-size:13px;
}
th,td{
  padding:8px 4px;
  border-bottom:1px solid #eee;
  text-align:center;
}
.error{
  background:#fff3f3;
  border:2px solid #e60012;
  padding:16px;
  border-radius:14px;
  color:#e60012;
  font-weight:900;
}
@media(max-width:520px){
  .hero{grid-template-columns:1fr}
  .grid{grid-template-columns:1fr 1fr}
  .team-grid{grid-template-columns:1fr}
  .riders{grid-template-columns:1fr}
}
</style>
</head>
<body>
<div class="wrap">

  <div class="header">
    <div class="logo">SUPERSONIC</div>
    <div class="sub">달서A 실시간 자동 관제판</div>
    <div class="time" id="timeNow">데이터 불러오는 중...</div>
  </div>

  <div class="tabs" id="areaTabs"></div>

  <div id="errorBox"></div>

  <div class="hero">
    <div class="card red">
      <div class="label">당일 총 완료</div>
      <div class="value big" id="totalComplete">0</div>
    </div>
    <div class="card black">
      <div class="label">수락률</div>
      <div class="value" id="acceptRate">0%</div>
    </div>
    <div class="card">
      <div class="label">현재구간</div>
      <div class="value" id="currentPeriod">-</div>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <div class="label">전체 기사</div>
      <div class="value" id="totalCount">0</div>
    </div>
    <div class="card">
      <div class="label">거절 / 취소</div>
      <div class="value" id="rejectCancel">0/0</div>
    </div>
    <div class="card">
      <div class="label">여유거절</div>
      <div class="value" id="spareRejects">0</div>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <div class="label">소닉팀 완료</div>
      <div class="value" id="sonicComplete">0</div>
    </div>
    <div class="card">
      <div class="label">달서팀 완료</div>
      <div class="value" id="dalseoComplete">0</div>
    </div>
    <div class="card">
      <div class="label">업데이트</div>
      <div class="value" style="font-size:16px" id="updatedAt">-</div>
    </div>
  </div>

  <div class="section">구간별 목표 현황</div>
  <div class="team-grid" id="teamGoals"></div>

  <div class="section">기사 실적 카드</div>
  <div class="filters">
    <button onclick="setFilter('전체')" id="f전체">전체</button>
    <button onclick="setFilter('소닉팀')" id="f소닉팀">소닉</button>
    <button onclick="setFilter('달서팀')" id="f달서팀">달서</button>
    <button onclick="toggleSort()" id="sortBtn">완료순</button>
  </div>

  <div class="riders" id="riderGrid"></div>

  <div class="weekly">
    <div class="section" style="margin-top:0">주간 마감 실적</div>
    <table>
      <thead>
        <tr>
          <th>날짜</th>
          <th>완료</th>
          <th>거절</th>
          <th>수락률</th>
          <th>여유</th>
        </tr>
      </thead>
      <tbody id="weeklyTable"></tbody>
    </table>
  </div>

</div>

<script>
let DATA = null;
let FILTER = "전체";
let SORT_DESC = true;

function num(v){
  return Number(v || 0).toLocaleString();
}

function pct(now, target){
  if(!target || target <= 0) return 0;
  return Math.min(100, Math.round((now / target) * 100));
}

function setFilter(v){
  FILTER = v;
  render();
}

function toggleSort(){
  SORT_DESC = !SORT_DESC;
  render();
}

async function loadData(){
  try{
    const res = await fetch("data.json?time=" + Date.now());
    DATA = await res.json();
    document.getElementById("errorBox").innerHTML = "";
    render();
  }catch(e){
    document.getElementById("errorBox").innerHTML =
      '<div class="error">data.json을 읽지 못했습니다. GitHub 업로드 또는 파일명을 확인하세요.</div>';
    console.error(e);
  }
}

function render(){
  const d = DATA;
  if(!d) return;

  document.getElementById("timeNow").innerText =
    "마지막 업데이트: " + d.updatedAt + " / 영업일: " + d.businessDate;

  document.getElementById("areaTabs").innerHTML = (d.areas || []).map(a => `
    <button class="${a === d.area ? "active" : ""}">${a}</button>
  `).join("");

  document.getElementById("totalComplete").innerText = num(d.total.complete);
  document.getElementById("acceptRate").innerText = d.total.acceptRate + "%";
  document.getElementById("currentPeriod").innerText = d.currentPeriodLabel;
  document.getElementById("totalCount").innerText = num(d.total.count);
  document.getElementById("rejectCancel").innerText = num(d.total.reject) + "/" + num(d.total.cancel);
  document.getElementById("spareRejects").innerText = num(d.total.spareRejects);
  document.getElementById("updatedAt").innerText = d.updatedAt.split(" ")[1] || d.updatedAt;

  const sonic = d.teams["소닉팀"] ? d.teams["소닉팀"].summary.complete : 0;
  const dalseo = d.teams["달서팀"] ? d.teams["달서팀"].summary.complete : 0;

  document.getElementById("sonicComplete").innerText = num(sonic);
  document.getElementById("dalseoComplete").innerText = num(dalseo);

  document.getElementById("teamGoals").innerHTML = Object.entries(d.teams).map(([team, obj]) => {
    const s = obj.summary;
    const t = obj.targets;

    return `
      <div class="team-card">
        <div class="team-title">${team} <span style="font-size:12px;color:#777">${t.sets}세트</span></div>
        ${["morning","afternoon","evening","midnight"].map(p => {
          const label = p === "morning" ? "오전" : p === "afternoon" ? "오후" : p === "evening" ? "저녁" : "심야";
          return `
            <div class="row">
              <div class="row-top">
                <span>${label}</span>
                <span>${num(s[p])} / ${num(t[p])}</span>
              </div>
              <div class="bar">
                <div class="fill" style="width:${pct(s[p], t[p])}%"></div>
              </div>
            </div>
          `;
        }).join("")}
      </div>
    `;
  }).join("");

  document.querySelectorAll(".filters button").forEach(b => b.classList.remove("active"));
  const filterBtn = document.getElementById("f" + FILTER);
  if(filterBtn) filterBtn.classList.add("active");

  let riders = Array.isArray(d.riders) ? [...d.riders] : [];

  if(FILTER !== "전체"){
    riders = riders.filter(r => r.team === FILTER);
  }

  riders.sort((a,b) => SORT_DESC ? b.complete - a.complete : a.complete - b.complete);

  document.getElementById("riderGrid").innerHTML = riders.map(r => `
    <div class="rider ${r.complete > 0 ? "active" : ""}">
      ${r.warning ? '<div class="warn">⚠ 80%↓</div>' : ''}
      <div class="rider-name">${r.name}</div>
      <div class="team">${r.team}</div>

      <div class="stats">
        <div class="stat"><small>완료</small><b>${num(r.complete)}</b></div>
        <div class="stat"><small>거절/취소</small><b>${num(r.reject)}/${num(r.cancel)}</b></div>
        <div class="stat"><small>수락률</small><b>${r.acceptRate}%</b></div>
      </div>

      <div class="periods">
        <div>오전<br>${num(r.morning)}</div>
        <div>오후<br>${num(r.afternoon)}</div>
        <div>저녁<br>${num(r.evening)}</div>
        <div>심야<br>${num(r.midnight)}</div>
      </div>
    </div>
  `).join("");

  document.getElementById("weeklyTable").innerHTML = (d.weekly || []).slice().reverse().map(w => `
    <tr>
      <td>${w.businessDate}</td>
      <td>${num(w.totalComplete)}</td>
      <td>${num(w.totalReject)}</td>
      <td>${w.acceptRate}%</td>
      <td>${num(w.spareRejects)}</td>
    </tr>
  `).join("");
}

loadData();
setInterval(loadData, 30000);
</script>
</body>
</html>
"""
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)


def git_push():
    if not AUTO_GIT_PUSH:
        return

    subprocess.run(["git", "add", "data.json", "index.html", "d_a.py", "logo.png"], cwd=BASE_DIR)

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
