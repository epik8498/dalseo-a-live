import json
import math
import re
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from firebase_admin import db
from firebase_uploader import init_firebase

from playwright.sync_api import sync_playwright
from firebase_uploader import upload_json

AUTO_GIT_PUSH = False
REFRESH_SECONDS = 60
MAX_PAGES = 20
TARGET_ACCEPT_RATE = 80

BACKGROUND_SAFE_ARGS = [
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--disable-extensions",
    "--mute-audio",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-features=CalculateNativeWinOcclusion,IntensiveWakeUpThrottling,MemorySaverMode",
]

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data_maeuma.json"
HTML_FILE = BASE_DIR / "index.html"
WEEKLY_FILE = BASE_DIR / "weekly_maeuma.json"

AREA_NAME = "마음 달서A"
TEAM_ORDER = []
AREA_CONFIG = {}
TEAM_MAP_PATH = ""
LIVE_PATH = ""
WEEKLY_PATH = ""
CURRENT_SLUG = ""
REQUIRED_TEAM_RIDERS = {}
TEAM_MAP_CACHE = None
VERIFIED_CENTER_CODE = None

CENTER_CONFIGS = [{'area': '마음 달서A',
  'slug': 'maeuma',
  'aliases': ['대구달서온나A(DP2509199364)', '대구달서온나A (DP2509199364)', '대구달서온나A', 'DP2509199364'],
  'center_code': 'DP2509199364',
  'team_order': ['마음1', '마음3'],
  'area_config': {'마음1': 5.5, '마음3': 4.5},
  'team_map_path': '/settings/maeuma/teamMap',
  'live_path': '/live/maeuma',
  'weekly_path': '/weekly/maeuma',
  'required_team_riders': {'마음3': ['김리현',
                                   '김민웅',
                                   '김원제',
                                   '김익한',
                                   '김재준',
                                   '남현우',
                                   '문재훈',
                                   '박명규',
                                   '박정현',
                                   '성동훈',
                                   '오세원',
                                   '윤종홍',
                                   '이우훈',
                                   '이정석',
                                   '이정호',
                                   '전재욱',
                                   '정은경',
                                   '정장훈',
                                   '정재균',
                                   '최영섭',
                                   '최종광',
                                   '최홍석',
                                   '추진태',
                                   '함영국',
                                   '현승희',
                                   '전재옥',
                                   '김래현',
                                   '김제헌',
                                   '이낙철']}},
 {'area': '달서B',
  'slug': 'maeum_dalseob',
  'aliases': ['대구달서B온나(DP2602028125)', '대구달서B온나 (DP2602028125)', '대구달서B온나', 'DP2602028125'],
  'center_code': 'DP2602028125',
  'team_order': ['소닉팀', '넘버팀', '마음팀'],
  'area_config': {'소닉팀': 2, '넘버팀': 5, '마음팀': 5},
  'team_map_path': '/settings/maeum_dalseob/teamMap',
  'live_path': '/live/maeum_dalseob',
  'weekly_path': '/weekly/maeum_dalseob',
  'required_team_riders': {'소닉팀': ['최경민',
                                   '윤규범',
                                   '신성욱',
                                   '박무성',
                                   '송득근',
                                   '정우혁',
                                   '김경섭',
                                   '장근영',
                                   '조윤환',
                                   '조승래',
                                   '정기정',
                                   '정규태',
                                   '장재근',
                                   '최지나',
                                   '이종필',
                                   '이정민',
                                   '이재상',
                                   '이재관',
                                   '윤철훈',
                                   '유영멸',
                                   '엄정철',
                                   '심재득',
                                   '신진학',
                                   '배준호',
                                   '박정민',
                                   '김주동',
                                   '김재현',
                                   '김상엽',
                                   '김동규',
                                   '권휘재',
                                   '최지용',
                                   '김종찬',
                                   '이상엽',
                                   '노우현',
                                   '박성우',
                                   '배재현',
                                   '신정훈',
                                   '최현준',
                                   '이부관'],
                           '넘버팀': ['유호성',
                                   '박세창',
                                   '강명원',
                                   '김수진',
                                   '배서후',
                                   '김요한',
                                   '김정근',
                                   '남승호',
                                   '이현재',
                                   '이윤재',
                                   '정수영',
                                   '장정석',
                                   '최영진',
                                   '임현석',
                                   '임승범',
                                   '이태훈',
                                   '이철우',
                                   '이재현',
                                   '이은성',
                                   '이영희',
                                   '이선노',
                                   '이동석',
                                   '우효상',
                                   '서강원',
                                   '한동훈',
                                   '마경민',
                                   '노재권',
                                   '남윤정',
                                   '남동욱',
                                   '김현준',
                                   '김태하',
                                   '김종희',
                                   '김용운',
                                   '김영천',
                                   '김명수',
                                   '김명한',
                                   '김동국',
                                   '권오현',
                                   '황홍섭',
                                   '강지은',
                                   '최윤호',
                                   '신명섭',
                                   '윤민석',
                                   '김애선',
                                   '이대겸',
                                   '김대운',
                                   '이헌재',
                                   '김병수',
                                   '이재헌',
                                   '한창목'],
                           '마음팀': ['임용우',
                                   '김강호',
                                   '김영우',
                                   '강지우',
                                   '이승훈',
                                   '박성림',
                                   '이영민',
                                   '손성곤',
                                   '구상훈',
                                   '박한울',
                                   '신가희',
                                   '박연호',
                                   '김형택',
                                   '김낙훈',
                                   '권영남',
                                   '이진복',
                                   '김석원',
                                   '길태빈',
                                   '김창범',
                                   '박광용',
                                   '성영길',
                                   '박원희',
                                   '최영우',
                                   '이전필',
                                   '이재현',
                                   '이강현',
                                   '김대한',
                                   '여세동',
                                   '신정하',
                                   '임지훈',
                                   '장민서',
                                   '임종현',
                                   '윤동근',
                                   '도수현',
                                   '김동현',
                                   '정동진',
                                   '정동수',
                                   '전한',
                                   '전하경',
                                   '전승욱',
                                   '전대명',
                                   '장예환',
                                   '장대웅',
                                   '임재백',
                                   '이진욱',
                                   '이진승',
                                   '이승준',
                                   '이경태',
                                   '전현',
                                   '최현주',
                                   '안호식',
                                   '신원순',
                                   '서봉용',
                                   '박호일',
                                   '도인환',
                                   '노지훈',
                                   '김현진',
                                   '김지성',
                                   '김재훈',
                                   '황유경',
                                   '김성현',
                                   '김서현',
                                   '문영신',
                                   '곽봉수',
                                   '장민규',
                                   '김효겸',
                                   '송인섭',
                                   '김종서',
                                   '김종호',
                                   '남재화',
                                   '박남아',
                                   '구용태',
                                   '한대성',
                                   '윤정원',
                                   '손지수',
                                   '김숙자',
                                   '김현숙',
                                   '최종현',
                                   '김인수',
                                   '김일식',
                                   '신인호',
                                   '구자돈',
                                   '차무길',
                                   '차성원',
                                   '박지홍',
                                   '이예준',
                                   '위석훈',
                                   '피우덕',
                                   '소귀숙',
                                   '피우정',
                                   '백창열',
                                   '하태수',
                                   '명재규',
                                   '한희숙',
                                   '김동욱',
                                   '김도형',
                                   '김대환',
                                   '김임식',
                                   '명제규',
                                   '박성립',
                                   '신정학',
                                   '신원준',
                                   '임종헌',
                                   '전승옥']}},
 {'area': '중구A',
  'slug': 'maeum_junggua',
  'aliases': ['대구중A온나3(DP2511170481)', '대구중A온나3 (DP2511170481)', '대구중A온나3', 'DP2511170481'],
  'center_code': 'DP2511170481',
  'team_order': ['소닉팀', '넘버팀', '마음팀'],
  'area_config': {'소닉팀': 3, '넘버팀': 1, '마음팀': 3},
  'team_map_path': '/settings/maeum_junggua/teamMap',
  'live_path': '/live/maeum_junggua',
  'weekly_path': '/weekly/maeum_junggua',
  'required_team_riders': {'넘버팀': ['한창목',
                                   '구민성',
                                   '석윤미',
                                   '조영웅',
                                   '류창우',
                                   '이경은',
                                   '이경림',
                                   '김광미',
                                   '정용운',
                                   '지덕곤',
                                   '김우중',
                                   '김시곤',
                                   '천재원',
                                   '조정래',
                                   '이금형',
                                   '최종용',
                                   '최문호',
                                   '이정미',
                                   '염용범',
                                   '김성주',
                                   '이창원',
                                   '채기후',
                                   '손성기',
                                   '박진수',
                                   '김병찬',
                                   '지덕근',
                                   '최중용']}},
 {'area': '수성C',
  'slug': 'maeum_suseongc',
  'aliases': ['대구수성C온나(DP2606010723)', '대구수성C온나 (DP2606010723)', '대구수성C온나', 'DP2606010723'],
  'center_code': 'DP2606010723',
  'team_order': ['마음팀', 'BDMJ팀'],
  'area_config': {'마음팀': 1, 'BDMJ팀': 3},
  'team_map_path': '/settings/maeum_suseongc/teamMap',
  'live_path': '/live/maeum_suseongc',
  'weekly_path': '/weekly/maeum_suseongc',
  'required_team_riders': {'BDMJ팀': ['정병준',
                                     '정을갑',
                                     '석정균',
                                     '황재상',
                                     '정철민',
                                     '홍찬윤',
                                     '임미영',
                                     '강상기',
                                     '오명준',
                                     '김용철',
                                     '이동수',
                                     '김근식',
                                     '이태원',
                                     '신정현',
                                     '정성원',
                                     '강현기',
                                     '김기억',
                                     '김경훈',
                                     '김영철',
                                     '신순미',
                                     '송윤미',
                                     '이승재',
                                     '김도식',
                                     '이슬기',
                                     '손영빈',
                                     '이상구',
                                     '강석진',
                                     '김성우',
                                     '조정민',
                                     '장재근',
                                     '이재정',
                                     '오세현',
                                     '송한솔',
                                     '황호진',
                                     '손효상',
                                     '천기준',
                                     '김형민',
                                     '박민욱',
                                     '강성모',
                                     '김초혜',
                                     '정인기',
                                     '김준상',
                                     '김경환',
                                     '이현동',
                                     '김동현',
                                     '김효용',
                                     '오세출',
                                     '정병철',
                                     '손자수',
                                     '한용규',
                                     '장대식',
                                     '김민찬',
                                     '오강식',
                                     '이준원',
                                     '이상철',
                                     '이상운',
                                     '이동협',
                                     '우상수',
                                     '송정자',
                                     '박준민',
                                     '김진흥',
                                     '김우주',
                                     '김상훈',
                                     '김복룡',
                                     '김명현',
                                     '김명일',
                                     '강철구']}}]

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
    "2026-07-17": 6,
}

