import json
import math
import re
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from playwright.sync_api import sync_playwright
from firebase_admin import db
from firebase_uploader import init_firebase, upload_json

AUTO_GIT_PUSH = False
REFRESH_SECONDS = 60
MAX_PAGES = 20
TARGET_ACCEPT_RATE = 80

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data_suseongc.json"
HTML_FILE = BASE_DIR / "index.html"
WEEKLY_FILE = BASE_DIR / "weekly_suseongc.json"

AREA_NAME = "수성C"

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

TEAM_ORDER = ["마음팀", "BDMJ팀"]

AREA_CONFIG = {
    "수성C": {
        "마음팀": 1,
        "BDMJ팀": 3,
    }
}

DAY_TARGETS = {
    0: [22, 21, 32, 25],
    1: [22, 21, 32, 25],
    2: [22, 21, 32, 25],
    3: [22, 21, 32, 25],
    4: [25, 22, 34, 29],
    5: [31, 23, 38, 28],
    6: [32, 24, 37, 27],
}

SPECIAL_DAY_TARGET_WEEKDAY = {
    "2026-05-25": 6,
    "2026-06-03": 6,
}

PERIODS = ["morning", "afternoon", "evening", "midnight"]
PERIOD_LABELS = {
    "morning": "오전피크",
    "afternoon": "오후논피크",
    "evening": "저녁피크",
    "midnight": "심야논피크",
}


def split_hourly_by_sla(hourly, date_value=None):
    h = list(hourly or [])[:24]
    if len(h) < 24:
        h += [0] * (24 - len(h))
    if date_value is None:
        date_value = business_date(datetime.now())
    weekend = date_value.weekday() >= 5

    # 미포함은 표시만 하고 게이지/목표 달성 계산에는 절대 포함하지 않음
    morning_excluded = sum(h[6:10])       # 06,07,08,09
    midnight_excluded = sum(h[0:6])      # 00,01,02,03,04,05

    if weekend:
        morning = sum(h[10:14])          # 토일 10,11,12,13
        afternoon = sum(h[14:17])        # 토일 14,15,16
    else:
        morning = sum(h[10:13])          # 평일 10,11,12
        afternoon = sum(h[13:17])        # 평일 13,14,15,16

    evening = sum(h[17:20])              # 17,18,19
    midnight = sum(h[20:24])             # 20,21,22,23

    return {
        "morning": morning,
        "afternoon": afternoon,
        "evening": evening,
        "midnight": midnight,
        "morningExcluded": morning_excluded,
        "midnightExcluded": midnight_excluded,
        "excluded": morning_excluded + midnight_excluded,
    }

def business_date(now):
    if now.hour < 6:
        return (now - timedelta(days=1)).date()
    return now.date()


def current_period(now):
    h = now.hour
    weekend = now.weekday() >= 5

    # SLA 포함 구간 기준입니다.
    # 06~09, 00~05는 미포함 표시 구간이라 게이지/달성률에는 넣지 않습니다.
    if weekend:
        if 10 <= h < 14:
            return "morning"
        if 14 <= h < 17:
            return "afternoon"
    else:
        if 10 <= h < 13:
            return "morning"
        if 13 <= h < 17:
            return "afternoon"

    if 17 <= h < 20:
        return "evening"

    return "midnight"

def calc_accept_rate(complete, reject, cancel=0, rider_fault=0):
    bad_total = reject + cancel + rider_fault
    total = complete + bad_total
    if total == 0:
        return 100
    return round((complete / total) * 100, 1)


def spare_rejects(complete, reject, cancel=0, rider_fault=0):
    bad_total = reject + cancel + rider_fault
    if complete <= 0:
        return 0
    max_bad_total = math.floor(complete * 0.25)
    return max_bad_total - bad_total


TEAM_MAP_CACHE = None


def team_of(name):
    global TEAM_MAP_CACHE

    if TEAM_MAP_CACHE is None:
        try:
            init_firebase()

            TEAM_MAP_CACHE = (
                db.reference("/settings/suseongc/teamMap").get()
                or {}
            )

            print(f"teamMap 로드 완료: {len(TEAM_MAP_CACHE)}명")

        except Exception as e:
            print("teamMap 로드 실패:", e)
            TEAM_MAP_CACHE = {}

    return TEAM_MAP_CACHE.get(name, "마음팀")


