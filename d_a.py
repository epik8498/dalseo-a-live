import json
import math
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright

AUTO_GIT_PUSH = True
REFRESH_SECONDS = 60
TARGET_ACCEPT_RATE = 98

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data.json"
HTML_FILE = BASE_DIR / "index.html"
WEEKLY_FILE = BASE_DIR / "weekly.json"

API_URL = "https://api-deliverycenter.baemin.com/v2/management/delivery-status"

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
        "teams": {
            "소닉팀": {"sets": 7},
            "달서팀": {"sets": 1},
        }
    },
    "달서B": {
        "teams": {
            "마음팀": {"sets": 5.5},
            "넘버팀": {"sets": 5.5},
            "소닉팀": {"sets": 2},
        }
    },
    "중구A": {
        "teams": {
            "소닉팀": {"sets": 4},
            "넘버팀": {"sets": 1},
        }
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
    is_weekend = now.weekday() >= 5
    h = now.hour

    if is_weekend:
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


def get_day_targets(now):
    return dict(zip(PERIODS, DAY_TARGETS[now.weekday()]))


def calc_accept_rate(complete, reject):
    total = complete + reject
    if total == 0:
        return 100
    return round((complete / total) * 100, 1)


def spare_rejects(complete, reject):
    if complete <= 0:
        return 0 - reject
    max_reject = math.floor(complete * (100 - TARGET_ACCEPT_RATE) / TARGET_ACCEPT_RATE)
    return max_reject - reject


def collect_data(page):
    all_riders = []

    first_data = page.evaluate(
        """
        async (url) => {
            const res = await fetch(url + "?page=0&size=100&orderName=name&orderBy=asc&name=&userId=&phoneNumber=&riderStatus=", {
                credentials: "include"
            });
            return await res.json();
        }
        """,
        API_URL,
    )

    total_page = first_data.get("totalPage", 1)
    all_riders.extend(first_data.get("data", []))

    print(f"API 전체 페이지 수: {total_page}")
    print(f"1페이지 기사 수: {len(first_data.get('data', []))}")

    for page_no in range(1, total_page):
        data = page.evaluate(
            """
            async ({url, pageNo}) => {
                const res = await fetch(url + `?page=${pageNo}&size=100&orderName=name&orderBy=asc&name=&userId=&phoneNumber=&riderStatus=`, {
                    credentials: "include"
                });
                return await res.json();
            }
            """,
            {"url": API_URL, "pageNo": page_no},
        )

        page_rows = data.get("data", [])
        print(f"{page_no + 1}페이지 기사 수: {len(page_rows)}")
        all_riders.extend(page_rows)

    return all_riders


def team_of(name):
    if name in DALSEO_T_RIDERS:
        return "달서팀"
    return "소닉팀"


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


def team_targets(area_name, now):
    day_targets = get_day_targets(now)
    teams = AREA_CONFIG[area_name]["teams"]
    result = {}

    for team, cfg in teams.items():
        sets = cfg["sets"]
        result[team] = {
            p: math.ceil(day_targets[p] * sets)
            for p in PERIODS
        }
        result[team]["total"] = sum(result[team][p] for p in PERIODS)
        result[team]["sets"] = sets

    return result


def make_dashboard_data(riders):
    now = datetime.now()
    area_name = "달서A"
    targets = team_targets(area_name, now)

    result = []

    for rider in riders:
        name = rider.get("name", "").strip()
        acc = rider.get("deliveryAcceptanceCount", {})
        peak = rider.get("deliveryPeakTimeCount", {})

        complete = acc.get("complete", 0)
        reject = acc.get("reject", 0)
        cancel = acc.get("cancel", 0)
        rider_fault = acc.get("riderFault", 0)

        item = {
            "name": name,
            "area": area_name,
            "team": team_of(name),
            "status": rider.get("status", {}).get("desc", ""),
            "complete": complete,
            "reject": reject,
            "cancel": cancel,
            "riderFault": rider_fault,
            "morning": peak.get("morning", 0),
            "afternoon": peak.get("afternoon", 0),
            "evening": peak.get("evening", 0),
            "midnight": peak.get("midnight", 0),
            "acceptRate": calc_accept_rate(complete, reject),
            "warning": calc_accept_rate(complete, reject) < 80,
        }

        result.append(item)

    result.sort(key=lambda x: x["complete"], reverse=True)

    teams = {}
    for team in AREA_CONFIG[area_name]["teams"].keys():
        rows = [r for r in result if r["team"] == team]
        teams[team] = {
            "summary": summary(rows),
            "targets": targets[team],
            "riders": rows,
        }

    total = summary(result)
    weekly = load_weekly()

    return {
        "area": area_name,
        "areas": list(AREA_CONFIG.keys()),
        "updatedAt": now.strftime("%Y-%m-%d %H:%M:%S"),
        "businessDate": str(business_date(now)),
        "currentPeriod": current_period(now),
        "currentPeriodLabel": PERIOD_LABELS[current_period(now)],
        "targetAcceptRate": TARGET_ACCEPT_RATE,
        "total": total,
        "teams": teams,
        "riders": result,
        "weekly": weekly,
    }


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
:root {
    --red:#e60012;
    --dark:#111111;
    --green:#00e676;
    --gray:#f4f4f4;
}
* { box-sizing:border-box; }
body {
    margin:0;
    background:#ffffff;
    font-family: Arial, sans-serif;
    color:#111;
}
.wrap {
    max-width:560px;
    margin:0 auto;
    padding:14px;
}
.top-btn {
    border:3px solid #111;
    background:#fff;
    padding:8px 30px;
    font-weight:800;
    font-size:16px;
}
.logo {
    text-align:center;
    margin-top:-8px;
}
.logo-mark {
    font-size:58px;
    color:var(--red);
    font-weight:900;
    line-height:1;
}
.logo-title {
    color:var(--red);
    font-size:28px;
    font-weight:900;
}
.logo-sub {
    font-weight:800;
    font-size:16px;
}
.area-now {
    text-align:center;
    margin:18px 0 10px;
    font-weight:800;
}
.area-tabs {
    display:flex;
    gap:6px;
    margin:12px 0;
}
.area-tabs button {
    flex:1;
    padding:9px 0;
    border:2px solid #111;
    background:#fff;
    font-weight:800;
}
.area-tabs button.active {
    background:var(--red);
    color:white;
    border-color:var(--red);
}
.summary-box {
    border:4px solid var(--red);
    border-radius:18px;
    padding:10px;
    margin:12px 0 24px;
}
.grid-3 {
    display:grid;
    grid-template-columns:repeat(3,1fr);
}
.sum-cell {
    text-align:center;
    padding:10px 4px;
    border-bottom:1px solid var(--red);
}
.sum-cell:nth-child(3n+2) {
    border-left:1px solid var(--red);
    border-right:1px solid var(--red);
}
.sum-title {
    font-size:12px;
    font-weight:800;
}
.sum-val {
    font-size:16px;
    font-weight:900;
    margin-top:5px;
}
.section-title {
    text-align:center;
    font-size:14px;
    font-weight:900;
    margin-bottom:8px;
}
.team-goals {
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:18px;
    margin:20px 0;
}
.goal-card {
    border:3px solid var(--red);
    border-radius:16px;
    padding:10px;
}
.goal-row {
    display:grid;
    grid-template-columns:48px 1fr 48px;
    gap:6px;
    align-items:center;
    margin:8px 0;
    font-size:13px;
    font-weight:800;
}
.bar {
    height:14px;
    background:#eee;
    border-radius:999px;
    overflow:hidden;
}
.fill {
    height:100%;
    background:var(--red);
    border-radius:999px;
}
.filter-row {
    display:flex;
    gap:8px;
    margin:22px 0 14px;
}
.filter-row button {
    flex:1;
    border:1px solid #111;
    background:#fff;
    padding:6px 0;
    font-weight:800;
}
.filter-row button.active {
    background:#111;
    color:#fff;
}
.rider-grid {
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:12px;
}
.rider-card {
    border:3px solid #111;
    border-radius:14px;
    padding:10px;
    position:relative;
}
.rider-card.green {
    border-color:var(--green);
}
.rider-name {
    font-size:21px;
    font-weight:900;
    margin-bottom:8px;
}
.warn {
    position:absolute;
    right:10px;
    top:10px;
    font-size:13px;
    background:#fff3cd;
    border:1px solid #ffd666;
    padding:2px 6px;
    border-radius:999px;
}
.rider-stats {
    display:grid;
    grid-template-columns:repeat(3,1fr);
    text-align:center;
    font-size:12px;
    gap:4px;
}
.rider-stats b {
    display:block;
    font-size:15px;
}
.periods {
    display:grid;
    grid-template-columns:repeat(4,1fr);
    text-align:center;
    margin-top:10px;
    font-size:12px;
}
.weekly {
    border:3px solid #111;
    border-radius:16px;
    padding:10px;
    margin:20px 0;
}
.weekly table {
    width:100%;
    border-collapse:collapse;
    font-size:12px;
}
.weekly th, .weekly td {
    border-bottom:1px solid #ddd;
    padding:6px;
    text-align:center;
}
.time {
    text-align:center;
    color:#555;
    font-size:13px;
    margin:8px 0;
}
@media(max-width:420px) {
    .rider-grid { grid-template-columns:1fr; }
}
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

function pct(now, target) {
    if (!target || target <= 0) return 0;
    return Math.min(100, Math.round((now / target) * 100));
}

function setFilter(v) {
    FILTER = v;
    render();
}

function setSort() {
    SORT_DESC = !SORT_DESC;
    render();
}

async function loadData() {
    const res = await fetch("data.json?time=" + Date.now());
    DATA = await res.json();
    render();
}

function render() {
    const d = DATA;
    if (!d) return;

    document.getElementById("areaNow").innerText = `(${d.area} 보고있는 권역)`;
    document.getElementById("timeNow").innerText = `마지막 업데이트 ${d.updatedAt} | 영업일 ${d.businessDate}`;

    document.getElementById("areaTabs").innerHTML = d.areas.map(a => `
        <button class="${a === d.area ? 'active' : ''}">${a}</button>
    `).join("");

    const weeklyComplete = d.weekly.reduce((s,x)=>s+x.totalComplete,0);
    const weeklyReject = d.weekly.reduce((s,x)=>s+x.totalReject,0);
    const weeklyCancel = d.weekly.reduce((s,x)=>s+x.totalCancel,0);
    const weeklyRate = weeklyComplete + weeklyReject === 0 ? 100 : Math.round((weeklyComplete / (weeklyComplete + weeklyReject)) * 1000) / 10;
    const weeklySpare = Math.floor(weeklyComplete * 2 / 98) - weeklyReject;

    document.getElementById("weekComplete").innerText = weeklyComplete;
    document.getElementById("weekReject").innerText = `${weeklyReject}/${weeklyCancel}`;
    document.getElementById("weekRate").innerText = `${weeklyRate}% / ${weeklySpare}`;

    document.getElementById("dayComplete").innerText = d.total.complete;
    document.getElementById("dayReject").innerText = `${d.total.reject}/${d.total.cancel}`;
    document.getElementById("dayRate").innerText = `${d.total.acceptRate}%`;
    document.getElementById("currentPeriod").innerText = d.currentPeriodLabel;

    document.getElementById("sonicTotal").innerText = d.teams["소닉팀"] ? d.teams["소닉팀"].summary.complete : 0;
    document.getElementById("dalseoTotal").innerText = d.teams["달서팀"] ? d.teams["달서팀"].summary.complete : 0;

    document.getElementById("teamGoals").innerHTML = Object.entries(d.teams).map(([team, obj]) => {
        const s = obj.summary;
        const t = obj.targets;
        return `
        <div class="goal-card">
            <div class="section-title">${team} 완료총량 / 달성해야하는 총량</div>
            ${["morning","afternoon","evening","midnight"].map(p => `
                <div class="goal-row">
                    <div>${p === "morning" ? "오전" : p === "afternoon" ? "오후" : p === "evening" ? "저녁" : "심야"}</div>
                    <div class="bar"><div class="fill" style="width:${pct(s[p], t[p])}%"></div></div>
                    <div>${s[p]}/${t[p]}</div>
                </div>
            `).join("")}
        </div>`;
    }).join("");

    document.querySelectorAll(".filter-row button").forEach(b => b.classList.remove("active"));
    document.getElementById("f" + FILTER).classList.add("active");

    let riders = [...d.riders];
    if (FILTER !== "전체") riders = riders.filter(r => r.team === FILTER);
    riders.sort((a,b) => SORT_DESC ? b.complete - a.complete : a.complete - b.complete);

    document.getElementById("riderGrid").innerHTML = riders.map(r => `
        <div class="rider-card ${r.complete > 0 ? 'green' : ''}">
            ${r.warning ? '<div class="warn">⚠ 수락률</div>' : ''}
            <div class="rider-name">${r.name}</div>
            <div class="rider-stats">
                <div>완료<b>${r.complete}</b></div>
                <div>거절/취소<b>${r.reject}/${r.cancel}</b></div>
                <div>수락률<b>${r.acceptRate}%</b></div>
            </div>
            <div class="periods">
                <div>오전<br>${r.morning}</div>
                <div>오후<br>${r.afternoon}</div>
                <div>저녁<br>${r.evening}</div>
                <div>심야<br>${r.midnight}</div>
            </div>
        </div>
    `).join("");

    document.getElementById("weeklyTable").innerHTML = d.weekly.slice().reverse().map(w => `
        <tr>
            <td>${w.businessDate}</td>
            <td>${w.totalComplete}</td>
            <td>${w.totalReject}</td>
            <td>${w.acceptRate}%</td>
            <td>${w.spareRejects}</td>
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

    subprocess.run(["git", "add", "data.json", "index.html", "d_a.py"], cwd=BASE_DIR)

    if WEEKLY_FILE.exists():
        subprocess.run(["git", "add", "weekly.json"], cwd=BASE_DIR)

    commit_result = subprocess.run(
        ["git", "commit", "-m", "auto update"],
        cwd=BASE_DIR,
        capture_output=True,
        text=True
    )

    if commit_result.returncode != 0:
        print("커밋할 변경사항 없음 또는 커밋 생략")
        print(commit_result.stdout)
        print(commit_result.stderr)
        return

    push_result = subprocess.run(
        ["git", "push"],
        cwd=BASE_DIR,
        capture_output=True,
        text=True
    )

    print(push_result.stdout)
    print(push_result.stderr)


def main():
    print("배민비즈 창을 엽니다.")

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(BASE_DIR / "chrome_profile"),
            headless=False,
            viewport={"width": 1400, "height": 900},
        )

        page = browser.new_page()
        page.goto("https://deliverycenter.baemin.com")

        print("")
        print("1. 열린 창에서 배민비즈 로그인하세요.")
        print("2. 기사 실적 페이지까지 이동하세요.")
        print("3. 준비되면 이 CMD 창에서 Enter 누르세요.")
        input("Enter 대기 중...")

        while True:
            try:
                print("")
                print("===================================")
                print("데이터 수집 시작")
                print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

                riders = collect_data(page)

                print(f"수집된 전체 기사 수: {len(riders)}")
                print("앞 10명 이름:")
                print([r.get("name") for r in riders[:10]])

                raw_total_complete = 0
                for r in riders:
                    raw_total_complete += r.get("deliveryAcceptanceCount", {}).get("complete", 0)

                print(f"API 원본 전체 완료 합계: {raw_total_complete}")

                data = make_dashboard_data(riders)

                save_weekly_if_close(data)
                data["weekly"] = load_weekly()

                save_json(data)
                save_html()
                git_push()

                print(f"대시보드 전체 완료: {data['total']['complete']}건")
                print(f"대시보드 수락률: {data['total']['acceptRate']}%")
                print("업데이트 완료")
                print(f"{REFRESH_SECONDS}초 후 다시 수집합니다.")

            except Exception as e:
                print("오류 발생:")
                print(e)

            time.sleep(REFRESH_SECONDS)


if __name__ == "__main__":
    main()