PERIODS = ["morning", "afternoon", "evening", "midnight"]
PERIOD_LABELS = {
    "morning": "오전피크",
    "afternoon": "오후논피크",
    "evening": "저녁피크",
    "midnight": "심야논피크",
}



def keep_chrome_rendering(context, page):
    """Chrome을 최소화하지 않고 화면 밖 정상 창 상태로 유지합니다."""
    try:
        page.bring_to_front()
    except Exception:
        pass
    try:
        session = context.new_cdp_session(page)
        try:
            info = session.send("Browser.getWindowForTarget")
            window_id = info.get("windowId")
            if window_id is not None:
                session.send("Browser.setWindowBounds", {
                    "windowId": window_id,
                    "bounds": {
                        "left": -1800,
                        "top": 20,
                        "width": 1400,
                        "height": 900,
                        "windowState": "normal",
                    },
                })
        except Exception:
            pass
        try:
            session.send("Page.setWebLifecycleState", {"state": "active"})
        except Exception:
            pass
        try:
            session.send("Emulation.setFocusEmulationEnabled", {"enabled": True})
        except Exception:
            pass
        try:
            session.send("Emulation.setIdleOverride", {
                "isUserActive": True,
                "isScreenUnlocked": True,
            })
        except Exception:
            pass
        try:
            session.detach()
        except Exception:
            pass
    except Exception:
        pass

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
    # 80% 기준: 완료 4건당 실패 1건까지 허용
    max_bad_total = math.floor(complete * 0.25)
    return max_bad_total - bad_total