def to_int(value):
    try:
        return int(str(value).replace(",", "").strip())
    except Exception:
        return 0


def norm(value):
    return str(value).replace("\u200b", "").replace("\ufeff", "").strip()


def status_online(status):
    return str(status).replace(" ", "").strip() == "운행중"


def is_phone(value):
    v = norm(value)
    return "010-" in v or "010" in v


def is_bad_name(value):
    v = norm(value)
    bad = {
        "", "-", "이름", "운행상태", "휴대폰번호", "완료", "거절",
        "배차취소", "배달취소(라이더귀책)", "아이디", "합계",
        "아침점심피크", "오후논피크", "저녁피크", "심야논피크",
        "운행중", "운행 중", "운행 종료", "운행종료",
        "개인정보처리방침", "이용약관", "고객센터", "공지사항",
        "회사소개", "사업자정보", "서비스이용약관", "위치기반서비스이용약관",
        "개인정보", "처리방침", "푸터", "footer",
    }
    return v in bad or is_phone(v) or v.isdigit() or v.endswith("시")

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


def read_dom_rows(page):
    """
    배민 화면이 div-grid/고정열/가로스크롤로 바뀌어도 헤더의 x좌표를 기준으로
    00~23시 값을 직접 매칭합니다. offset 추정 금지.
    """
    return page.evaluate(r"""
    () => {
      const phoneRe = /010[-\s]?\d{3,4}[-\s]?\d{4}/;
      const hourRe = /^(?:[01]?\d|2[0-3])\s*시$/;
      const out = [];
      const seen = new Set();

      function isVisible(el){
        const r = el.getBoundingClientRect();
        const s = window.getComputedStyle(el);
        return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
      }
      function textOf(el){ return (el.innerText || el.textContent || '').trim(); }
      function norm(t){ return String(t||'').replace(/\u200b|\ufeff/g,'').trim(); }
      function isIntText(t){ return /^-?\d{1,5}$/.test(String(t||'').replace(/,/g,'').trim()); }
      function toInt(t){ const n = parseInt(String(t||'0').replace(/,/g,'').trim(),10); return Number.isFinite(n)?n:0; }

      function isLeafText(el){
        const t = norm(textOf(el));
        if (!t || !isVisible(el)) return false;
        for (const c of Array.from(el.children || [])) {
          const ct = norm(textOf(c));
          if (ct && ct === t && isVisible(c)) return false;
        }
        return true;
      }

      const badLegalNames = new Set(['개인정보처리방침','이용약관','고객센터','공지사항','회사소개','사업자정보','서비스이용약관','위치기반서비스이용약관']);

      const nodes = Array.from(document.querySelectorAll('body *')).filter(isLeafText).map(el => {
        const r = el.getBoundingClientRect();
        return {el, text:norm(textOf(el)), left:r.left, right:r.right, top:r.top, bottom:r.bottom, cx:r.left+r.width/2, cy:r.top+r.height/2, width:r.width, height:r.height};
      });

      const hourHeaders = [];
      for (const n of nodes) {
        const m = n.text.match(hourRe);
        if (!m) continue;
        const h = parseInt(n.text.replace(/\D/g,''),10);
        if (h >= 0 && h <= 23) hourHeaders.push({...n, hour:h});
      }
      // 같은 시간 헤더가 여러 번 잡히면 실제 기사행 바로 위의 가장 아래쪽 헤더를 사용
      const hourMap = {};
      for (const h of hourHeaders) {
        if (!hourMap[h.hour] || h.top > hourMap[h.hour].top) hourMap[h.hour] = h;
      }
      const hours = [];
      for (let h=0; h<24; h++) if (hourMap[h]) hours.push(hourMap[h]);

      function findHeader(...names){
        let candidates = nodes.filter(n => names.some(name => n.text === name || n.text.replace(/\s/g,'') === name.replace(/\s/g,'')));
        // 너무 위쪽 메뉴/필터가 아니라 기사행 바로 위쪽 실제 컬럼 헤더를 우선 사용
        candidates = candidates.filter(n => n.width > 0 && n.height > 0).sort((a,b)=>b.top-a.top);
        return candidates[0] || null;
      }
      const metricHeaders = {
        complete: findHeader('완료'),
        reject: findHeader('거절'),
        cancel: findHeader('배차취소', '배달취소'),
        riderFault: findHeader('배달취소(라이더귀책)', '라이더귀책')
      };

      // 시간 헤더를 20개 이상 못 찾으면 기존 파서가 처리하도록 raw lines로 반환
      if (hours.length < 20) {
        const phoneNodes = nodes.filter(n => phoneRe.test(n.text));
        for (const p of phoneNodes) {
          const key = (p.text.match(phoneRe)?.[0] || '').replace(/\s/g,'');
          if (!key || seen.has(key)) continue;
          seen.add(key);
          const rowNodes = nodes.filter(x => Math.abs(x.cy - p.cy) <= 12 && x.height > 0 && x.height <= 80 && x.text.length <= 40)
                              .sort((a,b)=> Math.abs(a.left-b.left)>2 ? a.left-b.left : a.top-b.top);
          out.push({__raw: rowNodes.map(x=>x.text)});
        }
        return out;
      }

      const phoneNodes = nodes.filter(n => phoneRe.test(n.text));
      for (const phoneNode of phoneNodes) {
        const phone = phoneNode.text.match(phoneRe)?.[0];
        if (!phone) continue;
        const key = phone.replace(/\s/g,'');
        if (seen.has(key)) continue;
        seen.add(key);

        const row = nodes.filter(x => Math.abs(x.cy - phoneNode.cy) <= 13 && x.height > 0 && x.height <= 80 && x.text.length <= 50)
                         .sort((a,b)=> Math.abs(a.left-b.left)>2 ? a.left-b.left : a.top-b.top);

        const texts = row.map(x=>x.text);
        let status = texts.some(t => t.replace(/\s/g,'') === '운행중') ? '운행중' : '운행 종료';

        let name = '';
        const phoneIdx = row.findIndex(x => phoneRe.test(x.text));
        for (let i = phoneIdx - 1; i >= 0; i--) {
          const t = row[i].text;
          if (!t || phoneRe.test(t) || /^\d+$/.test(t) || t.includes('운행') || t.includes('휴대폰') || t.includes('이름')) continue;
          name = t; break;
        }
        if (!name || badLegalNames.has(name)) continue;

        const rightNums = row.filter(x => x.cx > phoneNode.cx + 10 && isIntText(x.text));

        // 핵심: 요약 실적 숫자는 00~23시 시간대 컬럼 앞에 있는 숫자만 사용합니다.
        // 이전 버전은 오른쪽 숫자를 전부 섞어서 00시/01시/02시 값을 완료·거절로 오인했습니다.
        const firstHourLeft = Math.min(...hours.map(h => h.left));
        let metricCells = row
          .filter(x => x.cx > phoneNode.cx + 10 && x.right < firstHourLeft - 4 && isIntText(x.text))
          .sort((a,b) => a.left - b.left);

        // 배민 화면 폭/고정열 때문에 firstHourLeft 기준이 실패할 때만 전체 오른쪽 숫자 앞부분으로 fallback
        if (metricCells.length < 7) {
          metricCells = rightNums.slice(0, 7);
        }

        // 배민비즈 도출 기준:
        // 완료 = 푸드 완료 + B마트 완료 + 배민스토어 완료 (또는 배민의 전체 완료 칸)
        // 수락률 실패값 = 푸드 거절 + 푸드 취소 + 라이더귀책만 사용
        // B마트/배민스토어 거절·취소는 반영하지 않습니다.
        const metricNums = metricCells.map(x => toInt(x.text));
        // 배민비즈 현재 컬럼은 서비스별로 묶여 있습니다.
        // [푸드 완료, 푸드 거절, 푸드 취소, B마트 완료, B마트 거절, B마트 취소, 배민스토어 완료, ...]
        // 수락률 실패값은 반드시 푸드 거절/푸드 취소만 사용해야 하므로 1,2번을 사용합니다.
        // 배민비즈 현재 화면은 시간대 컬럼 앞 요약 숫자가 보통
        // [푸드완료, B마트완료, 배민스토어완료, 전체완료, 기타/예약, 푸드거절, 푸드취소, 라이더귀책 ...]
        // 순서로 잡힙니다. 이전 버전은 1,2번을 거절/취소로 읽어서 기사카드와 total reject/cancel이 0으로 올라갔습니다.
        const foodComplete = metricNums[0] || 0;
        const bmartComplete = metricNums[1] || 0;
        const storeComplete = metricNums[2] || 0;
        let complete = metricNums[3] || (foodComplete + bmartComplete + storeComplete);

        // 수락률 실패값은 푸드 거절/푸드 취소만 사용합니다.
        // 우선 검증된 위치(5,6)를 사용하고, 예전/다른 레이아웃 fallback으로 (1,2)를 사용합니다.
        let reject = metricNums[5] || 0;
        let cancel = metricNums[6] || 0;
        let riderFault = metricNums[7] || metricNums[8] || 0;

        if (reject === 0 && cancel === 0 && metricNums.length >= 3) {
          // 구형 레이아웃 fallback: [푸드완료, 푸드거절, 푸드취소, ...]
          const altReject = metricNums[1] || 0;
          const altCancel = metricNums[2] || 0;
          const altComplete = metricNums[0] || 0;
          // 1,2번이 B마트/스토어 완료처럼 보이지 않는 경우에만 fallback 적용
          if ((altReject + altCancel) > 0 && (altReject + altCancel) <= Math.max(altComplete * 2, 20)) {
            reject = altReject;
            cancel = altCancel;
            riderFault = metricNums[3] || riderFault;
          }
        }

        const hourly = Array(24).fill(0);
        for (const hh of hours) {
          // 해당 시간 헤더 x좌표와 가장 가까운 숫자 셀을 같은 행에서 선택
          let best = null;
          for (const cell of row) {
            if (!isIntText(cell.text)) continue;
            if (cell.cx <= phoneNode.cx) continue;
            const dx = Math.abs(cell.cx - hh.cx);
            if (dx > Math.max(28, hh.width * 1.8)) continue;
            const score = dx + Math.abs(cell.width - hh.width) * 0.05;
            if (!best || score < best.score) best = {cell, score};
          }
          if (best) hourly[hh.hour] = toInt(best.cell.text);
        }

        // 완료 컬럼이 배민 UI 변경으로 잘못 잡히는 경우가 있어
        // 검증된 00~23시 헤더 x좌표 매칭값의 합계를 완료 기준으로 사용합니다.
        // 수락률 분모의 완료도 이 값으로 계산됩니다.
        const hourlyTotal = hourly.reduce((a, b) => a + b, 0);
        if (hourlyTotal > 0) {
          complete = hourlyTotal;
        }

        let userId = '';
        for (let i=row.length-1; i>phoneIdx; i--) {
          const t = row[i].text;
          if (!t || isIntText(t) || hourRe.test(t) || t.includes('개인정보')) continue;
          if (t === phone || t.includes('운행')) continue;
          userId = t; break;
        }

        out.push({name, phone, userId, status, complete, reject, cancel, riderFault, hourly, __raw:texts});
      }
      return out;
    }
    """)