def team_of(name):
    global TEAM_MAP_CACHE
    name = norm(name)
    if TEAM_MAP_CACHE is None:
        try:
            init_firebase()
            TEAM_MAP_CACHE = db.reference(TEAM_MAP_PATH).get() or {}
            TEAM_MAP_CACHE = {norm(k): norm(v) for k, v in TEAM_MAP_CACHE.items()}
            print(f"teamMap 로드 완료: {len(TEAM_MAP_CACHE)}명")
        except Exception as e:
            print("teamMap 로드 실패:", e)
            TEAM_MAP_CACHE = {}
    mapped = TEAM_MAP_CACHE.get(name)
    if mapped in TEAM_ORDER:
        return mapped
    for team, names in REQUIRED_TEAM_RIDERS.items():
        if name in {norm(x) for x in names}:
            return team
    return TEAM_ORDER[0] if TEAM_ORDER else "소닉팀"

def to_int(value):
    try:
        return int(str(value).replace(",", "").strip())
    except Exception:
        return 0


def norm(value):
    return str(value).replace("\u200b", "").replace("\ufeff", "").strip()


def normalize_phone(value):
    return re.sub(r"\D", "", str(value or ""))


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
    # 로그인/리다이렉트 URL이 base_url로 잡혀도 항상 기사 실적 페이지로 고정합니다.
    if parsed.path != "/delivery/history":
        parsed = parsed._replace(path="/delivery/history")
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
      const exactPhoneRe = /^010[-\s]?\d{3,4}[-\s]?\d{4}$/;
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
      function phoneKey(t){ return String(t||'').replace(/\D/g,''); }

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
        riderFault: findHeader('배달취소(라이더귀책)', '라이더귀책'),
        morningPeriod: findHeader('아침점심피크'),
        afternoonPeriod: findHeader('오후논피크'),
        eveningPeriod: findHeader('저녁피크'),
        midnightPeriod: findHeader('심야논피크')
      };

      function nearestMetricByHeader(row, header, phoneNode, firstHourLeft){
        if (!header) return null;
        let best = null;
        for (const cell of row) {
          if (!isIntText(cell.text)) continue;
          if (cell.cx <= phoneNode.cx + 10) continue;
          if (Number.isFinite(firstHourLeft) && cell.right >= firstHourLeft - 4) continue;
          const dx = Math.abs(cell.cx - header.cx);
          // 헤더와 x좌표가 크게 떨어진 값은 다른 컬럼으로 봅니다.
          if (dx > Math.max(34, header.width * 2.2)) continue;
          const score = dx + Math.abs(cell.width - header.width) * 0.05;
          if (!best || score < best.score) best = {cell, score};
        }
        return best ? toInt(best.cell.text) : null;
      }

      // 시간 헤더를 20개 이상 못 찾으면 기존 파서가 처리하도록 raw lines로 반환
      if (hours.length < 20) {
        const phoneNodes = nodes.filter(n => exactPhoneRe.test(n.text));
        for (const p of phoneNodes) {
          const key = phoneKey(p.text.match(phoneRe)?.[0] || '');
          if (!key) continue;
          // 여기서 seen 처리하지 않습니다.
          // 잘못 잡힌 푸터/약관 행이 먼저 나오면 같은 전화번호의 실제 기사행이 스킵되는 문제가 있었습니다.
          const rowNodes = nodes.filter(x => Math.abs(x.cy - p.cy) <= 12 && x.height > 0 && x.height <= 80 && x.text.length <= 40)
                              .sort((a,b)=> Math.abs(a.left-b.left)>2 ? a.left-b.left : a.top-b.top);
          out.push({__raw: rowNodes.map(x=>x.text)});
        }
        return out;
      }

      const phoneNodes = nodes.filter(n => exactPhoneRe.test(n.text));
      for (const phoneNode of phoneNodes) {
        const phone = phoneNode.text.match(phoneRe)?.[0];
        if (!phone) continue;
        const key = phoneKey(phone);

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
        if (!name || badLegalNames.has(name)) {
          // 이름이 약관/푸터 문구로 잘못 잡힌 경우, 같은 줄의 다른 이름 후보를 한 번 더 찾습니다.
          const candidates = row
            .filter(x => x.cx < phoneNode.cx && x.text && !phoneRe.test(x.text))
            .map(x => x.text)
            .filter(t => !badLegalNames.has(t) && !/^\d+$/.test(t) && !t.includes('운행') && !t.includes('휴대폰') && !t.includes('이름'));
          name = candidates.reverse().find(t => /^[가-힣]{2,6}$/.test(t)) || '';
        }
        if (!name || badLegalNames.has(name)) {
          out.push({__debugSkip:true, reason:'bad_name', phone, raw:texts});
          continue;
        }
        // 정상 기사로 확정된 뒤에만 전화번호 기준 중복 제거합니다.
        // phoneNode를 '정확히 전화번호만 적힌 셀'로 제한했기 때문에,
        // 푸터/상위 컨테이너가 전화번호를 선점하는 문제는 발생하지 않습니다.
        if (seen.has(key)) {
          out.push({__debugSkip:true, reason:'duplicate_phone', name, phone, raw:texts});
          continue;
        }
        seen.add(key);

        const rightNums = row.filter(x => x.cx > phoneNode.cx + 10 && isIntText(x.text));

        // 배민비즈 현재 화면 구조:
        // 완료[푸드,B마트,배민스토어,합계] → 거절[푸드,B마트,배민스토어,합계]
        // → 배차취소[푸드,B마트,배민스토어,합계]
        // → 배달취소(라이더귀책)[푸드,B마트,배민스토어,합계]
        // → 피크/시간대 컬럼 순서입니다.
        // 따라서 수락률 실패값은 위치 인덱스로 정확히 푸드 컬럼만 읽습니다.
        const firstHourLeft = Math.min(...hours.map(h => h.left));
        const periodLefts = [metricHeaders.morningPeriod, metricHeaders.afternoonPeriod, metricHeaders.eveningPeriod, metricHeaders.midnightPeriod]
          .filter(Boolean).map(h => h.left);
        const firstPeriodLeft = periodLefts.length ? Math.min(...periodLefts) : firstHourLeft;

        let metricCells = row
          .filter(x => x.cx > phoneNode.cx + 10 && x.right < firstPeriodLeft - 4 && isIntText(x.text))
          .sort((a,b) => a.left - b.left);

        // 가로 스크롤/렌더링 때문에 피크 헤더 위치를 못 잡은 경우에만 시간대 앞 숫자를 fallback으로 씁니다.
        if (metricCells.length < 16) {
          metricCells = row
            .filter(x => x.cx > phoneNode.cx + 10 && x.right < firstHourLeft - 4 && isIntText(x.text))
            .sort((a,b) => a.left - b.left)
            .slice(0, 16);
        }

        const metricNums = metricCells.map(x => toInt(x.text));

        // 인덱스 기준:
        // 0 푸드완료, 1 B마트완료, 2 배민스토어완료, 3 완료합계
        // 4 푸드거절, 5 B마트거절, 6 배민스토어거절, 7 거절합계
        // 8 푸드배차취소, 9 B마트배차취소, 10 배민스토어배차취소, 11 배차취소합계
        // 12 푸드배달취소(라이더귀책), 13 B마트, 14 배민스토어, 15 라이더귀책합계
        const foodComplete = metricNums[0] || 0;
        let complete = metricNums[3] || foodComplete;
        let reject = metricNums[4] || 0;
        let cancel = metricNums[8] || 0;
        let riderFault = metricNums[12] || 0;

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

    # 현재 배민비즈 순서:
    # 완료 4칸, 거절 4칸, 배차취소 4칸, 배달취소(라이더귀책) 4칸, 피크 4칸, 시간대
    food_complete = to_int(lines[phone_idx + 1])
    complete = to_int(lines[phone_idx + 4]) or food_complete

    reject = to_int(lines[phone_idx + 5])      # 푸드 거절
    cancel = to_int(lines[phone_idx + 9])      # 푸드 배차취소
    rider_fault = to_int(lines[phone_idx + 13]) # 푸드 배달취소(라이더귀책)

    hourly = []
    hour_start = phone_idx + 21
    for h in range(24):
        hourly.append(to_int(lines[hour_start + h] if hour_start + h < len(lines) else 0))

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
        if isinstance(group, dict) and group.get("__debugSkip"):
            continue
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



def empty_rider_card(name, team):
    return {
        "name": name,
        "phone": "",
        "userId": "",
        "team": team,
        "status": "운행 종료",
        "isOnline": False,
        "complete": 0,
        "reject": 0,
        "cancel": 0,
        "riderFault": 0,
        "morning": 0,
        "afternoon": 0,
        "evening": 0,
        "midnight": 0,
        "morningExcluded": 0,
        "midnightExcluded": 0,
        "excluded": 0,
        "hourly": [0] * 24,
        "acceptRate": 100,
        "warning": False,
        "placeholder": True,
    }


def ensure_required_rider_cards(riders):
    existing_names = {norm(r.get("name", "")) for r in riders if r.get("name")}
    added = []
    for team, names in REQUIRED_TEAM_RIDERS.items():
        for name in names:
            clean_name = norm(name)
            if clean_name and clean_name not in existing_names:
                riders.append(empty_rider_card(clean_name, team))
                added.append(clean_name)
                existing_names.add(clean_name)
    if added:
        print("카드 보강 추가 기사:", ", ".join(added))
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
        debug_skips = [g for g in row_groups if isinstance(g, dict) and g.get('__debugSkip')]
        if debug_skips:
            print(f"{page_no + 1}페이지 스킵 후보 행 수: {len(debug_skips)}")
            for ds in debug_skips[:10]:
                print('스킵행:', ds.get('reason'), ds.get('name', ''), ds.get('phone', ''), ds.get('raw', [])[:12])
        print(f"{page_no + 1}페이지 읽은 기사 수: {len(riders)}")
        if riders:
            print(f"{page_no + 1}페이지 첫/끝 기사: {riders[0]['name']} / {riders[-1]['name']}")

        if page_no == 0 and len(riders) == 0:
            print("DOM 샘플:")
            for idx, row in enumerate(row_groups[:3]):
                print(idx, row[:20])

        if len(riders) == 0:
            print("빈 페이지라서 수집 종료")
            break

        new_count = 0
        for r in riders:
            key = normalize_phone(r.get("phone", "")) or (norm(r.get("name", "")) + "_" + norm(r.get("phone", "")))
            if key not in seen:
                seen.add(key)
                all_riders.append(r)
                new_count += 1
            else:
                print(f"중복 기사 제외: {r.get('name')} / {r.get('phone')} / {r.get('status')}")

        print(f"{page_no + 1}페이지 신규 기사 수: {new_count}")

        if new_count == 0:
            print("새 기사 없음. 마지막 페이지로 판단하고 종료")
            break

    all_riders = ensure_required_rider_cards(all_riders)
    print(f"전체 카드 기사 수: {len(all_riders)}")
    phones = [normalize_phone(r.get("phone", "")) for r in all_riders if r.get("phone")]
    if len(phones) != len(set(phones)):
        print("중복 휴대폰 감지:", [p for p in sorted(set(phones)) if phones.count(p) > 1])
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



def weekly_summary(weekly_rows, now, config=None):
    """현재 수~화 주차의 권역 전체 및 팀별 합계를 계산합니다.

    예전 weekly 행(teams 필드 없음)도 그대로 읽을 수 있도록 호환성을 유지합니다.
    """
    config = config or {
        "area": AREA_NAME,
        "team_order": TEAM_ORDER,
        "area_config": AREA_CONFIG.get(AREA_NAME, {}),
    }
    week_dates = current_week_dates(now)
    date_keys = [str(d) for d in week_dates]
    by_date = {x.get("businessDate"): x for x in weekly_rows if isinstance(x, dict)}

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

    team_totals = {}
    for team in config.get("team_order", []):
        team_totals[team] = {
            "complete": 0,
            "reject": 0,
            "cancel": 0,
            "riderFault": 0,
            "morning": 0,
            "afternoon": 0,
            "evening": 0,
            "midnight": 0,
            "morningExcluded": 0,
            "midnightExcluded": 0,
            "excluded": 0,
            "periodTargets": {p: 0 for p in PERIODS},
            "days": [],
        }

    labels = ["수", "목", "금", "토", "일", "월", "화"]
    period_names = {
        "morning": "오전피크",
        "afternoon": "오후논피크",
        "evening": "저녁피크",
        "midnight": "심야논피크",
    }

    for label, date_value, date_key in zip(labels, week_dates, date_keys):
        row = by_date.get(date_key, {})
        complete = to_int(row.get("totalComplete", row.get("total", {}).get("complete", 0)))
        reject = to_int(row.get("totalReject", row.get("total", {}).get("reject", 0)))
        cancel = to_int(row.get("totalCancel", row.get("total", {}).get("cancel", 0)))
        rider_fault = to_int(row.get("riderFault", row.get("total", {}).get("riderFault", 0)))
        bad_total = reject + cancel + rider_fault
        morning_excluded = to_int(row.get("morningExcluded", row.get("total", {}).get("morningExcluded", 0)))
        midnight_excluded = to_int(row.get("midnightExcluded", row.get("total", {}).get("midnightExcluded", 0)))
        excluded = to_int(row.get(
            "excluded",
            row.get("totalExcluded", row.get("total", {}).get("excluded", morning_excluded + midnight_excluded))
        ))
        period_targets = row.get("periodTargets") or target_total_by_period_for_date(date_value)

        period_rows = []
        for p in PERIODS:
            done = to_int(row.get(p, row.get("total", {}).get(p, 0)))
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

        day_obj = {
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
        }
        days.append(day_obj)

        stored_teams = row.get("teams") or {}
        for team in config.get("team_order", []):
            stored = stored_teams.get(team) or {}
            s = stored.get("summary") if isinstance(stored, dict) and isinstance(stored.get("summary"), dict) else stored
            s = s if isinstance(s, dict) else {}
            t = stored.get("targets") if isinstance(stored, dict) and isinstance(stored.get("targets"), dict) else {}
            team_day = {
                "label": label,
                "businessDate": date_key,
                "hasData": bool(s),
                "complete": to_int(s.get("complete", 0)),
                "reject": to_int(s.get("reject", 0)),
                "cancel": to_int(s.get("cancel", 0)),
                "riderFault": to_int(s.get("riderFault", 0)),
                "morning": to_int(s.get("morning", 0)),
                "afternoon": to_int(s.get("afternoon", 0)),
                "evening": to_int(s.get("evening", 0)),
                "midnight": to_int(s.get("midnight", 0)),
                "morningExcluded": to_int(s.get("morningExcluded", 0)),
                "midnightExcluded": to_int(s.get("midnightExcluded", 0)),
                "excluded": to_int(s.get("excluded", 0)),
                "targets": {p: to_int(t.get(p, 0)) for p in PERIODS},
            }
            team_day["acceptRate"] = calc_accept_rate(
                team_day["complete"], team_day["reject"], team_day["cancel"], team_day["riderFault"]
            )
            team_totals[team]["days"].append(team_day)
            for key in [
                "complete", "reject", "cancel", "riderFault",
                "morning", "afternoon", "evening", "midnight",
                "morningExcluded", "midnightExcluded", "excluded",
            ]:
                team_totals[team][key] += team_day[key]
            for p in PERIODS:
                team_totals[team]["periodTargets"][p] += team_day["targets"][p]

    for team, value in team_totals.items():
        value["acceptRate"] = calc_accept_rate(
            value["complete"], value["reject"], value["cancel"], value["riderFault"]
        )
        value["spareRejects"] = spare_rejects(
            value["complete"], value["reject"], value["cancel"], value["riderFault"]
        )
        value["periodTotals"] = {p: value[p] for p in PERIODS}
        value["sets"] = to_int(config.get("area_config", {}).get(team, 0))

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
        "teams": team_totals,
    }