def parse_row_lines(row_lines):
    lines = [norm(x) for x in row_lines if norm(x)]
    phone_idx = None

    for idx, line in enumerate(lines):
        if is_phone(line):
            phone_idx = idx
            break

    if phone_idx is None:
        return None

    phone = lines[phone_idx]

    status = "운행 종료"
    for item in lines[:phone_idx + 1]:
        if item.replace(" ", "") == "운행중":
            status = "운행중"
            break

    name = ""
    for item in reversed(lines[:phone_idx]):
        if not is_bad_name(item):
            name = item
            break

    if not name:
        return None
    if is_bad_name(name):
        return None

    if phone_idx + 35 >= len(lines):
        return None

    food_complete = to_int(lines[phone_idx + 1])
    bmart_complete = to_int(lines[phone_idx + 2])
    store_complete = to_int(lines[phone_idx + 3])
    complete = to_int(lines[phone_idx + 4])

    reject = to_int(lines[phone_idx + 5])
    cancel = to_int(lines[phone_idx + 6])
    rider_fault = to_int(lines[phone_idx + 7])

    hourly = []
    for h in range(24):
        hourly.append(to_int(lines[phone_idx + 12 + h]))

    sla = split_hourly_by_sla(hourly)
    morning = sla["morning"]
    afternoon = sla["afternoon"]
    evening = sla["evening"]
    midnight = sla["midnight"]
    morning_excluded = sla["morningExcluded"]
    midnight_excluded = sla["midnightExcluded"]
    excluded = sla["excluded"]

    user_id = ""
    for item in reversed(lines[phone_idx + 36:]):
        if not str(item).isdigit() and not is_bad_name(item):
            user_id = item
            break

    is_online = status_online(status)

    return {
        "name": name,
        "phone": phone,
        "userId": user_id,
        "team": team_of(name),
        "status": "운행중" if is_online else "운행 종료",
        "isOnline": is_online,
        "complete": complete,
        "reject": reject,
        "cancel": cancel,
        "riderFault": rider_fault,
        "morning": morning,
        "afternoon": afternoon,
        "evening": evening,
        "midnight": midnight,
        "morningExcluded": morning_excluded,
        "midnightExcluded": midnight_excluded,
        "excluded": excluded,
        "hourly": hourly,
        "acceptRate": calc_accept_rate(complete, reject, cancel, rider_fault),
        "warning": calc_accept_rate(complete, reject, cancel, rider_fault) < 80,
    }