def save_weekly_if_close(data, config=None):
    """오늘 권역 전체 및 팀별 실적을 weekly 파일에 갱신합니다.

    같은 날짜는 최신값으로 덮어쓰고, 날짜가 다르면 수치가 같아도 새 행으로 보존합니다.
    """
    config = config or {
        "area": AREA_NAME,
        "slug": CURRENT_SLUG,
        "team_order": TEAM_ORDER,
    }
    weekly = load_weekly()
    if not isinstance(weekly, list):
        weekly = []

    today_key = data["businessDate"]
    target_date = datetime.strptime(today_key, "%Y-%m-%d").date()
    period_targets = target_total_by_period_for_date(target_date)
    week_start = week_start_wednesday(target_date)
    week_end = week_start + timedelta(days=6)

    team_rows = {}
    for team in config.get("team_order", []):
        current = data.get("teams", {}).get(team, {})
        team_rows[team] = {
            "summary": dict(current.get("summary") or {}),
            "targets": dict(current.get("targets") or {}),
        }

    row = {
        "area": config["area"],
        "slug": config["slug"],
        "businessDate": today_key,
        "weekStart": str(week_start),
        "weekEnd": str(week_end),
        "closedAt": data["updatedAt"],

        # 기존 HTML 호환 필드
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

        # 신규 장기 정산용 구조
        "total": dict(data["total"]),
        "teams": team_rows,
    }

    found = False
    for i, old in enumerate(weekly):
        if isinstance(old, dict) and old.get("businessDate") == today_key:
            weekly[i] = row
            found = True
            break

    if not found:
        weekly.append(row)

    # 날짜 중복을 제거하면서 최신 행을 우선 보존
    dedup = {}
    for item in weekly:
        if isinstance(item, dict) and item.get("businessDate"):
            dedup[item["businessDate"]] = item
    weekly = sorted(dedup.values(), key=lambda x: x.get("businessDate", ""))[-730:]

    with open(WEEKLY_FILE, "w", encoding="utf-8") as f:
        json.dump(weekly, f, ensure_ascii=False, indent=2)