def parse_dom_rows(row_groups):
    riders = []
    for group in row_groups:
        if isinstance(group, dict) and group.get("__raw") and not group.get("hourly"):
            rider = parse_row_lines(group.get("__raw") or [])
        elif isinstance(group, dict):
            hourly = group.get("hourly") or [0] * 24
            sla = split_hourly_by_sla(hourly)
            complete = to_int(group.get("complete", 0))
            reject = to_int(group.get("reject", 0))
            cancel = to_int(group.get("cancel", 0))
            rider_fault = to_int(group.get("riderFault", 0))
            is_online = status_online(group.get("status", ""))
            rider = {
                "name": group.get("name", ""),
                "phone": group.get("phone", ""),
                "userId": group.get("userId", ""),
                "team": team_of(group.get("name", "")),
                "status": "운행중" if is_online else "운행 종료",
                "isOnline": is_online,
                "complete": complete,
                "reject": reject,
                "cancel": cancel,
                "riderFault": rider_fault,
                "morning": sla["morning"],
                "afternoon": sla["afternoon"],
                "evening": sla["evening"],
                "midnight": sla["midnight"],
                "morningExcluded": sla["morningExcluded"],
                "midnightExcluded": sla["midnightExcluded"],
                "excluded": sla["excluded"],
                "hourly": hourly,
                "acceptRate": calc_accept_rate(complete, reject, cancel, rider_fault),
                "warning": calc_accept_rate(complete, reject, cancel, rider_fault) < 80,
            }
        else:
            rider = parse_row_lines(group)
        if rider and rider.get("name") and rider.get("phone") and not is_bad_name(rider.get("name")):
            riders.append(rider)
    return riders

def collect_all_pages_by_dom(page):
    base_url = page.url
    all_riders = []
    seen = set()

    for page_no in range(MAX_PAGES):
        target_url = set_page_number(base_url, page_no)
        print(f"{page_no + 1}페이지 이동: {target_url}")

        page.goto(target_url)
        page.wait_for_load_state("networkidle")
        time.sleep(1.5)

        if "size=100" not in page.url:
            fixed_url = set_page_number(page.url, page_no)
            print("100개 보기 강제 적용:", fixed_url)
            page.goto(fixed_url)
            page.wait_for_load_state("networkidle")
            time.sleep(1.5)

        row_groups = read_dom_rows(page)
        riders = parse_dom_rows(row_groups)

        print(f"{page_no + 1}페이지 DOM 행 수: {len(row_groups)}")
        print(f"{page_no + 1}페이지 읽은 기사 수: {len(riders)}")

        if page_no == 0 and len(riders) == 0:
            print("DOM 샘플:")
            for idx, row in enumerate(row_groups[:3]):
                print(idx, row[:20])

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
    rider_fault = sum(r["riderFault"] for r in rows)

    return {
        "complete": complete,
        "reject": reject,
        "cancel": cancel,
        "riderFault": rider_fault,
        "morning": sum(r["morning"] for r in rows),
        "afternoon": sum(r["afternoon"] for r in rows),
        "evening": sum(r["evening"] for r in rows),
        "midnight": sum(r["midnight"] for r in rows),
        "morningExcluded": sum(r.get("morningExcluded", 0) for r in rows),
        "midnightExcluded": sum(r.get("midnightExcluded", 0) for r in rows),
        "excluded": sum(r.get("excluded", 0) for r in rows),
        "count": len(rows),
        "onlineCount": sum(1 for r in rows if r.get("isOnline")),
        "acceptRate": calc_accept_rate(complete, reject, cancel, rider_fault),
        "spareRejects": spare_rejects(complete, reject, cancel, rider_fault),
    }