def available_weeks(weekly_rows):
    weeks = {}
    for row in weekly_rows:
        if not isinstance(row, dict) or not row.get("businessDate"):
            continue
        try:
            d = datetime.strptime(row["businessDate"], "%Y-%m-%d").date()
        except Exception:
            continue
        start = row.get("weekStart") or str(week_start_wednesday(d))
        end = row.get("weekEnd") or str(week_start_wednesday(d) + timedelta(days=6))
        weeks[start] = {"startDate": start, "endDate": end}
    return [weeks[k] for k in sorted(weeks.keys(), reverse=True)]


def make_data(riders, config=None):
    config = config or {
        "area": AREA_NAME,
        "slug": CURRENT_SLUG,
        "team_order": TEAM_ORDER,
        "area_config": AREA_CONFIG.get(AREA_NAME, {}),
    }
    now = datetime.now()
    riders.sort(key=lambda x: (not x["isOnline"], x["name"]))

    targets = team_targets(now)
    teams = {}

    for team in config["team_order"]:
        rows = [r for r in riders if r["team"] == team]
        teams[team] = {
            "summary": summary(rows),
            "targets": targets[team],
            "riders": rows,
        }

    weekly = load_weekly()

    return {
        "area": config["area"],
        "slug": config["slug"],
        "areas": [c["area"] for c in CENTER_CONFIGS],
        "teamOrder": list(config["team_order"]),
        "updatedAt": now.strftime("%Y-%m-%d %H:%M:%S"),
        "businessDate": str(business_date(now)),
        "currentPeriod": current_period(now),
        "currentPeriodLabel": PERIOD_LABELS[current_period(now)],
        "targetAcceptRate": TARGET_ACCEPT_RATE,
        "total": summary(riders),
        "teams": teams,
        "riders": riders,
        "weekly": weekly,
        "availableWeeks": available_weeks(weekly),
        "weeklySummary": weekly_summary(weekly, now, config),
    }