def team_targets(now):
    bd = business_date(now)
    target_weekday = SPECIAL_DAY_TARGET_WEEKDAY.get(bd.strftime("%Y-%m-%d"), bd.weekday())
    base = dict(zip(PERIODS, DAY_TARGETS[target_weekday]))
    result = {}

    for team, sets in AREA_CONFIG[AREA_NAME].items():
        result[team] = {p: math.ceil(base[p] * sets) for p in PERIODS}
        result[team]["total"] = sum(result[team][p] for p in PERIODS)
        result[team]["sets"] = sets

    return result


def load_weekly():
    try:
        if WEEKLY_FILE.exists():
            with open(WEEKLY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        print("weekly 파일 손상 - 새로 생성")
    return []

def week_start_wednesday(date_value):
    """수요일~화요일 주차 기준의 시작일을 반환합니다."""
    days_since_wed = (date_value.weekday() - 2) % 7
    return date_value - timedelta(days=days_since_wed)


def current_week_dates(now):
    start = week_start_wednesday(business_date(now))
    return [start + timedelta(days=i) for i in range(7)]


def target_total_by_period_for_date(date_value):
    target_weekday = SPECIAL_DAY_TARGET_WEEKDAY.get(date_value.strftime("%Y-%m-%d"), date_value.weekday())
    base = dict(zip(PERIODS, DAY_TARGETS[target_weekday]))
    total_sets = sum(AREA_CONFIG[AREA_NAME].values())
    return {p: math.ceil(base[p] * total_sets) for p in PERIODS}


def weekly_summary(weekly_rows, now):
    week_dates = current_week_dates(now)
    date_keys = [str(d) for d in week_dates]
    by_date = {x.get("businessDate"): x for x in weekly_rows}

    days = []
    total_complete = 0
    total_reject = 0
    total_cancel = 0
    total_rider_fault = 0
    total_periods = {p: 0 for p in PERIODS}
    total_period_targets = {p: 0 for p in PERIODS}
    total_excluded = 0
    total_morning_excluded = 0
    total_midnight_excluded = 0

    labels = ["수", "목", "금", "토", "일", "월", "화"]
    period_names = {
        "morning": "오전피크",
        "afternoon": "오후논피크",
        "evening": "저녁피크",
        "midnight": "심야논피크",
    }

    for label, date_value, date_key in zip(labels, week_dates, date_keys):
        row = by_date.get(date_key, {})
        complete = to_int(row.get("totalComplete", 0))
        reject = to_int(row.get("totalReject", 0))
        cancel = to_int(row.get("totalCancel", 0))
        rider_fault = to_int(row.get("riderFault", 0))
        bad_total = reject + cancel + rider_fault
        morning_excluded = to_int(row.get("morningExcluded", 0))
        midnight_excluded = to_int(row.get("midnightExcluded", 0))
        excluded = to_int(row.get("excluded", row.get("totalExcluded", morning_excluded + midnight_excluded)))
        period_targets = row.get("periodTargets") or target_total_by_period_for_date(date_value)

        period_rows = []
        for p in PERIODS:
            done = to_int(row.get(p, 0))
            goal = to_int(period_targets.get(p, 0))
            failed = bool(row) and goal > 0 and done < goal
            total_periods[p] += done
            total_period_targets[p] += goal
            period_rows.append({
                "key": p,
                "label": period_names[p],
                "done": done,
                "goal": goal,
                "failed": failed,
            })

        total_complete += complete
        total_reject += reject
        total_cancel += cancel
        total_rider_fault += rider_fault
        total_excluded += excluded
        total_morning_excluded += morning_excluded
        total_midnight_excluded += midnight_excluded

        days.append({
            "label": label,
            "businessDate": date_key,
            "complete": complete,
            "reject": reject,
            "cancel": cancel,
            "riderFault": rider_fault,
            "badTotal": bad_total,
            "morningExcluded": morning_excluded,
            "midnightExcluded": midnight_excluded,
            "excluded": excluded,
            "acceptRate": row.get("acceptRate", calc_accept_rate(complete, reject, cancel, rider_fault)),
            "spareRejects": spare_rejects(complete, reject, cancel, rider_fault),
            "periods": period_rows,
            "closedAt": row.get("closedAt", ""),
            "hasData": bool(row),
        })

    return {
        "startDate": date_keys[0],
        "endDate": date_keys[-1],
        "complete": total_complete,
        "reject": total_reject,
        "cancel": total_cancel,
        "riderFault": total_rider_fault,
        "badTotal": total_reject + total_cancel + total_rider_fault,
        "acceptRate": calc_accept_rate(total_complete, total_reject, total_cancel, total_rider_fault),
        "spareRejects": spare_rejects(total_complete, total_reject, total_cancel, total_rider_fault),
        "periodTotals": total_periods,
        "periodTargets": total_period_targets,
        "morningExcluded": total_morning_excluded,
        "midnightExcluded": total_midnight_excluded,
        "excluded": total_excluded,
        "days": days,
    }

def save_weekly_if_close(data):
    weekly = load_weekly()
    today_key = data["businessDate"]

    target_date = datetime.strptime(today_key, "%Y-%m-%d").date()
    period_targets = target_total_by_period_for_date(target_date)

    row = {
        "businessDate": today_key,
        "closedAt": data["updatedAt"],
        "totalComplete": data["total"]["complete"],
        "totalReject": data["total"]["reject"],
        "totalCancel": data["total"]["cancel"],
        "riderFault": data["total"]["riderFault"],
        "morning": data["total"]["morning"],
        "afternoon": data["total"]["afternoon"],
        "evening": data["total"]["evening"],
        "midnight": data["total"]["midnight"],
        "morningExcluded": data["total"].get("morningExcluded", 0),
        "midnightExcluded": data["total"].get("midnightExcluded", 0),
        "excluded": data["total"].get("excluded", 0),
        "periodTargets": period_targets,
        "acceptRate": data["total"]["acceptRate"],
        "spareRejects": data["total"]["spareRejects"],
    }

    def same_stats(a, b):
        return (
            to_int(a.get("totalComplete", 0)) == to_int(b.get("totalComplete", 0)) and
            to_int(a.get("totalReject", 0)) == to_int(b.get("totalReject", 0)) and
            to_int(a.get("totalCancel", 0)) == to_int(b.get("totalCancel", 0)) and
            to_int(a.get("riderFault", 0)) == to_int(b.get("riderFault", 0)) and
            to_int(a.get("morning", 0)) == to_int(b.get("morning", 0)) and
            to_int(a.get("afternoon", 0)) == to_int(b.get("afternoon", 0)) and
            to_int(a.get("evening", 0)) == to_int(b.get("evening", 0)) and
            to_int(a.get("midnight", 0)) == to_int(b.get("midnight", 0)) and
            to_int(a.get("excluded", 0)) == to_int(b.get("excluded", 0))
        )

    found = False

    for i, old in enumerate(weekly):
        if old.get("businessDate") == today_key:
            weekly[i] = row
            found = True
            break

    if not found:
        if weekly and same_stats(weekly[-1], row):
            print("전날 데이터와 동일해서 weekly 새 날짜 저장 건너뜀")
        else:
            weekly.append(row)

    weekly = sorted(weekly, key=lambda x: x.get("businessDate", ""))[-31:]

    with open(WEEKLY_FILE, "w", encoding="utf-8") as f:
        json.dump(weekly, f, ensure_ascii=False, indent=2)

def make_data(riders):
    now = datetime.now()
    riders.sort(key=lambda x: (not x["isOnline"], x["name"]))

    targets = team_targets(now)
    teams = {}

    for team in TEAM_ORDER:
        rows = [r for r in riders if r["team"] == team]
        teams[team] = {
            "summary": summary(rows),
            "targets": targets[team],
            "riders": rows,
        }

    weekly = load_weekly()

    return {
    "area": AREA_NAME,
    "areas": ["마음 달서A", "달서B", "수성C"],
    "teamOrder": TEAM_ORDER,
    "updatedAt": now.strftime("%Y-%m-%d %H:%M:%S"),
    "businessDate": str(business_date(now)),
    "currentPeriod": current_period(now),
    "currentPeriodLabel": PERIOD_LABELS[current_period(now)],
    "targetAcceptRate": TARGET_ACCEPT_RATE,
    "total": summary(riders),
    "teams": teams,
    "riders": riders,
    "weekly": weekly,
    "weeklySummary": weekly_summary(weekly, now),
    }

def save_json(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    try:
        upload_json("data_suseongc.json", "/live/suseongc")
        upload_json("weekly_suseongc.json", "/weekly/suseongc")
        print("Firebase 업로드 완료")
    except Exception as e:
        print("Firebase 업로드 실패")
        print(e)


def save_html():
    return


def git_push():
    if not AUTO_GIT_PUSH:
        return

    subprocess.run(["git", "add", "data_suseongc.json", "index.html", "s_c.py", "logo.png"], cwd=BASE_DIR)

    if WEEKLY_FILE.exists():
        subprocess.run(["git", "add", "weekly_suseongc.json"], cwd=BASE_DIR)

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
    riders = collect_all_pages_by_dom(page)

    if len(riders) == 0:
        print("기사 데이터를 못 읽었습니다.")
        return

    data = make_data(riders)
    save_weekly_if_close(data)
    weekly = load_weekly()
    data["weekly"] = weekly
    data["weeklySummary"] = weekly_summary(weekly, datetime.now())

    save_json(data)
    save_html()
    git_push()

    print(f"업로드 완료: {data['updatedAt']}")
    print(f"전체 기사 수: {data['total']['count']}")
    print(f"접속중 기사 수: {data['total']['onlineCount']}")
    print(f"마음팀 접속중: {data['teams']['마음팀']['summary']['onlineCount']}")
    print(f"BDMJ팀 접속중: {data['teams']['BDMJ팀']['summary']['onlineCount']}")
    print(f"전체 완료: {data['total']['complete']}")
    print(f"전체 거절: {data['total']['reject']}")
    print(f"전체 취소: {data['total']['cancel']}")
    print(f"수락률: {data['total']['acceptRate']}%")


def main():
    global TEAM_MAP_CACHE
    print("SUPERSONIC 수성C DOM 자동 수집기")

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(BASE_DIR / "chrome_profile_suseongc"),
            headless=False,
            viewport={"width": 1400, "height": 900},
        )

        page = browser.pages[0]

        page.goto(
            "https://deliverycenter.baemin.com/delivery/history?page=0&size=100&orderName=name&orderBy=asc&name=&userId=&phoneNumber=&riderStatus="
        )

        print("1. 열린 배민비즈 창에서 로그인하세요.")
        print("2. 수성C 기사 실적 페이지로 이동하세요.")
        print("3. 100개 보기로 맞추세요.")
        print("4. 준비되면 CMD에서 Enter 누르세요.")

        input("Enter 대기 중...")

        while True:
            TEAM_MAP_CACHE = None
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