def save_json(data, config=None):
    config = config or {
        "area": AREA_NAME,
        "slug": CURRENT_SLUG,
        "live_path": LIVE_PATH,
        "weekly_path": WEEKLY_PATH,
    }
    expected_data_file = BASE_DIR / f"data_{config['slug']}.json"
    expected_weekly_file = BASE_DIR / f"weekly_{config['slug']}.json"

    # 권역 혼선 방지: 업로드 전에 세 값을 모두 검증합니다.
    if data.get("area") != config["area"]:
        raise RuntimeError(
            f"권역 검증 실패: data.area={data.get('area')} / config.area={config['area']}"
        )
    if data.get("slug") != config["slug"]:
        raise RuntimeError(
            f"slug 검증 실패: data.slug={data.get('slug')} / config.slug={config['slug']}"
        )
    if DATA_FILE.resolve() != expected_data_file.resolve() or WEEKLY_FILE.resolve() != expected_weekly_file.resolve():
        raise RuntimeError(
            f"파일 경로 검증 실패: DATA_FILE={DATA_FILE.name}, WEEKLY_FILE={WEEKLY_FILE.name}, "
            f"예상={expected_data_file.name}, {expected_weekly_file.name}"
        )

    with open(expected_data_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 방금 저장한 로컬 JSON을 다시 읽어 최종 확인합니다.
    with open(expected_data_file, "r", encoding="utf-8") as f:
        verify = json.load(f)
    if verify.get("area") != config["area"] or verify.get("slug") != config["slug"]:
        raise RuntimeError(f"저장 후 권역 검증 실패: {expected_data_file.name}")

    try:
        upload_json(expected_data_file.name, config["live_path"])
        upload_json(expected_weekly_file.name, config["weekly_path"])
        print(f"Firebase 업로드 완료: {config['live_path']} ← {expected_data_file.name}")
        print(f"Firebase 업로드 완료: {config['weekly_path']} ← {expected_weekly_file.name}")
    except Exception as e:
        print("Firebase 업로드 실패")
        raise

def save_html():
    return


def git_push():
    if not AUTO_GIT_PUSH:
        return

    subprocess.run(["git", "add", "data_dalseoa.json", "index.html", "d_a.py", "logo.png"], cwd=BASE_DIR)

    if WEEKLY_FILE.exists():
        subprocess.run(["git", "add", "weekly_dalseoa.json"], cwd=BASE_DIR)

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



def run_update(page, config=None):
    global VERIFIED_CENTER_CODE
    config = config or {
        "area": AREA_NAME,
        "slug": CURRENT_SLUG,
        "team_order": TEAM_ORDER,
        "area_config": AREA_CONFIG.get(AREA_NAME, {}),
        "live_path": LIVE_PATH,
        "weekly_path": WEEKLY_PATH,
    }

    expected_code = norm(config.get("center_code", ""))
    if VERIFIED_CENTER_CODE != expected_code:
        raise RuntimeError(
            f"업로드 차단: 검증된 협력사={VERIFIED_CENTER_CODE!r}, 예상={expected_code!r}"
        )

    # 마음 수집기는 마음 전용 Firebase 경로만 허용합니다.
    allowed_live_prefix = "/live/maeum"
    allowed_weekly_prefix = "/weekly/maeum"
    live_path = str(config.get("live_path", ""))
    weekly_path = str(config.get("weekly_path", ""))
    if not live_path.startswith(allowed_live_prefix):
        raise RuntimeError(f"업로드 차단: 마음 전용 live 경로가 아닙니다: {live_path}")
    if not weekly_path.startswith(allowed_weekly_prefix):
        raise RuntimeError(f"업로드 차단: 마음 전용 weekly 경로가 아닙니다: {weekly_path}")

    riders = collect_all_pages_by_dom(page)
    if len(riders) == 0:
        raise RuntimeError("기사 데이터를 못 읽었습니다.")

    data = make_data(riders, config)

    if data.get("area") != config["area"] or data.get("slug") != config["slug"]:
        raise RuntimeError(
            f"수집 권역 불일치: {data.get('area')}/{data.get('slug')} "
            f"!= {config['area']}/{config['slug']}"
        )

    save_weekly_if_close(data, config)
    weekly = load_weekly()
    data["weekly"] = weekly
    data["availableWeeks"] = available_weeks(weekly)
    data["weeklySummary"] = weekly_summary(weekly, datetime.now(), config)
    save_json(data, config)

    print(f"업로드 완료: {data['updatedAt']}")
    print(f"권역: {config['area']} / slug: {config['slug']}")
    print(f"전체 기사 수: {data['total']['count']}")
    print(f"접속중 기사 수: {data['total']['onlineCount']}")
    for team in config["team_order"]:
        print(f"{team} 접속중: {data['teams'][team]['summary']['onlineCount']}")
    print(f"전체 완료: {data['total']['complete']}")
    print(f"전체 거절: {data['total']['reject']}")
    print(f"전체 취소: {data['total']['cancel']}")
    print(f"수락률: {data['total']['acceptRate']}%")
    return data

def activate_center(config):
    global AREA_NAME, TEAM_ORDER, AREA_CONFIG, TEAM_MAP_PATH
    global LIVE_PATH, WEEKLY_PATH, CURRENT_SLUG, DATA_FILE, WEEKLY_FILE
    global REQUIRED_TEAM_RIDERS, TEAM_MAP_CACHE, VERIFIED_CENTER_CODE
    VERIFIED_CENTER_CODE = None
    AREA_NAME = config["area"]
    CURRENT_SLUG = config["slug"]
    TEAM_ORDER = list(config["team_order"])
    AREA_CONFIG = {AREA_NAME: dict(config["area_config"])}
    TEAM_MAP_PATH = config["team_map_path"]
    LIVE_PATH = config["live_path"]
    WEEKLY_PATH = config["weekly_path"]
    REQUIRED_TEAM_RIDERS = dict(config.get("required_team_riders") or {})
    DATA_FILE = BASE_DIR / f"data_{CURRENT_SLUG}.json"
    WEEKLY_FILE = BASE_DIR / f"weekly_{CURRENT_SLUG}.json"
    TEAM_MAP_CACHE = None


def _visible(locator):
    try:
        return locator.count() > 0 and locator.first.is_visible()
    except Exception:
        return False


def _selected_center_code_on_change_page(page):
    """협력사 변경 화면의 현재 선택된 DP코드를 반환합니다."""
    return page.evaluate(r"""
    () => {
      const visible = el => {
        const r = el.getBoundingClientRect();
        const s = getComputedStyle(el);
        return r.width > 0 && r.height > 0 && s.display !== 'none' &&
               s.visibility !== 'hidden' && s.opacity !== '0';
      };
      const compact = s => String(s || '').replace(/\s+/g, '');
      const all = Array.from(document.querySelectorAll('body *')).filter(visible);
      const prompt = all
        .filter(el => compact(el.textContent) === compact('협력사를 선택해주세요.'))
        .sort((a,b) => a.children.length - b.children.length)[0];
      if (!prompt) return '';
      const py = prompt.getBoundingClientRect().bottom;
      const candidates = all
        .filter(el => {
          const r = el.getBoundingClientRect();
          const txt = compact(el.textContent);
          return r.top >= py - 8 && /DP\d+/.test(txt) && txt.length < 80;
        })
        .sort((a,b) => {
          const at = compact(a.textContent), bt = compact(b.textContent);
          const ar = a.getBoundingClientRect(), br = b.getBoundingClientRect();
          return at.length - bt.length || (ar.width*ar.height) - (br.width*br.height);
        });
      if (!candidates.length) return '';
      const m = compact(candidates[0].textContent).match(/DP\d+/);
      return m ? m[0] : '';
    }
    """)


def change_center(page, config):
    """마음 계정 안에서 목표 DP코드가 실제로 선택된 경우에만 수집합니다."""
    global VERIFIED_CENTER_CODE
    VERIFIED_CENTER_CODE = None

    target_code = norm(config.get("center_code", ""))
    if not re.fullmatch(r"DP\d+", target_code):
        raise RuntimeError(f"{config['area']} center_code 설정 오류: {target_code!r}")

    print(f"협력사 변경 시도: {config['area']} / {target_code}")
    change_url = "https://deliverycenter.baemin.com/center/change"

    page.goto(change_url)
    page.wait_for_load_state("domcontentloaded")
    time.sleep(2.0)

    current_code = _selected_center_code_on_change_page(page)
    print(f"변경 전 실제 협력사: {current_code or '확인 실패'}")

    if current_code != target_code:
        opened = page.evaluate(r"""
        () => {
          const visible = el => {
            const r=el.getBoundingClientRect(), s=getComputedStyle(el);
            return r.width>0 && r.height>0 && s.display!=='none' &&
                   s.visibility!=='hidden' && s.opacity!=='0';
          };
          const compact=s=>String(s||'').replace(/\s+/g,'');
          const all=Array.from(document.querySelectorAll('body *')).filter(visible);
          const prompt=all.filter(el=>compact(el.textContent)===compact('협력사를 선택해주세요.'))
                          .sort((a,b)=>a.children.length-b.children.length)[0];
          if(!prompt) return false;
          const py=prompt.getBoundingClientRect().bottom;
          const vals=all.filter(el=>{
            const r=el.getBoundingClientRect(), txt=compact(el.textContent);
            return r.top>=py-8 && /DP\d+/.test(txt) && txt.length<80;
          }).sort((a,b)=>{
            const at=compact(a.textContent),bt=compact(b.textContent);
            const ar=a.getBoundingClientRect(),br=b.getBoundingClientRect();
            return at.length-bt.length || (ar.width*ar.height)-(br.width*br.height);
          });
          if(!vals.length) return false;
          let el=vals[0];
          for(let i=0;i<6&&el;i++,el=el.parentElement){
            const r=el.getBoundingClientRect();
            const role=el.getAttribute&&el.getAttribute('role');
            const tag=(el.tagName||'').toLowerCase();
            if(r.height<140&&(tag==='button'||role==='button'||role==='combobox'||el.tabIndex>=0)){
              el.click(); return true;
            }
          }
          vals[0].click(); return true;
        }
        """)
        if not opened:
            raise RuntimeError("협력사 선택 박스를 열지 못했습니다.")
        time.sleep(1.2)

        selected = page.evaluate(r"""
        (targetCode) => {
          const visible = el => {
            const r=el.getBoundingClientRect(), s=getComputedStyle(el);
            return r.width>0 && r.height>0 && s.display!=='none' &&
                   s.visibility!=='hidden' && s.opacity!=='0';
          };
          const compact=s=>String(s||'').replace(/\s+/g,'');
          const matches=Array.from(document.querySelectorAll('body *'))
            .filter(visible)
            .filter(el=>{
              const txt=compact(el.textContent);
              return txt.includes(targetCode) && txt.length<100;
            })
            .sort((a,b)=>{
              const roleA=a.getAttribute&&a.getAttribute('role');
              const roleB=b.getAttribute&&b.getAttribute('role');
              const bonusA=(roleA==='option'?1000:0)+((a.tagName||'').toLowerCase()==='li'?500:0);
              const bonusB=(roleB==='option'?1000:0)+((b.tagName||'').toLowerCase()==='li'?500:0);
              const at=compact(a.textContent),bt=compact(b.textContent);
              const ar=a.getBoundingClientRect(),br=b.getBoundingClientRect();
              return bonusB-bonusA || at.length-bt.length ||
                     (ar.width*ar.height)-(br.width*br.height);
            });
          if(!matches.length) return '';
          let el=matches[0];
          for(let i=0;i<6&&el;i++,el=el.parentElement){
            const r=el.getBoundingClientRect();
            const role=el.getAttribute&&el.getAttribute('role');
            const tag=(el.tagName||'').toLowerCase();
            if(r.height<140&&(role==='option'||tag==='li'||tag==='button')){
              el.click(); return compact(matches[0].textContent);
            }
          }
          matches[0].click();
          return compact(matches[0].textContent);
        }
        """, target_code)

        if not selected:
            raise RuntimeError(f"{config['area']}({target_code}) 옵션을 찾지 못했습니다.")

        done = page.get_by_text("선택 완료", exact=True)
        if done.count() == 0 or not done.first.is_visible():
            raise RuntimeError("선택 완료 버튼을 찾지 못했습니다.")
        done.first.click()
        time.sleep(2.0)

    page.goto(change_url)
    page.wait_for_load_state("domcontentloaded")
    time.sleep(1.8)

    verified_code = _selected_center_code_on_change_page(page)
    if verified_code != target_code:
        raise RuntimeError(
            f"협력사 전환 검증 실패: 목표={target_code}, 실제={verified_code or '확인 실패'}; "
            "Firebase 업로드를 차단합니다."
        )

    VERIFIED_CENTER_CODE = verified_code
    print(f"협력사 변경 검증 성공: {config['area']} / {verified_code}")

    history_url = (
        "https://deliverycenter.baemin.com/delivery/history"
        "?page=0&size=100&orderName=name&orderBy=asc"
        "&name=&userId=&phoneNumber=&riderStatus="
    )
    page.goto(history_url)
    page.wait_for_load_state("networkidle")
    time.sleep(1.5)

def main():
    print("MAEUM 독립 다권역 DOM 자동 수집기 - 화면 밖 백그라운드 모드")
    print("대상 권역:", ", ".join(c["area"] for c in CENTER_CONFIGS))

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(BASE_DIR / "chrome_profile_maeum"),
            headless=False,
            viewport={"width": 1400, "height": 900},
            args=BACKGROUND_SAFE_ARGS,
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.set_default_timeout(30000)
        page.set_default_navigation_timeout(45000)

        page.goto(
            "https://deliverycenter.baemin.com/delivery/history"
            "?page=0&size=100&orderName=name&orderBy=asc"
            "&name=&userId=&phoneNumber=&riderStatus="
        )

        print("1. 열린 배민비즈 창에서 마음 계정으로 로그인하세요.")
        print("2. 기사 실적 페이지가 열리는지 확인하세요.")
        print("3. 준비되면 CMD에서 Enter를 누르세요.")
        print("4. Enter 후 Chrome 창은 최소화되지 않고 화면 바깥으로 이동합니다.")
        input("Enter 대기 중...")

        keep_chrome_rendering(browser, page)
        print("Chrome 창을 화면 밖으로 이동했습니다.")
        print("CMD 창은 최소화해도 됩니다. Chrome은 작업표시줄에서 최소화하지 마세요.")

        try:
            while True:
                cycle_started = datetime.now()
                print("\n" + "=" * 60)
                print("통합 자동 수집 시작:", cycle_started.strftime("%Y-%m-%d %H:%M:%S"))
                success_count = 0

                for config in CENTER_CONFIGS:
                    print("\n" + "-" * 60)
                    print(f"[{config['area']}] 수집 시작")
                    try:
                        keep_chrome_rendering(browser, page)
                        activate_center(config)
                        change_center(page, config)
                        keep_chrome_rendering(browser, page)
                        run_update(page, config)
                        success_count += 1
                    except KeyboardInterrupt:
                        raise
                    except Exception as e:
                        print(f"[{config['area']}] 오류 발생: {e}")
                        import traceback
                        traceback.print_exc()

                elapsed = int((datetime.now() - cycle_started).total_seconds())
                print("\n" + "=" * 60)
                print(f"한 바퀴 완료: {success_count}/{len(CENTER_CONFIGS)} 권역 성공, 소요 {elapsed}초")
                print(f"{REFRESH_SECONDS}초 후 다시 마음 달서A부터 수집합니다.")
                time.sleep(REFRESH_SECONDS)
        finally:
            try:
                browser.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
