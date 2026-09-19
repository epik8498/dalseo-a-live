import json
import math
import re
import subprocess
import time
import gc
import ctypes
from ctypes import wintypes
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from firebase_admin import db
from firebase_uploader import init_firebase

from playwright.sync_api import sync_playwright
from firebase_uploader import upload_json

AUTO_GIT_PUSH = False
DEBUG_LOG = False  # True일 때만 DOM/스킵/팀맵 등 상세 진단 로그 출력

def debug_log(*args, **kwargs):
    if DEBUG_LOG:
        print(*args, **kwargs)

# Enterprise Collector Core v2 - adaptive wait / DP speed optimization
# 기사실적 Source of Truth: Baemin delivery-status API JSON
# 목표: 하나의 배민 로그인 세션/Chrome으로 가능한 많은 DP를 순차 수집하되,
# 동일 DP 재수집 주기를 180초 목표로 관리합니다.
CYCLE_TARGET_SECONDS = 180
CYCLE_WARN_RATIO = 0.85  # 153초 초과 시 용량 경고
HISTORY_RENDER_TIMEOUT = 5.0
COLLECTION_VIEWPORT_WIDTH = 4200
COLLECTION_VIEWPORT_HEIGHT = 1000
CENTER_RENDER_TIMEOUT = 4.0
CENTER_COMMIT_GRACE = 0.45
COLLECTOR_ID = "supersonic-main-01"
COLLECTOR_STATUS_ROOT = "/collector-status"
COLLECTOR_ERROR_ROOT = "/collector-errors"
COLLECTOR_ERROR_KEEP = 100
WEEKLY_SNAPSHOT_HOUR = 1
WEEKLY_SAVED_BUSINESS_DATES = {}  # slug -> businessDate; 프로세스 내 01시 중복 저장 방지
MAX_PAGES = 20
TARGET_ACCEPT_RATE = 80

# ===== TNT BAEMIN DELIVERY-STATUS API DIRECT V3 2026-09 =====
# 기사실적은 화면 DOM 숫자 위치를 읽지 않고, 배민비즈가 실제 화면에 사용하는
# delivery-status XHR JSON 응답을 직접 수신합니다.
BAEMIN_API_RESPONSE_TIMEOUT_MS = 20000
BAEMIN_API_STABLE_RETRY = 2
BAEMIN_HISTORY_PAGE_SIZE = 100

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

# ===== TNT COLLECTOR RAM GUARD 2026-09 =====
# keep_chrome_rendering()에서 CDP 세션을 매 호출마다 새로 만들지 않고 1개를 재사용합니다.
# 기존 구조는 8DP x 사이클마다 반복 생성/분리되어 장기 실행 시 Python 메모리 누적 후보였습니다.
CHROME_RENDER_CDP_SESSION = None
CHROME_RENDER_CDP_PAGE = None
MEMORY_WARN_PRIVATE_MB = 1500.0
MEMORY_DIAG_INITIAL_CYCLES = 3


class _PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


def process_memory_mb():
    """현재 Collector Python 프로세스의 Working Set / Private RAM(MB)을 반환합니다."""
    try:
        counters = _PROCESS_MEMORY_COUNTERS_EX()
        counters.cb = ctypes.sizeof(counters)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(counters), counters.cb
        )
        if ok:
            mb = 1024.0 * 1024.0
            return (counters.WorkingSetSize / mb, counters.PrivateUsage / mb)
    except Exception:
        pass
    return (0.0, 0.0)


def print_memory_status(label, baseline_private=None):
    working, private = process_memory_mb()
    delta_text = ""
    if baseline_private is not None and private > 0:
        delta_text = f" · Δ {private - baseline_private:+.1f} MB"
    if DEBUG_LOG:
        print(f"[RAM] {label} · Working {working:.1f} MB · Private {private:.1f} MB{delta_text}")
    if private >= MEMORY_WARN_PRIVATE_MB:
        print(
            f"[경고] Collector RAM {private:.1f} MB"
        )
    return private

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data_dalseoa.json"
HTML_FILE = BASE_DIR / "index.html"
WEEKLY_FILE = BASE_DIR / "weekly_dalseoa.json"

AREA_NAME = "달서A"
TEAM_ORDER = []
AREA_CONFIG = {}
TEAM_MAP_PATH = ""
LIVE_PATH = ""
WEEKLY_PATH = ""
CURRENT_SLUG = ""
REQUIRED_TEAM_RIDERS = {}
TEAM_MAP_CACHE = None
# ===== TNT TEAMMAP READ CACHE 2026-09 =====
TEAM_MAP_CACHE_BY_SLUG = {}
TEAM_MAP_CACHE_AT_BY_SLUG = {}
TEAM_MAP_CACHE_TTL_SECONDS = 3600  # 센터별 최대 1시간에 1회 전체 teamMap 재동기화
VERIFIED_CENTER_CODE = None
IDENTITY_TEAM_MAP = {}
NAME_TEAM_MAP = {}
EXCLUDED_IDENTITY_KEYS = set()

CENTER_CONFIGS = [{'area': '달서A',
  'slug': 'dalseoa',
  'aliases': ['대구달서7M(DP2506234693)', '대구달서7M (DP2506234693)', '대구달서7M', 'DP2506234693'],
  'center_code': 'DP2506234693',
  'team_order': ['소닉팀', '달서팀', '신규'],
  'area_config': {'소닉팀': 6.5, '달서팀': 1.5, '신규': 0},
  'team_map_path': '/settings/dalseoa/teamMap',
  'live_path': '/live/dalseoa',
  'weekly_path': '/weekly/dalseoa',
  'required_team_riders': {'달서팀': ['김민승',
                                   '윤창근',
                                   '김병국',
                                   '신호준',
                                   '김영빈',
                                   '김용우',
                                   '박지원',
                                   '김탁기',
                                   '김병철',
                                   '정영훈',
                                   '김태광',
                                   '배재현',
                                   '김형민',
                                   '문승수',
                                   '이상민',
                                   '정성훈',
                                   '이주철',
                                   '박기홍',
                                   '정판호',
                                   '나미영',
                                   '황호용',
                                   '김영철',
                                   '남승훈',
                                   '남수현',
                                   '김민서',
                                   '신진관',
                                   '임선미',
                                   '여재환',
                                   '정주현',
                                   '김기현',
                                   '김범준',
                                   '이윤석',
                                   '양혜진',
                                   '김민우',
                                   '김혜성',
                                   '김기헌',
                                   '조대영',
                                   '정승덕',
                                   '임상완',
                                   '김우진',
                                   '신민규',
                                   '김진현',
                                   '김재석',
                                   '서청만']}},
 {'area': '달서B',
  'slug': 'dalseob',
  'aliases': ['대구달서B온나(DP2602028125)', '대구달서B온나 (DP2602028125)', '대구달서B온나', 'DP2602028125'],
  'center_code': 'DP2602028125',
  'team_order': ['소닉팀', '넘버팀', '마음팀', '성공드림', '신규'],
  'area_config': {'소닉팀': 1.5, '넘버팀': 5.3, '마음팀': 2.7, '성공드림': 1.5, '신규': 0},
  'team_map_path': '/settings/dalseob/teamMap',
  'live_path': '/live/dalseob',
  'weekly_path': '/weekly/dalseob',
  'required_team_riders': {},
  'identity_team_map': {'uid_shopvw': '성공드림',
                        'uid_qw1637': '성공드림',
                        'uid_yy2146': '성공드림',
                        'uid_doshin0000': '성공드림',
                        'uid_hero2000a': '성공드림',
                        'uid_kim1302': '성공드림',
                        'uid_BC97751': '성공드림',
                        'uid_820111': '성공드림',
                        'uid_kimkutak49r6': '성공드림',
                        'uid_wprb44': '성공드림',
                        'uid_shin84': '성공드림',
                        'uid_pna5511': '성공드림',
                        'uid_01093634891': '성공드림',
                        'uid_jieum1010': '성공드림',
                        'uid_sign111': '성공드림',
                        'uid_jwss8489': '성공드림',
                        'uid_sjs071021': '성공드림',
                        'uid_inhoshin': '성공드림',
                        'uid_stv77': '성공드림',
                        'uid_Minhlong0109': '성공드림',
                        'uid_injae7082': '성공드림',
                        'uid_jjjgw57': '성공드림',
                        'uid_sophia1004': '성공드림',
                        'uid_gil2048': '성공드림',
                        'uid_gil3378': '성공드림',
                        'uid_ggttooii': '성공드림',
                        'uid_cjhcjh1': '성공드림',
                        'uid_pee8156': '성공드림',
                        'uid_pwjg25': '성공드림',
                        'uid_ts2037': '성공드림',
                        'uid_djmatzzang': '성공드림',
                        'uid_nigimi4i': '성공드림',
                        'uid_gallardo007': '성공드림'}},
 {'area': '중구A',
  'slug': 'junggua',
  'aliases': ['대구중A온나1(DP2505305786)', '대구중A온나1 (DP2505305786)', '대구중A온나1', 'DP2505305786'],
  'center_code': 'DP2505305786',
  'team_order': ['슈퍼', '성공', '직영', 'BM', '상생', '나르미', '신규'],
  'area_config': {'슈퍼': 2.0, '성공': 3.5, '직영': 5.0, 'BM': 2, '상생': 1, '나르미': 1.5, '신규': 0},
  'team_map_path': '/settings/junggua/teamMap',
  'live_path': '/live/junggua',
  'weekly_path': '/weekly/junggua',
  'required_team_riders': {},
  'identity_team_map': {'phone_01057456300': '슈퍼',
                        'uid_aa57456300': '슈퍼',
                        'phone_01023326437': '나르미',
                        'uid_agiwang88': '나르미',
                        'phone_01089510080': '슈퍼',
                        'uid_won6542': '슈퍼',
                        'phone_01095661008': '슈퍼',
                        'uid_daedong1008': '슈퍼',
                        'phone_01083667241': '나르미',
                        'phone_01029972284': '나르미',
                        'uid_yyss0908': '나르미',
                        'phone_01027257069': '직영',
                        'uid_yuil666': '직영',
                        'phone_01096792722': '슈퍼',
                        'uid_jm3315': '슈퍼',
                        'phone_01095157960': '나르미',
                        'uid_yby9913': '나르미',
                        'phone_01028105684': '직영',
                        'uid_ansgh5684': '직영',
                        'phone_01085654445': '슈퍼',
                        'uid_bmw159357': '슈퍼',
                        'phone_01076637520': '나르미',
                        'uid_woals77s': '나르미',
                        'phone_01097790044': '슈퍼',
                        'uid_wngh1710': '슈퍼',
                        'phone_01092032403': '나르미',
                        'uid_asessnail': '나르미',
                        'phone_01062457690': '슈퍼',
                        'uid_hnm05003': '슈퍼',
                        'phone_01057789690': '슈퍼',
                        'uid_ngtm9': '슈퍼',
                        'phone_01071548131': '슈퍼',
                        'uid_fnwnfk33': '슈퍼',
                        'phone_01035272356': '직영',
                        'uid_moon1250': '직영',
                        'phone_01021978393': '나르미',
                        'phone_01055488393': '나르미',
                        'phone_01051217089': '슈퍼',
                        'uid_dream7350': '슈퍼',
                        'phone_01036163400': '슈퍼',
                        'uid_cyon2231': '슈퍼',
                        'phone_01093442156': '슈퍼',
                        'uid_kdh7631': '슈퍼',
                        'phone_01022877383': '슈퍼',
                        'uid_chols18': '슈퍼',
                        'phone_01082471499': '직영',
                        'uid_kbc1422': '직영',
                        'phone_01074099919': '슈퍼',
                        'uid_ksm108': '슈퍼',
                        'phone_01045846363': '나르미',
                        'uid_tkddlf6361': '나르미',
                        'phone_01090397150': '나르미',
                        'uid_kimsh7150': '나르미',
                        'phone_01095819421': '직영',
                        'uid_BC942145': '직영',
                        'phone_01090721235': '나르미',
                        'uid_개인정보처리방침\nCopyright ⓒ Woowa Brothers Corp All Rights Reserved_': '나르미',
                        'phone_01084171900': '슈퍼',
                        'uid_sos1900': '슈퍼',
                        'phone_01088588862': '직영',
                        'uid_mysigon2': '직영',
                        'phone_01044606052': '슈퍼',
                        'uid_kkk7285': '슈퍼',
                        'phone_01033310513': '나르미',
                        'uid_das5019': '나르미',
                        'phone_01091725567': '나르미',
                        'uid_Kys5567': '나르미',
                        'phone_01036966753': '슈퍼',
                        'uid_dudtn6753': '슈퍼',
                        'phone_01038148938': '슈퍼',
                        'uid_ko7330': '슈퍼',
                        'phone_01076884319': '슈퍼',
                        'uid_dbswo4633': '슈퍼',
                        'phone_01036495033': '슈퍼',
                        'uid_kis5033': '슈퍼',
                        'phone_01035271068': '슈퍼',
                        'uid_tjq0925': '슈퍼',
                        'phone_01023878546': '나르미',
                        'uid_wnduqdl91': '나르미',
                        'phone_01077419068': '나르미',
                        'uid_khjwj2': '나르미',
                        'phone_01025047344': '슈퍼',
                        'uid_smilemaru19': '슈퍼',
                        'phone_01040540117': '나르미',
                        'uid_shoorainbow': '나르미',
                        'phone_01086303485': '슈퍼',
                        'uid_jungh16': '슈퍼',
                        'phone_01035373966': '나르미',
                        'phone_01076343059': '직영',
                        'uid_ckddn456123': '직영',
                        'phone_01080820179': '슈퍼',
                        'uid_kyeongjin1': '슈퍼',
                        'phone_01043431800': '나르미',
                        'uid_pks061012': '나르미',
                        'phone_01079160000': '나르미',
                        'uid_gcpark100': '나르미',
                        'phone_01079637387': '슈퍼',
                        'uid_rktl1212': '슈퍼',
                        'phone_01038068348': '슈퍼',
                        'uid_sbeotjd': '슈퍼',
                        'phone_01064634980': '슈퍼',
                        'uid_tjdrbs11020': '슈퍼',
                        'phone_01082215061': '슈퍼',
                        'uid_epik8498': '슈퍼',
                        'phone_01058974243': '슈퍼',
                        'phone_01075765128': '슈퍼',
                        'uid_jrs7639': '슈퍼',
                        'phone_01068939625': '슈퍼',
                        'uid_pj0906': '슈퍼',
                        'phone_01081407166': '직영',
                        'uid_rudtnwlstn12': '직영',
                        'phone_01038217652': '직영',
                        'phone_01077361022': '나르미',
                        'uid_gogoterry': '나르미',
                        'phone_01050462797': '나르미',
                        'phone_01024260078': '슈퍼',
                        'uid_skce123': '슈퍼',
                        'phone_01049858252': '직영',
                        'uid_ahafree': '직영',
                        'phone_01037102977': '슈퍼',
                        'uid_skch01': '슈퍼',
                        'phone_01091519166': '직영',
                        'uid_zxc9166': '직영',
                        'phone_01072624644': '나르미',
                        'uid_yss0908': '나르미',
                        'phone_01039723064': '직영',
                        'uid_jaeyong1983': '직영',
                        'phone_01082092975': '나르미',
                        'uid_ascmoon': '나르미',
                        'phone_01091614445': '직영',
                        'uid_pooh3986': '직영',
                        'phone_01076271378': '나르미',
                        'uid_fmamfnan': '나르미',
                        'phone_01042577444': '슈퍼',
                        'uid_h7444': '슈퍼',
                        'phone_01048950609': '직영',
                        'uid_mylive00': '직영',
                        'phone_01076263146': '직영',
                        'uid_chsolem2': '직영',
                        'phone_01079049872': '슈퍼',
                        'uid_boo2132': '슈퍼',
                        'phone_01096588114': '슈퍼',
                        'uid_ggmomo98': '슈퍼',
                        'phone_01028825855': '직영',
                        'uid_dlrmagud': '직영',
                        'phone_01059094145': '슈퍼',
                        'uid_intherain010': '슈퍼',
                        'phone_01040712284': '나르미',
                        'phone_01058949971': '나르미',
                        'uid_lmh0113': '나르미',
                        'phone_01076109761': '슈퍼',
                        'uid_lesangm': '슈퍼',
                        'phone_01099197690': '슈퍼',
                        'uid_moeer': '슈퍼',
                        'phone_01057224644': '나르미',
                        'phone_01048683753': '나르미',
                        'uid_asd0714': '나르미',
                        'phone_01059474863': '슈퍼',
                        'uid_hn54002': '슈퍼',
                        'phone_01083747444': '슈퍼',
                        'uid_mywoals66': '슈퍼',
                        'phone_01054442225': '직영',
                        'uid_dokebi3': '직영',
                        'phone_01044115684': '직영',
                        'uid_zzunga820407': '직영',
                        'phone_01064988113': '슈퍼',
                        'uid_dlwjdqls0813': '슈퍼',
                        'phone_01090909466': '나르미',
                        'phone_01042220059': '나르미',
                        'uid_dlwhdejr77': '나르미',
                        'phone_01090893777': '나르미',
                        'uid_dididirmsid': '나르미',
                        'phone_01049380544': '슈퍼',
                        'uid_cdll27': '슈퍼',
                        'phone_01041332410': '직영',
                        'uid_dnjs96000': '직영',
                        'phone_01039704456': '나르미',
                        'uid_tepery': '나르미',
                        'phone_01025239330': '슈퍼',
                        'uid_roder9330': '슈퍼',
                        'phone_01022224512': '슈퍼',
                        'uid_rksek7763': '슈퍼',
                        'phone_01085403884': '슈퍼',
                        'uid_qwqw1230': '슈퍼',
                        'phone_01040479098': '나르미',
                        'uid_jikrty2621': '나르미',
                        'phone_01068654893': '슈퍼',
                        'uid_cion4893': '슈퍼',
                        'phone_01035064035': '나르미',
                        'uid_jjisik': '나르미',
                        'phone_01038001769': '슈퍼',
                        'uid_Sin69333': '슈퍼',
                        'phone_01094174313': '슈퍼',
                        'uid_gnfcp': '슈퍼',
                        'phone_01045339113': '슈퍼',
                        'uid_wolf0122': '슈퍼',
                        'phone_01064072855': '슈퍼',
                        'uid_esthell2': '슈퍼',
                        'phone_01039945353': '나르미',
                        'uid_jjk73299': '나르미',
                        'phone_01046452907': '슈퍼',
                        'uid_chome0411': '슈퍼',
                        'phone_01049991096': '슈퍼',
                        'uid_dkgee': '슈퍼',
                        'phone_01029915550': '슈퍼',
                        'uid_jin70fa': '슈퍼',
                        'phone_01087059260': '슈퍼',
                        'uid_cghzxc': '슈퍼',
                        'phone_01073789884': '슈퍼',
                        'uid_choijy9219': '슈퍼',
                        'phone_01089302205': '슈퍼',
                        'uid_chlwnstn1226': '슈퍼',
                        'phone_01095126282': '슈퍼',
                        'uid_zuno10': '슈퍼',
                        'phone_01099000232': '직영',
                        'uid_vip1128': '직영',
                        'phone_01044331492': '나르미',
                        'uid_chs33': '나르미',
                        'phone_01098194222': '슈퍼',
                        'uid_cjh2331': '슈퍼',
                        'phone_01056608498': '슈퍼',
                        'uid_epik849812': '슈퍼',
                        'phone_01085065130': '슈퍼',
                        'uid_dkagh3295': '슈퍼',
                        'phone_01057851012': '직영',
                        'uid_riuxioknu': '직영',
                        'phone_01028323995': '직영',
                        'uid_cthanhqb': '직영',
                        'phone_01056641307': '성공',
                        'uid_screenstar': '성공',
                        'phone_01023727221': '직영',
                        'uid_ss10500': '직영',
                        'phone_01085970060': '직영',
                        'uid_kts822300': '직영',
                        'phone_01059336512': '직영',
                        'uid_gywnsdpwl10': '직영',
                        'phone_01030397177': '상생',
                        'uid_zet707': '상생',
                        'phone_01099158611': '성공',
                        'uid_saz1212': '성공',
                        'phone_01082056416': '직영',
                        'uid_youjoon0407': '직영',
                        'phone_01056589664': '성공',
                        'uid_bluesens': '성공',
                        'phone_01035050800': 'BM',
                        'uid_kolon77': 'BM',
                        'phone_01087623602': '직영',
                        'uid_bjw3602': '직영',
                        'phone_01030585896': '성공',
                        'uid_3hk2212': '성공',
                        'phone_01056439969': '직영',
                        'uid_qnfehr1237': '직영',
                        'phone_01088407989': 'BM',
                        'uid_mudark623': 'BM',
                        'phone_01077703289': '직영',
                        'uid_qlsdnsl': '직영',
                        'phone_01033168902': '직영',
                        'uid_tksxkdhwna99': '직영',
                        'phone_01055397207': '직영',
                        'uid_BC720742': '직영',
                        'phone_01026290157': '직영',
                        'uid_my101001': '직영',
                        'phone_01072346097': '직영',
                        'uid_kanghiung': '직영',
                        'phone_01084268623': '성공',
                        'uid_BC862346': '성공',
                        'phone_01065037450': '성공',
                        'uid_kooja79': '성공',
                        'phone_01088569679': '성공',
                        'uid_Good9679': '성공',
                        'phone_01058631372': 'BM',
                        'uid_fks024': 'BM',
                        'phone_01051444441': '직영',
                        'uid_Asd2259': '직영',
                        'phone_01088146134': '상생',
                        'uid_korea6587': '상생',
                        'phone_01076335554': '직영',
                        'uid_bm91bm91': '직영',
                        'phone_01026755482': '상생',
                        'uid_wnsrldihy': '상생',
                        'phone_01045424686': '성공',
                        'uid_rnjs9639': '성공',
                        'phone_01048899272': '직영',
                        'uid_akroto10': '직영',
                        'phone_01059241664': '상생',
                        'uid_sky1sea97': '상생',
                        'phone_01098366557': 'BM',
                        'uid_azxs0790': 'BM',
                        'phone_01058615229': '상생',
                        'uid_ddim5004': '상생',
                        'phone_01075379533': '성공',
                        'uid_qqaazz120000': '성공',
                        'phone_01028115580': '성공',
                        'uid_beatsuya': '성공',
                        'phone_01084310043': '직영',
                        'uid_alsghd33': '직영',
                        'phone_01085157793': '상생',
                        'uid_Himemay184': '상생',
                        'phone_01046515916': '직영',
                        'uid_개인정보처리방침': '직영',
                        'phone_01066988781': '직영',
                        'uid_wizzzzz2491': '직영',
                        'phone_01056322414': '상생',
                        'uid_kzuuya': '상생',
                        'phone_01080989458': '직영',
                        'uid_namh0801': '직영',
                        'phone_01048297999': '성공',
                        'uid_byung9643': '성공',
                        'phone_01038064118': '직영',
                        'uid_win9198': '직영',
                        'phone_01033749936': '직영',
                        'uid_kbc9936': '직영',
                        'phone_01021655947': '성공',
                        'uid_Kk6021': '성공',
                        'phone_01082505746': '상생',
                        'uid_zzlccg445': '상생',
                        'phone_01066873099': '직영',
                        'uid_k7811305': '직영',
                        'phone_01045114445': '상생',
                        'uid_aasdds': '상생',
                        'phone_01065589422': '성공',
                        'uid_nice1250': '성공',
                        'phone_01074965436': '직영',
                        'uid_sksmsk22': '직영',
                        'phone_01021649980': '직영',
                        'uid_kcc518551': '직영',
                        'phone_01094509952': '상생',
                        'uid_wjdgus9887': '상생',
                        'phone_01034898989': '성공',
                        'uid_wowgma2': '성공',
                        'phone_01062223655': '성공',
                        'uid_promisel': '성공',
                        'phone_01084016924': 'BM',
                        'uid_Jongman6189': 'BM',
                        'phone_01062980423': 'BM',
                        'uid_sadf8122': 'BM',
                        'phone_01066652756': '직영',
                        'uid_zzzsss5': '직영',
                        'phone_01097792669': '직영',
                        'uid_tk770322': '직영',
                        'phone_01026708245': '상생',
                        'uid_xkdlass0245': '상생',
                        'phone_01045889854': '성공',
                        'uid_sign222': '성공',
                        'phone_01082552058': '직영',
                        'uid_hyunjin2058': '직영',
                        'phone_01040826360': '상생',
                        'uid_kimli0109': '상생',
                        'phone_01057183351': '상생',
                        'uid_fkdnrtjd': '상생',
                        'phone_01081806691': '성공',
                        'uid_coolnjc': '성공',
                        'phone_01067957475': '직영',
                        'uid_bangho0112': '직영',
                        'phone_01063935129': '직영',
                        'uid_j63935129': '직영',
                        'phone_01023526995': '직영',
                        'uid_njw0414': '직영',
                        'phone_01039172070': '성공',
                        'uid_fbtmdcks31': '성공',
                        'phone_01036933810': '성공',
                        'uid_stp21': '성공',
                        'phone_01022695096': 'BM',
                        'uid_kslove1269': 'BM',
                        'phone_01021948560': '직영',
                        'uid_j1030jhs': '직영',
                        'phone_01083447540': '성공',
                        'uid_qkrtkddlf': '성공',
                        'phone_01042339955': '직영',
                        'uid_snskwks': '직영',
                        'phone_01071332776': '직영',
                        'uid_71332776': '직영',
                        'phone_01072529443': '직영',
                        'uid_pyh9443': '직영',
                        'phone_01098898011': '직영',
                        'uid_jhan1052': '직영',
                        'phone_01077092461': '직영',
                        'uid_wogus9043': '직영',
                        'phone_01062089030': '상생',
                        'uid_popiop123': '상생',
                        'phone_01050601319': '성공',
                        'uid_opop0323': '성공',
                        'phone_01038226593': '성공',
                        'uid_pcs1803': '성공',
                        'phone_01073501388': '성공',
                        'uid_honga1388': '성공',
                        'phone_01051548925': '성공',
                        'uid_cs8925': '성공',
                        'phone_01048695822': '직영',
                        'uid_snns432': '직영',
                        'phone_01084451461': 'BM',
                        'uid_xkxl67': 'BM',
                        'phone_01028788705': 'BM',
                        'uid_qoqudgh456': 'BM',
                        'phone_01043125247': '상생',
                        'uid_abollo1': '상생',
                        'phone_01057734867': '성공',
                        'uid_tgb4ever': '성공',
                        'phone_01048678489': '성공',
                        'uid_tg4ever': '성공',
                        'phone_01022185625': '직영',
                        'uid_dnjs817': '직영',
                        'phone_01089479130': 'BM',
                        'uid_hg97507': 'BM',
                        'phone_01077154649': '직영',
                        'uid_zx0921': '직영',
                        'phone_01042454345': 'BM',
                        'uid_seoseo0314': 'BM',
                        'phone_01088657389': '직영',
                        'uid_eddie6577': '직영',
                        'phone_01093312498': '직영',
                        'uid_bogus2498': '직영',
                        'phone_01073973335': 'BM',
                        'uid_sa003114': 'BM',
                        'phone_01084418283': 'BM',
                        'uid_thdwodyd': 'BM',
                        'phone_01049078688': '직영',
                        'uid_halada011': '직영',
                        'phone_01064655868': '직영',
                        'uid_duddk6022': '직영',
                        'phone_01058638489': '성공',
                        'uid_tgs4ever': '성공',
                        'phone_01035002074': '성공',
                        'uid_aa35002074': '성공',
                        'phone_01095500590': 'BM',
                        'uid_cxz3131': 'BM',
                        'phone_01025248560': '성공',
                        'uid_Dawon51': '성공',
                        'phone_01058741714': '직영',
                        'uid_yousy1128': '직영',
                        'phone_01035523225': '성공',
                        'uid_yeoil486': '성공',
                        'phone_01077953316': '직영',
                        'uid_rkcl1234': '직영',
                        'phone_01096092776': '성공',
                        'uid_ysh2776': '성공',
                        'phone_01038042784': '직영',
                        'uid_onna2776': '직영',
                        'phone_01065219430': '직영',
                        'uid_cole9430': '직영',
                        'phone_01026701866': '직영',
                        'uid_dhkdrkdnl02': '직영',
                        'phone_01071446550': '직영',
                        'uid_eotkd93': '직영',
                        'phone_01036736050': '직영',
                        'uid_rmatja1214': '직영',
                        'phone_01084207505': '상생',
                        'uid_jjj3357': '상생',
                        'phone_01095337575': '직영',
                        'uid_aswq666': '직영',
                        'phone_01042343299': '상생',
                        'uid_3299yu3299': '상생',
                        'phone_01076801653': '직영',
                        'uid_tkddyd778': '직영',
                        'phone_01088861539': '직영',
                        'uid_aqeda': '직영',
                        'phone_01044336385': '직영',
                        'uid_gidrml12': '직영',
                        'phone_01046476973': '상생',
                        'uid_tmddyd9714': '상생',
                        'phone_01082820407': '성공',
                        'uid_BC200532': '성공',
                        'phone_01075099361': '성공',
                        'uid_lee9361': '성공',
                        'phone_01074053712': 'BM',
                        'uid_biomedics': 'BM',
                        'phone_01043663838': 'BM',
                        'uid_mystop1214': 'BM',
                        'phone_01085258088': '성공',
                        'uid_zwzwzwz': '성공',
                        'phone_01089567995': '성공',
                        'uid_nnhs6670': '성공',
                        'phone_01085799951': '성공',
                        'uid_hunt011': '성공',
                        'phone_01037694885': 'BM',
                        'uid_lee1hahaha': 'BM',
                        'phone_01059297202': 'BM',
                        'uid_r78789': 'BM',
                        'phone_01020440978': '성공',
                        'uid_Tack0957': '성공',
                        'phone_01095697982': '직영',
                        'uid_BC533812': '직영',
                        'phone_01082828008': '상생',
                        'uid_luxury8707': '상생',
                        'phone_01022502382': '성공',
                        'uid_imss119': '성공',
                        'phone_01090651819': '성공',
                        'uid_hra0318': '성공',
                        'phone_01026465953': '직영',
                        'uid_csp7687': '직영',
                        'phone_01044006914': '상생',
                        'uid_aa7096': '상생',
                        'phone_01049559963': '성공',
                        'uid_junhan0202': '성공',
                        'phone_01031342157': '직영',
                        'uid_rhfjsrjdia1': '직영',
                        'phone_01056974044': '상생',
                        'uid_ssogi1': '상생',
                        'phone_01027564187': '직영',
                        'uid_sok1038': '직영',
                        'phone_01035410201': '상생',
                        'uid_cat3434': '상생',
                        'phone_01053428451': '상생',
                        'uid_jhj845100': '상생',
                        'phone_01055945572': 'BM',
                        'uid_fiat4408': 'BM',
                        'phone_01055114469': '상생',
                        'uid_B4469011': '상생',
                        'phone_01021952353': '상생',
                        'uid_jang2535': '상생',
                        'phone_01035703210': '성공',
                        'uid_ssssb95': '성공',
                        'phone_01075042474': '직영',
                        'uid_vhtpglehs': '직영',
                        'phone_01059186698': '직영',
                        'uid_junjunghwan1': '직영',
                        'phone_01058408883': 'BM',
                        'uid_wjswls201': 'BM',
                        'phone_01055515588': '성공',
                        'uid_realdal': '성공',
                        'phone_01028176207': 'BM',
                        'uid_jun2817': 'BM',
                        'phone_01021889481': 'BM',
                        'uid_mamigirl1004': 'BM',
                        'phone_01057421370': '직영',
                        'uid_tjdgkr1370': '직영',
                        'phone_01051577745': 'BM',
                        'uid_freehug4610': 'BM',
                        'phone_01064783350': '상생',
                        'uid_mkoq80': '상생',
                        'phone_01048944440': 'BM',
                        'uid_hoya104': 'BM',
                        'phone_01077610715': '상생',
                        'uid_Kaze0715': '상생',
                        'phone_01021432011': '직영',
                        'uid_eksfk711': '직영',
                        'phone_01064244113': '성공',
                        'uid_oppyn': '성공',
                        'phone_01025220677': '성공',
                        'uid_cho0677': '성공',
                        'phone_01089568216': '직영',
                        'uid_csyyyys': '직영',
                        'phone_01050137594': '성공',
                        'uid_zezx20': '성공',
                        'phone_01099546312': 'BM',
                        'uid_ccm7577': 'BM',
                        'phone_01056876099': '상생',
                        'uid_hjjphd': '상생',
                        'phone_01077011158': '상생',
                        'uid_kdkd88': '상생',
                        'phone_01063895509': '직영',
                        'uid_hwangjoil': '직영'},
  'excluded_identity_keys': ['phone_01046515916',
                             'phone_01020582724',
                             'phone_01023061112',
                             'phone_01024348122',
                             'phone_01028607600',
                             'phone_01033651548',
                             'phone_01034929496',
                             'phone_01037959383',
                             'phone_01054464713',
                             'phone_01055535804',
                             'phone_01055987613',
                             'phone_01057430409',
                             'phone_01057901107',
                             'phone_01062852543',
                             'phone_01072210501',
                             'phone_01076736626',
                             'phone_01081144903',
                             'phone_01088832434',
                             'phone_01089701982',
                             'phone_01089831091',
                             'phone_01091144577',
                             'phone_01091895291',
                             'phone_01095064566',
                             'phone_01099665758',
                             'uid_31324577',
                             'uid_BC6626125',
                             'uid_Syk1232',
                             'uid_diqkdndlstod74',
                             'uid_ish2751',
                             'uid_kgw49280',
                             'uid_kingzex333',
                             'uid_ksh9522',
                             'uid_lo154800',
                             'uid_msigumchi',
                             'uid_na0507',
                             'uid_psy524',
                             'uid_qopqop86',
                             'uid_rerere3',
                             'uid_sizz104',
                             'uid_sky624b',
                             'uid_sosms2',
                             'uid_sslove0317',
                             'uid_tg850824',
                             'uid_tnt2772',
                             'uid_umkilyong',
                             'uid_wkdgustlr81',
                             'uid_yes022619']},
 {'area': '대구달서A온나SLA',
  'slug': 'dalseoa_sla',
  'aliases': ['대구달서A온나SLA(DP2605187587)', '대구달서A온나SLA (DP2605187587)', '대구달서A온나SLA', 'DP2605187587'],
  'center_code': 'DP2605187587',
  'team_order': ['bm1팀', 'bm2팀', 'bm3팀', 'bm4팀', '신규'],
  'area_config': {'bm1팀': 2, 'bm2팀': 4, 'bm3팀': 2, 'bm4팀': 0, '신규': 0},
  'team_map_path': '/settings/dalseoa_sla/teamMap',
  'live_path': '/live/dalseoa_sla',
  'weekly_path': '/weekly/dalseoa_sla',
  'required_team_riders': {},
  'identity_team_map': {},
  'excluded_identity_keys': [],
  'name_team_map': {'김도현': 'bm1팀',
                    '안병무': 'bm1팀',
                    '공인표': 'bm1팀',
                    '윤지욱': 'bm1팀',
                    '정성헌': 'bm1팀',
                    '최무열': 'bm1팀',
                    '신준호': 'bm1팀',
                    '김동형': 'bm1팀',
                    '홍성준': 'bm1팀',
                    '정용국': 'bm1팀',
                    '김강탁': 'bm1팀',
                    '소성용': 'bm1팀',
                    '배성진': 'bm1팀',
                    '강상우': 'bm1팀',
                    '고재성': 'bm1팀',
                    '구대훈': 'bm1팀',
                    '권태방': 'bm1팀',
                    '권호찬': 'bm1팀',
                    '김강산': 'bm1팀',
                    '김동규': 'bm1팀',
                    '김민섭': 'bm1팀',
                    '김민수': 'bm1팀',
                    '김세현': 'bm1팀',
                    '김주화': 'bm1팀',
                    '김혜철': 'bm1팀',
                    '박근태': 'bm1팀',
                    '박연호': 'bm1팀',
                    '박준호': 'bm1팀',
                    '서효일': 'bm1팀',
                    '신정오': 'bm1팀',
                    '이경일': 'bm1팀',
                    '이선호': 'bm1팀',
                    '이우석': 'bm1팀',
                    '장기화': 'bm1팀',
                    '전성대': 'bm1팀',
                    '정규진': 'bm1팀',
                    '정승호': 'bm1팀',
                    '정윤수': 'bm1팀',
                    '조은성': 'bm1팀',
                    '진성민': 'bm1팀',
                    '최영준': 'bm1팀',
                    '최윤호': 'bm1팀',
                    '최재혁': 'bm1팀',
                    '최제우': 'bm1팀',
                    '최철민': 'bm1팀',
                    '최효정': 'bm1팀',
                    '피민재': 'bm1팀',
                    '하유정': 'bm1팀',
                    '조원빈': 'bm2팀',
                    '김갑래': 'bm2팀',
                    '기병환': 'bm2팀',
                    '김규태': 'bm2팀',
                    '노영욱': 'bm2팀',
                    '김상태': 'bm2팀',
                    '이태욱': 'bm2팀',
                    '이현우': 'bm2팀',
                    '전동식': 'bm2팀',
                    '정민규': 'bm2팀',
                    '나형수': 'bm2팀',
                    '오성환': 'bm2팀',
                    '최해인': 'bm2팀',
                    '정하나': 'bm2팀',
                    '박재현': 'bm2팀',
                    '임차규': 'bm2팀',
                    '신은호': 'bm2팀',
                    '최재수': 'bm2팀',
                    '유준영': 'bm2팀',
                    '문성호': 'bm2팀',
                    '진형훈': 'bm2팀',
                    '김정원': 'bm2팀',
                    '박장호': 'bm2팀',
                    '이영준': 'bm2팀',
                    '성영현': 'bm2팀',
                    '강이섭': 'bm2팀',
                    '권형태': 'bm2팀',
                    '김민형': 'bm2팀',
                    '김상호': 'bm2팀',
                    '김송이': 'bm2팀',
                    '김은경': 'bm2팀',
                    '김종민': 'bm2팀',
                    '김준태': 'bm2팀',
                    '김지현': 'bm2팀',
                    '김진욱': 'bm2팀',
                    '김창식': 'bm2팀',
                    '김현근': 'bm2팀',
                    '남승훈': 'bm2팀',
                    '남진만': 'bm2팀',
                    '문영우': 'bm2팀',
                    '박대희': 'bm2팀',
                    '박상섭': 'bm2팀',
                    '박은정': 'bm2팀',
                    '박정환': 'bm2팀',
                    '박춘환': 'bm2팀',
                    '박칠오': 'bm2팀',
                    '박홍근': 'bm2팀',
                    '서현아': 'bm2팀',
                    '성지원': 'bm2팀',
                    '손봉식': 'bm2팀',
                    '양주호': 'bm2팀',
                    '이석민': 'bm2팀',
                    '이승준': 'bm2팀',
                    '이우호': 'bm2팀',
                    '이원준': 'bm2팀',
                    '이재형': 'bm2팀',
                    '이지훈': 'bm2팀',
                    '임경목': 'bm2팀',
                    '장영수': 'bm2팀',
                    '장지희': 'bm2팀',
                    '전영한': 'bm2팀',
                    '정대진': 'bm2팀',
                    '정명광': 'bm2팀',
                    '정명일': 'bm2팀',
                    '정진': 'bm2팀',
                    '조명석': 'bm2팀',
                    '최상록': 'bm2팀',
                    '최정걸': 'bm2팀',
                    '허성모': 'bm2팀',
                    '홍부기': 'bm2팀',
                    '황혜진': 'bm2팀',
                    '박성오': 'bm3팀',
                    '박만오': 'bm3팀',
                    '전승열': 'bm3팀',
                    '전소현': 'bm3팀',
                    '이덕순': 'bm3팀',
                    '이진희': 'bm3팀',
                    '김연규': 'bm3팀',
                    '권완용': 'bm3팀',
                    '정영수': 'bm3팀',
                    '임채욱': 'bm3팀',
                    '김재명': 'bm3팀',
                    '배상민': 'bm3팀',
                    '이상룡': 'bm3팀',
                    '이용태': 'bm3팀',
                    '차두성': 'bm3팀',
                    '나형우': 'bm3팀',
                    '고동완': 'bm3팀',
                    '권일근': 'bm3팀',
                    '김정환': 'bm3팀',
                    '김지훈': 'bm3팀',
                    '김현규': 'bm3팀',
                    '남건욱': 'bm3팀',
                    '박상대': 'bm3팀',
                    '박승혁': 'bm3팀',
                    '박정원': 'bm3팀',
                    '박혜경': 'bm3팀',
                    '백미연': 'bm3팀',
                    '백현석': 'bm3팀',
                    '석민수': 'bm3팀',
                    '손명환': 'bm3팀',
                    '송인득': 'bm3팀',
                    '안규리': 'bm3팀',
                    '양기식': 'bm3팀',
                    '엄호대': 'bm3팀',
                    '위혜경': 'bm3팀',
                    '윤영준': 'bm3팀',
                    '이강호': 'bm3팀',
                    '이나경': 'bm3팀',
                    '이동민': 'bm3팀',
                    '이상득': 'bm3팀',
                    '이상익': 'bm3팀',
                    '이상훈': 'bm3팀',
                    '이수연': 'bm3팀',
                    '이재운': 'bm3팀',
                    '장국홍': 'bm3팀',
                    '장용현': 'bm3팀',
                    '정민혁': 'bm3팀',
                    '정의환': 'bm3팀',
                    '최민현': 'bm3팀',
                    '홍영준': 'bm3팀'}},
 {'area': '대구달서온나A',
  'slug': 'dalseo_onnaa',
  'aliases': ['대구달서온나A(DP2509199364)', '대구달서온나A (DP2509199364)', '대구달서온나A', 'DP2509199364'],
  'center_code': 'DP2509199364',
  'team_order': ['마음1', '마음3', '마음4', '신규'],
  'area_config': {'마음1': 7, '마음3': 4, '마음4': 1, '신규': 0},
  'team_map_path': '/settings/dalseo_onnaa/teamMap',
  'live_path': '/live/dalseo_onnaa',
  'weekly_path': '/weekly/dalseo_onnaa',
  'required_team_riders': {},
  'identity_team_map': {},
  'excluded_identity_keys': [],
  'name_team_map': {'박재화': '마음1',
                    '이정호': '마음1',
                    '천수영': '마음1',
                    '김정봉': '마음1',
                    '오창익': '마음1',
                    '배성혁': '마음1',
                    '윤치선': '마음1',
                    '진솔지': '마음1',
                    '전판근': '마음1',
                    '허용준': '마음1',
                    '김종서': '마음1',
                    '이영균': '마음1',
                    '이상걸': '마음1',
                    '정경오': '마음1',
                    '박준민': '마음1',
                    '문석민': '마음1',
                    '권은빈': '마음1',
                    '김경환': '마음1',
                    '나경태': '마음1',
                    '유성진': '마음1',
                    '황성욱': '마음1',
                    '정가연': '마음1',
                    '신재효': '마음1',
                    '박종필': '마음1',
                    '조채은': '마음1',
                    '우상영': '마음1',
                    '지성환': '마음1',
                    '김병수': '마음1',
                    '배시오': '마음1',
                    '안동우': '마음1',
                    '유동혁': '마음1',
                    '한영환': '마음1',
                    '김종호': '마음1',
                    '이영미': '마음1',
                    'WEIMAOSHENG': '마음1',
                    '김보금': '마음1',
                    '이명우': '마음1',
                    '김용진': '마음1',
                    '김진성': '마음1',
                    '김소연': '마음1',
                    'NANLINSHENG': '마음1',
                    '강경원': '마음1',
                    '강민석': '마음1',
                    '강주영': '마음1',
                    '강철': '마음1',
                    '구준영': '마음1',
                    '금미라': '마음1',
                    '김규복': '마음1',
                    '김규태': '마음1',
                    '김낙희': '마음1',
                    '김미경': '마음1',
                    '김민건': '마음1',
                    '김상훈': '마음1',
                    '김성국': '마음1',
                    '김성용': '마음1',
                    '김영우': '마음1',
                    '김유경': '마음1',
                    '김정화': '마음1',
                    '김제웅': '마음1',
                    '김주원': '마음1',
                    '김진우': '마음1',
                    '김창민': '마음1',
                    '김태수': '마음1',
                    '김태현': '마음1',
                    '김하랑': '마음1',
                    '남재화': '마음1',
                    '도기만': '마음1',
                    '도진채': '마음1',
                    '류충열': '마음1',
                    '문종덕': '마음1',
                    '박관호': '마음1',
                    '박대영': '마음1',
                    '박병문': '마음1',
                    '박상현': '마음1',
                    '박성훈': '마음1',
                    '박웅집': '마음1',
                    '박재민': '마음1',
                    '박재현': '마음1',
                    '박준혁': '마음1',
                    '박준현': '마음1',
                    '박지윤': '마음1',
                    '박찬규': '마음1',
                    '방종윤': '마음1',
                    '변재욱': '마음1',
                    '서은숙': '마음1',
                    '성영길': '마음1',
                    '성일호': '마음1',
                    '손재익': '마음1',
                    '송보균': '마음1',
                    '심정민': '마음1',
                    '심진섭': '마음1',
                    '안재형': '마음1',
                    '양봉환': '마음1',
                    '오임경': '마음1',
                    '오정현': '마음1',
                    '유상범': '마음1',
                    '유성혜': '마음1',
                    '유소담': '마음1',
                    '윤미성': '마음1',
                    '윤영수': '마음1',
                    '윤영환': '마음1',
                    '이강현': '마음1',
                    '이기영': '마음1',
                    '이상민': '마음1',
                    '이상영': '마음1',
                    '이상욱': '마음1',
                    '이선미': '마음1',
                    '이성구': '마음1',
                    '이성애': '마음1',
                    '이세비': '마음1',
                    '이수영': '마음1',
                    '이승준': '마음1',
                    '이승훈': '마음1',
                    '이영길': '마음1',
                    '이영용': '마음1',
                    '이장훈': '마음1',
                    '이재신': '마음1',
                    '이정주': '마음1',
                    '이정훈': '마음1',
                    '이종하': '마음1',
                    '이지언': '마음1',
                    '이진기': '마음1',
                    '이헌영': '마음1',
                    '이혁재': '마음1',
                    '임용우': '마음1',
                    '임용훈': '마음1',
                    '임유진': '마음1',
                    '임윤정': '마음1',
                    '임준현': '마음1',
                    '장은실': '마음1',
                    '장현욱': '마음1',
                    '전인엽': '마음1',
                    '정웅일': '마음1',
                    '정의동': '마음1',
                    '정현보': '마음1',
                    '조동현': '마음1',
                    '조수빈': '마음1',
                    '진승표': '마음1',
                    '최경민': '마음1',
                    '최은실': '마음1',
                    '최정훈': '마음1',
                    '최주영': '마음1',
                    '최준형': '마음1',
                    '하윤정': '마음1',
                    '한지훈': '마음1',
                    '함정수': '마음1',
                    '허성혁': '마음1',
                    '허정백': '마음1',
                    '황인규': '마음1',
                    '황종욱': '마음1',
                    '전재옥': '마음3',
                    '박정현': '마음3',
                    '정은경': '마음3',
                    '한윤희': '마음3',
                    '김정열': '마음3',
                    '문재훈': '마음3',
                    '서석구': '마음3',
                    '오세원': '마음3',
                    '이낙철': '마음3',
                    '김제헌': '마음3',
                    '정재균': '마음3',
                    '남현우': '마음3',
                    '제갈현': '마음3',
                    '최홍석': '마음3',
                    '김리현': '마음3',
                    '김민웅': '마음3',
                    '김성욱': '마음3',
                    '김익한': '마음3',
                    '김재준': '마음3',
                    '박명규': '마음3',
                    '박태안': '마음3',
                    '성동훈': '마음3',
                    '윤종홍': '마음3',
                    '이우훈': '마음3',
                    '이정석': '마음3',
                    '전재욱': '마음3',
                    '최영섭': '마음3',
                    '최종광': '마음3',
                    '추진태': '마음3',
                    '허말순': '마음3',
                    '현승희': '마음3',
                    '황용민': '마음3',
                    '지영주': '마음4',
                    '유철진': '마음4',
                    '이종균': '마음4',
                    '박윤지': '마음4',
                    '홍재림': '마음4',
                    '이성덕': '마음4',
                    '이종운': '마음4',
                    '김병기': '마음4',
                    '김세린': '마음4',
                    '김용호': '마음4',
                    '이상규': '마음4',
                    '이재범': '마음4',
                    '이정미': '마음4',
                    '장우식': '마음4',
                    '정재익': '마음4',
                    '조덕래': '마음4',
                    '천장현': '마음4',
                    '최병열': '마음4',
                    '허문구': '마음4'}},
 {'area': '대구수성C온나',
  'slug': 'suseongc',
  'aliases': ['대구수성C온나(DP2606010723)', '대구수성C온나 (DP2606010723)', '대구수성C온나', 'DP2606010723'],
  'center_code': 'DP2606010723',
  'team_order': ['마음', 'BDMJ', '신규'],
  'area_config': {'마음': 1, 'BDMJ': 1, '신규': 0},
  'team_map_path': '/settings/suseongc/teamMap',
  'live_path': '/live/suseongc',
  'weekly_path': '/weekly/suseongc',
  'required_team_riders': {},
  'identity_team_map': {},
  'excluded_identity_keys': [],
  'name_team_map': {'김성준': '마음',
                    '김형민': '마음',
                    '배민석': '마음',
                    '신손미': '마음',
                    '이원현': '마음',
                    '정재곤': '마음',
                    '정준영': '마음',
                    '김근식': 'BDMJ',
                    '강상기': 'BDMJ',
                    '홍찬윤': 'BDMJ',
                    '강석진': 'BDMJ',
                    '강성모': 'BDMJ',
                    '강철구': 'BDMJ',
                    '강현기': 'BDMJ',
                    '김경환': 'BDMJ',
                    '김경훈': 'BDMJ',
                    '김기억': 'BDMJ',
                    '김도식': 'BDMJ',
                    '김동현': 'BDMJ',
                    '김명일': 'BDMJ',
                    '김명현': 'BDMJ',
                    '김민찬': 'BDMJ',
                    '김복룡': 'BDMJ',
                    '김상훈': 'BDMJ',
                    '김성우': 'BDMJ',
                    '김영철': 'BDMJ',
                    '김용철': 'BDMJ',
                    '김우주': 'BDMJ',
                    '김준상': 'BDMJ',
                    '김진흥': 'BDMJ',
                    '김초혜': 'BDMJ',
                    '김효용': 'BDMJ',
                    '박민욱': 'BDMJ',
                    '박준민': 'BDMJ',
                    '석정균': 'BDMJ',
                    '손영빈': 'BDMJ',
                    '손자수': 'BDMJ',
                    '손효상': 'BDMJ',
                    '송윤미': 'BDMJ',
                    '송정자': 'BDMJ',
                    '송한솔': 'BDMJ',
                    '신순미': 'BDMJ',
                    '신정현': 'BDMJ',
                    '오강식': 'BDMJ',
                    '오명준': 'BDMJ',
                    '오세출': 'BDMJ',
                    '오세현': 'BDMJ',
                    '우상수': 'BDMJ',
                    '이동수': 'BDMJ',
                    '이동협': 'BDMJ',
                    '이상구': 'BDMJ',
                    '이상운': 'BDMJ',
                    '이상철': 'BDMJ',
                    '이슬기': 'BDMJ',
                    '이승재': 'BDMJ',
                    '이재정': 'BDMJ',
                    '이준원': 'BDMJ',
                    '이태원': 'BDMJ',
                    '이현동': 'BDMJ',
                    '임미영': 'BDMJ',
                    '장대식': 'BDMJ',
                    '장재근': 'BDMJ',
                    '정병준': 'BDMJ',
                    '정병철': 'BDMJ',
                    '정성원': 'BDMJ',
                    '정을갑': 'BDMJ',
                    '정인기': 'BDMJ',
                    '정철민': 'BDMJ',
                    '조정민': 'BDMJ',
                    '천기준': 'BDMJ',
                    '한용규': 'BDMJ',
                    '황재상': 'BDMJ',
                    '황호진': 'BDMJ'}},
 {'area': '표준대구중A주식회사바이온커넥티드',
  'slug': 'junggua_bion',
  'aliases': ['표준대구중A주식회사바이온커넥티드(DP2509099587)', '표준대구중A주식회사바이온커넥티드 (DP2509099587)', '표준대구중A주식회사바이온커넥티드', 'DP2509099587'],
  'center_code': 'DP2509099587',
  'team_order': ['더플러스', '썬더', '몬스터', '신규'],
  'area_config': {'더플러스': 5, '썬더': 1, '몬스터': 3, '신규': 0},
  'team_map_path': '/settings/junggua_bion/teamMap',
  'live_path': '/live/junggua_bion',
  'weekly_path': '/weekly/junggua_bion',
  'required_team_riders': {},
  'identity_team_map': {},
  'excluded_identity_keys': [],
  'name_team_map': {'민병수': '더플러스',
                    '최호영': '더플러스',
                    '엄태일': '더플러스',
                    '오선찬': '더플러스',
                    '정용철': '더플러스',
                    '임성현': '더플러스',
                    '장현식': '더플러스',
                    '이승훈': '더플러스',
                    '이홍우': '더플러스',
                    '정원용': '더플러스',
                    '고선모': '더플러스',
                    '권시환': '더플러스',
                    '김유섭': '더플러스',
                    '서도원': '더플러스',
                    '김범주': '더플러스',
                    '이동규': '더플러스',
                    '손수민': '더플러스',
                    '김영민': '더플러스',
                    '강정호': '더플러스',
                    '권재성': '더플러스',
                    '김건우': '더플러스',
                    '김권민': '더플러스',
                    '김동훈': '더플러스',
                    '김영아': '더플러스',
                    '김정수': '더플러스',
                    '김진현': '더플러스',
                    '김태윤': '더플러스',
                    '김홍식': '더플러스',
                    '나성복': '더플러스',
                    '목성연': '더플러스',
                    '문천수': '더플러스',
                    '박진석': '더플러스',
                    '배규광': '더플러스',
                    '서상교': '더플러스',
                    '시영기': '더플러스',
                    '양지성': '더플러스',
                    '이광춘': '더플러스',
                    '이상탁': '더플러스',
                    '이슬비': '더플러스',
                    '이정윤': '더플러스',
                    '임세규': '더플러스',
                    '전종대': '더플러스',
                    '조원준': '더플러스',
                    '조형철': '더플러스',
                    '최성재': '더플러스',
                    '최유미': '더플러스',
                    '황태일': '더플러스',
                    '안태현': '썬더',
                    '안순애': '썬더',
                    '손성인': '썬더',
                    '이기윤': '썬더',
                    '탁은희': '썬더',
                    '권기덕': '썬더',
                    '신봉우': '썬더',
                    '김동진': '썬더',
                    '오석운': '썬더',
                    '양동헌': '몬스터',
                    '이성민': '몬스터',
                    '김예찬': '몬스터',
                    '김기태': '몬스터',
                    '신재섭': '몬스터',
                    '정기홍': '몬스터',
                    '김하늘': '몬스터',
                    '남은석': '몬스터',
                    '김동현': '몬스터',
                    '조유라': '몬스터',
                    '김태수': '몬스터',
                    '강대호': '몬스터',
                    '권재준': '몬스터',
                    '김대운': '몬스터',
                    '임현욱': '몬스터',
                    '윤병철': '몬스터',
                    '이연빈': '몬스터',
                    '강민호': '몬스터',
                    '강정훈': '몬스터',
                    '김경덕': '몬스터',
                    '김경민': '몬스터',
                    '김성용': '몬스터',
                    '김성훈': '몬스터',
                    '김준희': '몬스터',
                    '김지니': '몬스터',
                    '박경수': '몬스터',
                    '박성훈': '몬스터',
                    '박세만': '몬스터',
                    '박정민': '몬스터',
                    '백승헌': '몬스터',
                    '유선희': '몬스터',
                    '이진승': '몬스터',
                    '장영삼': '몬스터',
                    '전재민': '몬스터',
                    '조경대': '몬스터',
                    '조익현': '몬스터',
                    '최진호': '몬스터',
                    '최홍찬': '몬스터'}}]

DAY_TARGETS = {
    0: [19, 18, 30, 23],
    1: [19, 18, 30, 23],
    2: [19, 18, 30, 23],
    3: [19, 18, 30, 23],
    4: [21, 21, 32, 26],
    5: [27, 22, 36, 25],
    6: [29, 22, 35, 24],
}

SPECIAL_DAY_TARGET_WEEKDAY = {
    "2026-05-25": 6,
    "2026-06-03": 6,
    "2026-07-17": 6,
    "2026-08-17": 6,
    
}


def schedule_weekday(date_value):
    """특별일은 목표 물량뿐 아니라 SLA 시간 구간도 지정 요일 기준으로 적용합니다."""
    return SPECIAL_DAY_TARGET_WEEKDAY.get(date_value.strftime("%Y-%m-%d"), date_value.weekday())


def uses_weekend_schedule(date_value):
    return schedule_weekday(date_value) >= 5

PERIODS = ["morning", "afternoon", "evening", "midnight"]
PERIOD_LABELS = {
    "morning": "오전피크",
    "afternoon": "오후논피크",
    "evening": "저녁피크",
    "midnight": "심야논피크",
    "excluded": "미포함시간",
}



def _close_chrome_render_session():
    global CHROME_RENDER_CDP_SESSION, CHROME_RENDER_CDP_PAGE
    session = CHROME_RENDER_CDP_SESSION
    CHROME_RENDER_CDP_SESSION = None
    CHROME_RENDER_CDP_PAGE = None
    if session is not None:
        try:
            session.detach()
        except Exception:
            pass


def _get_chrome_render_session(context, page):
    """동일 Page target에는 CDP 세션 1개만 생성해 재사용합니다."""
    global CHROME_RENDER_CDP_SESSION, CHROME_RENDER_CDP_PAGE
    if CHROME_RENDER_CDP_SESSION is not None and CHROME_RENDER_CDP_PAGE is page:
        return CHROME_RENDER_CDP_SESSION

    _close_chrome_render_session()
    session = context.new_cdp_session(page)
    CHROME_RENDER_CDP_SESSION = session
    CHROME_RENDER_CDP_PAGE = page
    return session


def keep_chrome_rendering(context, page):
    """Chrome 렌더링 유지. CDP 세션은 반복 생성하지 않고 재사용합니다."""
    try:
        page.bring_to_front()
    except Exception:
        pass

    try:
        current = page.viewport_size or {}
        if (
            int(current.get("width") or 0) != COLLECTION_VIEWPORT_WIDTH
            or int(current.get("height") or 0) != COLLECTION_VIEWPORT_HEIGHT
        ):
            page.set_viewport_size({
                "width": COLLECTION_VIEWPORT_WIDTH,
                "height": COLLECTION_VIEWPORT_HEIGHT,
            })
    except Exception:
        pass

    try:
        session = _get_chrome_render_session(context, page)
    except Exception:
        return

    try:
        info = session.send("Browser.getWindowForTarget")
        window_id = info.get("windowId")
        if window_id is not None:
            session.send("Browser.setWindowBounds", {
                "windowId": window_id,
                "bounds": {
                    "left": -(COLLECTION_VIEWPORT_WIDTH + 200),
                    "top": 20,
                    "width": COLLECTION_VIEWPORT_WIDTH,
                    "height": COLLECTION_VIEWPORT_HEIGHT,
                    "windowState": "normal",
                },
            })
    except Exception:
        # 세션이 실제로 끊긴 경우 다음 호출에서 한 번만 다시 생성합니다.
        _close_chrome_render_session()
        return

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

def split_hourly_by_sla(hourly, date_value=None):
    h = list(hourly or [])[:24]
    if len(h) < 24:
        h += [0] * (24 - len(h))
    if date_value is None:
        date_value = business_date(datetime.now())
    weekend = uses_weekend_schedule(date_value)

    # 미포함은 표시만 하고 게이지/목표 달성 계산에는 절대 포함하지 않음
    morning_excluded = sum(h[6:9])        # 06,07,08
    midnight_excluded = sum(h[0:6])      # 00,01,02,03,04,05

    if weekend:
        morning = sum(h[9:14])           # 토일 09,10,11,12,13
        afternoon = sum(h[14:17])        # 토일 14,15,16
    else:
        morning = sum(h[9:13])           # 평일 09,10,11,12
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
    # business_date 기준으로 특별일의 주말형 SLA 시간표까지 함께 적용합니다.
    weekend = uses_weekend_schedule(business_date(now))

    # SLA 포함 구간 기준입니다.
    # 06~08, 00~05는 미포함 표시 구간이라 게이지/달성률에는 넣지 않습니다.
    if 0 <= h < 9:
        return "excluded"

    if weekend:
        if 9 <= h < 14:
            return "morning"
        if 14 <= h < 17:
            return "afternoon"
    else:
        if 9 <= h < 13:
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




def normalize_team_for_area(team, area_name=None):
    """권역별 표준 팀명으로 변환합니다."""
    area_name = area_name or AREA_NAME
    team = norm(team)

    if area_name == "달서B":
        if team in ("마음", "마음팀", "THE +", "THE +팀", "THE+", "THE+팀"):
            return "마음팀"

    if area_name == "중구A":
        if team in ("마음", "마음팀", "THE +", "THE +팀", "THE+", "THE+팀"):
            return "THE +팀"

    return team


def migrate_team_map_names():
    """Firebase teamMap에 남아 있는 예전 팀명을 권역별 현재 이름으로 실제 저장까지 정리합니다."""
    global TEAM_MAP_CACHE
    init_firebase()
    ref = db.reference(TEAM_MAP_PATH)
    raw = ref.get() or {}
    if not isinstance(raw, dict):
        raw = {}

    migrated = {}
    updates = {}
    for rider_name, old_team in raw.items():
        clean_name = norm(rider_name)
        new_team = normalize_team_for_area(old_team, AREA_NAME)
        migrated[clean_name] = new_team
        if norm(old_team) != new_team:
            updates[clean_name] = new_team

    if updates:
        ref.update(updates)
        debug_log(f"{AREA_NAME} teamMap 팀명 마이그레이션 완료: {len(updates)}명")
        for rider_name, team in list(updates.items())[:20]:
            debug_log(f"  {rider_name} -> {team}")
    else:
        debug_log(f"{AREA_NAME} teamMap 팀명 마이그레이션: 변경 없음")

    TEAM_MAP_CACHE = migrated
    return migrated



def team_map_dirty_flag(slug=None):
    # API가 기사이동을 저장했음을 Collector에 알리는 로컬 신호 파일
    clean_slug = norm(slug or CURRENT_SLUG)
    return BASE_DIR / f".teammap_dirty_{clean_slug}.flag"


def load_team_map_cached():
    # 센터별 teamMap 메모리 캐시
    # 최초/1시간 만료/기사이동 dirty signal 때만 Firebase 전체 READ
    global TEAM_MAP_CACHE

    slug = norm(CURRENT_SLUG)
    now_mono = time.monotonic()
    flag = team_map_dirty_flag(slug)

    cached = TEAM_MAP_CACHE_BY_SLUG.get(slug)
    cached_at = float(TEAM_MAP_CACHE_AT_BY_SLUG.get(slug, 0) or 0)
    cache_fresh = cached is not None and (now_mono - cached_at) < TEAM_MAP_CACHE_TTL_SECONDS

    if cache_fresh and not flag.exists():
        TEAM_MAP_CACHE = cached
        return cached

    loaded = migrate_team_map_names()
    TEAM_MAP_CACHE_BY_SLUG[slug] = loaded
    TEAM_MAP_CACHE_AT_BY_SLUG[slug] = now_mono
    TEAM_MAP_CACHE = loaded

    try:
        flag.unlink(missing_ok=True)
    except Exception:
        pass

    return loaded

def firebase_safe_key(value):
    """Firebase key 금지문자를 제거한 안정적인 문자열을 만듭니다."""
    value = norm(value)
    return re.sub(r'[.#$\[\]/]', '_', value)


def rider_team_keys(name, phone="", user_id="", include_name=True):
    """동명이인 충돌 방지용 기사 식별키. phone_은 정상 010 11자리만 허용합니다."""
    keys = []
    phone_key = normalize_mobile_phone(phone)
    if phone_key:
        keys.append("phone_" + phone_key)
    user_key = firebase_safe_key(user_id)
    if user_key:
        keys.append("uid_" + user_key)
    name_key = norm(name)
    if include_name and name_key:
        keys.append(name_key)
    return list(dict.fromkeys(keys))

def team_of(name, phone="", user_id=""):
    global TEAM_MAP_CACHE
    name = norm(name)
    if TEAM_MAP_CACHE is None:
        try:
            TEAM_MAP_CACHE = load_team_map_cached()
            debug_log(f"teamMap 로드 완료: {len(TEAM_MAP_CACHE)}명 / {AREA_NAME}")
        except Exception as e:
            print(f"[경고] {AREA_NAME} teamMap 로드 실패: {e}")
            TEAM_MAP_CACHE = {}
    # 중구A 이관 명단은 이름이 아닌 전화번호/userId로만 확정합니다.
    # 동명이인은 절대 이름만으로 같은 소속에 넣지 않습니다.
    for identity_key in rider_team_keys(name, phone, user_id, include_name=False):
        fixed_team = IDENTITY_TEAM_MAP.get(identity_key)
        if fixed_team in TEAM_ORDER:
            return fixed_team

    mapped = None
    matched_key = None
    include_name_lookup = AREA_NAME != "중구A"
    for lookup_key in rider_team_keys(name, phone, user_id, include_name=include_name_lookup):
        candidate = normalize_team_for_area(TEAM_MAP_CACHE.get(lookup_key), AREA_NAME)
        if candidate in TEAM_ORDER:
            mapped = candidate
            matched_key = lookup_key
            break

    # 전화번호/userId 고유키를 우선하고, 없을 때만 기존 이름 key를 하위 호환으로 사용합니다.
    if mapped in TEAM_ORDER:
        return mapped
    # 달서A/B 기존 고정 명단은 유지하되, 중구A는 이름 단독 매칭을 금지합니다.
    if AREA_NAME != "중구A":
        for team, names in REQUIRED_TEAM_RIDERS.items():
            if name in {norm(x) for x in names}:
                return team
    # 어느 팀에도 등록되지 않은 새 기사는 자동으로 신규 팀에 배정합니다.
    return "신규" if "신규" in TEAM_ORDER else (TEAM_ORDER[0] if TEAM_ORDER else "신규")


def stable_team_keys(name="", phone="", user_id=""):
    """기사 이동/팀 저장에 사용하는 고유키. 이름은 절대 포함하지 않습니다."""
    return rider_team_keys(name, phone, user_id, include_name=False)


def canonical_rider_key(rider):
    """화면/관리용 기사 고유키. 정상 전화번호 우선, 없으면 userId를 사용합니다."""
    rider = rider or {}
    keys = stable_team_keys(rider.get("name", ""), rider.get("phone", ""), rider.get("userId", ""))
    return keys[0] if keys else ""

def resolve_team_safely(rider, duplicate_names=None):
    """
    팀 분류 최종판정.
    - 전화번호/userId가 있으면 그 고유키만 우선 사용
    - 동명이인은 이름 기반 teamMap/고정명단을 절대 사용하지 않음
    - 이름 기반 레거시 매핑은 현재 권역에서 이름이 유일한 기사에게만 허용
    """
    global TEAM_MAP_CACHE
    rider = rider or {}
    name = norm(rider.get("name", ""))
    phone = rider.get("phone", "")
    user_id = rider.get("userId", "")
    duplicate_names = duplicate_names or set()

    if TEAM_MAP_CACHE is None:
        try:
            TEAM_MAP_CACHE = load_team_map_cached()
        except Exception:
            TEAM_MAP_CACHE = {}

    # ===== TNT MANUAL MOVE KEYS EXACT 2026-09 =====
    # 기존 teamMap 전체가 아니라 사용자가 직접 이동한 기사 특수키만 최우선 적용합니다.
    for key in stable_team_keys(name, phone, user_id):
        if key.startswith("phone_"):
            manual_key = "phone_manual_" + key[len("phone_"):]
        elif key.startswith("uid_"):
            manual_key = "uid_manual_" + key[len("uid_"):]
        else:
            continue
        moved = normalize_team_for_area((TEAM_MAP_CACHE or {}).get(manual_key), AREA_NAME)
        if moved in TEAM_ORDER:
            return moved

    # 1) 코드에 내장된 안정 식별자 고정팀
    for key in stable_team_keys(name, phone, user_id):
        fixed = normalize_team_for_area(IDENTITY_TEAM_MAP.get(key), AREA_NAME)
        if fixed in TEAM_ORDER:
            return fixed

    # 2) Firebase teamMap의 안정 식별자
    for key in stable_team_keys(name, phone, user_id):
        mapped = normalize_team_for_area((TEAM_MAP_CACHE or {}).get(key), AREA_NAME)
        if mapped in TEAM_ORDER:
            return mapped

    # 3) 이름이 중복되지 않을 때만 과거 이름키를 하위호환으로 허용
    if name and name not in duplicate_names:
        mapped = normalize_team_for_area((TEAM_MAP_CACHE or {}).get(name), AREA_NAME)
        if mapped in TEAM_ORDER:
            return mapped

        # 신규 DP 초기 명단: 이름이 유일한 기사에게만 적용합니다.
        # TNT LIVE 기사관리에서 저장된 teamMap이 위에서 먼저 적용되므로
        # 이후 수동 팀 이동은 초기 엑셀 명단보다 항상 우선합니다.
        initial_team = normalize_team_for_area(NAME_TEAM_MAP.get(name), AREA_NAME)
        if initial_team in TEAM_ORDER:
            return initial_team

        # 달서A/B 고정명단도 이름이 유일할 때만 사용
        if AREA_NAME != "중구A":
            for team, names in REQUIRED_TEAM_RIDERS.items():
                if name in {norm(x) for x in names}:
                    return team

    return "신규" if "신규" in TEAM_ORDER else (TEAM_ORDER[0] if TEAM_ORDER else "신규")


def finalize_rider_identity_and_teams(riders):
    """중복 제거 후 기사ID와 팀을 최종 확정합니다."""
    riders = list(riders or [])
    name_counts = {}
    for r in riders:
        nm = norm(r.get("name", ""))
        if nm:
            name_counts[nm] = name_counts.get(nm, 0) + 1
    duplicate_names = {nm for nm, cnt in name_counts.items() if cnt > 1}

    if duplicate_names:
        debug_log("동명이인 감지(이름 매핑 차단):", ", ".join(sorted(duplicate_names)))

    seen_keys = {}
    for r in riders:
        r["riderKey"] = canonical_rider_key(r)
        r["team"] = resolve_team_safely(r, duplicate_names)
        key = r.get("riderKey", "")
        if key:
            if key in seen_keys:
                print("[경고] riderKey 중복:", key, seen_keys[key], r.get("name", ""))
            else:
                seen_keys[key] = r.get("name", "")
    return riders

def to_int(value):
    try:
        return int(str(value).replace(",", "").strip())
    except Exception:
        return 0


def norm(value):
    return str(value).replace("\u200b", "").replace("\ufeff", "").strip()


def normalize_phone(value):
    return re.sub(r"\D", "", str(value or ""))


# ===== TNT RIDER IDENTITY FIX 2026-09 =====
def normalize_mobile_phone(value):
    """기사 고유식별에 사용할 수 있는 정상 국내 010 휴대폰번호만 반환합니다."""
    digits = normalize_phone(value)
    if digits.startswith("82") and len(digits) == 12 and digits[2:4] == "10":
        digits = "0" + digits[2:]
    if len(digits) == 11 and digits.startswith("010"):
        return digits
    return ""


def phone_like_fragment(value):
    """정상번호와의 잘림 중복 판정에만 쓰는 약한 전화번호 조각."""
    digits = normalize_phone(value)
    if digits.startswith("82") and len(digits) >= 9:
        digits = "0" + digits[2:]
    if 7 <= len(digits) <= 10 and digits.startswith("010"):
        return digits
    return ""

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
    2026-08 배민커넥트비즈 신규 배달현황 구조 대응.

    고정 컬럼:
      이름 → 운행상태 → 아이디 → 휴대폰번호

    실적 컬럼:
      총 배달완료(1)
      → SLA 배달완료[푸드, 비마트, 배민스토어, 합계](4)
      → SLA 거절[푸드, 비마트, 배민스토어, 합계](4)
      → SLA 배차취소[푸드, 비마트, 배민스토어, 합계](4)
      → SLA 배달취소(라이더귀책)[푸드, 비마트, 배민스토어, 합계](4)
      → SLA 슬롯별 배달완료[오전, 오후, 저녁, 심야](4)
      → SLA 시간외 배달완료(1)
      → 00~23시 시간대별 완료(24)

    기사 이름과 아이디를 '전화번호 바로 앞 텍스트'로 추정하지 않고,
    실제 컬럼 헤더의 x좌표와 같은 행의 셀을 직접 매칭합니다.
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
      function isIntText(t){ return /^-?\d{1,7}$/.test(String(t||'').replace(/,/g,'').trim()); }
      function toInt(t){
        const n = parseInt(String(t||'0').replace(/,/g,'').trim(),10);
        return Number.isFinite(n) ? n : 0;
      }
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

      const badLegalNames = new Set([
        '개인정보처리방침','이용약관','고객센터','공지사항','회사소개','사업자정보',
        '서비스이용약관','위치기반서비스이용약관'
      ]);

      const nodes = Array.from(document.querySelectorAll('body *'))
        .filter(isLeafText)
        .map(el => {
          const r = el.getBoundingClientRect();
          return {
            el,
            text:norm(textOf(el)),
            left:r.left, right:r.right, top:r.top, bottom:r.bottom,
            cx:r.left+r.width/2, cy:r.top+r.height/2,
            width:r.width, height:r.height
          };
        });

      function findHeader(...names){
        let candidates = nodes.filter(n =>
          names.some(name =>
            n.text === name ||
            n.text.replace(/\s/g,'') === String(name).replace(/\s/g,'')
          )
        );
        // 표의 실제 컬럼 헤더는 필터/메뉴보다 아래쪽에 있으므로 가장 아래 후보를 사용합니다.
        candidates = candidates
          .filter(n => n.width > 0 && n.height > 0)
          .sort((a,b)=>b.top-a.top);
        return candidates[0] || null;
      }

      const identityHeaders = {
        name: findHeader('이름'),
        status: findHeader('운행상태'),
        userId: findHeader('아이디'),
        phone: findHeader('휴대폰번호')
      };

      const allDayHeader = findHeader('총 배달완료');

      // 00~23시 헤더를 실제 x좌표 기준으로 확보합니다.
      const hourHeaders = [];
      for (const n of nodes) {
        if (!hourRe.test(n.text)) continue;
        const h = parseInt(n.text.replace(/\D/g,''),10);
        if (h >= 0 && h <= 23) hourHeaders.push({...n, hour:h});
      }
      const hourMap = {};
      for (const h of hourHeaders) {
        if (!hourMap[h.hour] || h.top > hourMap[h.hour].top) hourMap[h.hour] = h;
      }
      const hours = [];
      for (let h=0; h<24; h++) if (hourMap[h]) hours.push(hourMap[h]);

      function nearestCell(row, header, predicate=null, maxDx=90){
        if (!header) return null;
        let best = null;
        for (const cell of row) {
          if (predicate && !predicate(cell)) continue;
          const dx = Math.abs(cell.cx - header.cx);
          if (dx > Math.max(maxDx, header.width * 2.4)) continue;
          const score = dx + Math.abs(cell.width-header.width)*0.03;
          if (!best || score < best.score) best = {cell, score};
        }
        return best ? best.cell : null;
      }

      function cleanNameCandidate(t){
        t = norm(t);
        if (!t || badLegalNames.has(t)) return '';
        if (phoneRe.test(t) || /^\d+$/.test(t)) return '';
        if (/^(운행중|운행\s*종료)$/.test(t.replace(/\s+/g,''))) return '';
        if (['이름','아이디','휴대폰번호','운행상태'].includes(t)) return '';
        return t;
      }

      // 전화번호는 기사행을 찾는 가장 안정적인 앵커로 사용합니다.
      const phoneNodes = nodes.filter(n => exactPhoneRe.test(n.text));

      // 시간 헤더가 아직 가로 렌더링되지 않은 경우에도 기사 신원정보는 정확히 읽도록 raw 대신
      // 현재 행 전체를 함께 반환합니다. parse_row_lines가 신규 구조 fallback을 처리합니다.
      for (const phoneNode of phoneNodes) {
        const phone = phoneNode.text.match(phoneRe)?.[0];
        if (!phone) continue;
        const key = phoneKey(phone);
        if (!key) continue;

        const row = nodes
          .filter(x =>
            Math.abs(x.cy - phoneNode.cy) <= 14 &&
            x.height > 0 && x.height <= 90 &&
            x.text.length <= 80
          )
          .sort((a,b)=> Math.abs(a.left-b.left)>2 ? a.left-b.left : a.top-b.top);

        const texts = row.map(x=>x.text);

        // 신규 UI 핵심: 이름과 아이디를 헤더 x좌표로 분리합니다.
        let nameCell = nearestCell(row, identityHeaders.name, c => !!cleanNameCandidate(c.text), 110);
        let userIdCell = nearestCell(
          row,
          identityHeaders.userId,
          c => c.text && !phoneRe.test(c.text) && !c.text.includes('운행'),
          110
        );
        // 운행상태는 인접 기사 행의 상태가 섞이면 접속자 수가 잘못 잡히므로
        // 휴대폰 셀과 세로 중심이 거의 같은 셀만 허용하고 정확히 두 상태만 인정합니다.
        const statusRow = row.filter(c => Math.abs(c.cy - phoneNode.cy) <= 6);
        let statusCell = nearestCell(
          statusRow,
          identityHeaders.status,
          c => /^(운행중|운행종료)$/.test(c.text.replace(/\s+/g,'')),
          110
        );

        let name = nameCell ? cleanNameCandidate(nameCell.text) : '';
        let userId = userIdCell ? norm(userIdCell.text) : '';
        let status = statusCell && statusCell.text.replace(/\s/g,'').includes('운행중')
          ? '운행중' : '운행 종료';

        const phoneIdx = row.findIndex(x => exactPhoneRe.test(x.text));

        // 헤더가 순간적으로 렌더링되지 않았을 때의 보조 fallback.
        // 신규 고정열 순서: 이름 → 운행상태 → 아이디 → 휴대폰번호.
        if ((!name || !userId) && phoneIdx >= 0) {
          const left = row.slice(0, phoneIdx);
          const statusIdx = left.findIndex(x => x.text.replace(/\s/g,'') === '운행중' || x.text.replace(/\s/g,'') === '운행종료');

          if (!name) {
            const candidates = (statusIdx >= 0 ? left.slice(0, statusIdx) : left)
              .map(x=>cleanNameCandidate(x.text))
              .filter(Boolean);
            name = candidates.length ? candidates[candidates.length-1] : '';
          }

          if (!userId) {
            const afterStatus = statusIdx >= 0 ? left.slice(statusIdx+1) : left;
            const candidates = afterStatus
              .map(x=>norm(x.text))
              .filter(t => t && t !== name && !phoneRe.test(t) && !/운행/.test(t));
            userId = candidates.length ? candidates[candidates.length-1] : '';
          }

          if (statusIdx >= 0) {
            status = left[statusIdx].text.replace(/\s/g,'').includes('운행중') ? '운행중' : '운행 종료';
          }
        }

        // 아이디가 이름과 동일하게 잡히는 비정상 케이스를 방지합니다.
        if (userId === name) userId = '';

        if (!name || badLegalNames.has(name)) {
          out.push({__debugSkip:true, reason:'bad_name_new_ui', phone, userId, raw:texts});
          continue;
        }

        if (seen.has(key)) {
          out.push({__debugSkip:true, reason:'duplicate_phone', name, phone, raw:texts});
          continue;
        }
        seen.add(key);

        // 시간대 컬럼의 첫 x좌표. 못 찾으면 현재 행의 우측 숫자 전체를 fallback으로 사용합니다.
        const firstHourLeft = hours.length ? Math.min(...hours.map(h=>h.left)) : Infinity;

        // 신규 UI에서 휴대폰번호 다음 숫자 순서:
        // 0 총 배달완료
        // 1~4 SLA 배달완료(푸드/비마트/스토어/합계)
        // 5~8 SLA 거절
        // 9~12 SLA 배차취소
        // 13~16 SLA 배달취소(라이더귀책)
        // 17~20 SLA 슬롯별 완료(오전/오후/저녁/심야)
        // 21 SLA 시간외 배달완료
        let metricCells = row
          .filter(x =>
            x.cx > phoneNode.cx + 8 &&
            x.right < firstHourLeft - 3 &&
            isIntText(x.text)
          )
          .sort((a,b)=>a.left-b.left);

        // 일부 브라우저에서 첫 시간 헤더가 아직 안 보이는 경우에는
        // 전화번호 뒤 숫자 중 신규 UI의 앞 22개 실적셀만 사용합니다.
        if (!Number.isFinite(firstHourLeft) || metricCells.length < 22) {
          metricCells = row
            .filter(x => x.cx > phoneNode.cx + 8 && isIntText(x.text))
            .sort((a,b)=>a.left-b.left)
            .slice(0,22);
        }

        const metricNums = metricCells.map(x=>toInt(x.text));

        let allDayComplete = metricNums[0] || 0;

        // 총 배달완료 헤더가 정상 렌더링된 경우 x좌표 값을 우선 검증값으로 사용합니다.
        if (allDayHeader) {
          const c = nearestCell(row, allDayHeader, x=>isIntText(x.text), 100);
          if (c) allDayComplete = toInt(c.text);
        }

        // 기존 수락률 정책을 보존: 푸드 SLA 실패건만 사용.
        const reject = metricNums[5] || 0;
        const cancel = metricNums[9] || 0;
        const riderFault = metricNums[13] || 0;

        // 배민 화면이 직접 제공하는 SLA 슬롯별 완료 4개.
        // 일부 DP에서 00~23시 시간대 컬럼이 가로 렌더링되지 않아도
        // 이 4개 값은 앞쪽 고정 실적영역에서 안정적으로 읽을 수 있습니다.
        const slotMorning = metricNums[17] || 0;
        const slotAfternoon = metricNums[18] || 0;
        const slotEvening = metricNums[19] || 0;
        const slotMidnight = metricNums[20] || 0;

        const hourly = Array(24).fill(0);
        if (hours.length >= 20) {
          for (const hh of hours) {
            let best = null;
            for (const cell of row) {
              if (!isIntText(cell.text)) continue;
              if (cell.cx <= phoneNode.cx) continue;
              const dx = Math.abs(cell.cx - hh.cx);
              if (dx > Math.max(28, hh.width * 1.8)) continue;
              const score = dx + Math.abs(cell.width-hh.width)*0.05;
              if (!best || score < best.score) best = {cell, score};
            }
            if (best) hourly[hh.hour] = toInt(best.cell.text);
          }
        } else {
          // 신규 UI 고정 순서 fallback: phone + 23부터 24개 시간대 값.
          const rightTexts = row.slice(phoneIdx+1).map(x=>x.text);
          const nums = rightTexts.filter(isIntText).map(toInt);
          const hourPart = nums.slice(22,46);
          for (let h=0; h<Math.min(24,hourPart.length); h++) hourly[h] = hourPart[h];
        }

        const hourlyTotal = hourly.reduce((a,b)=>a+b,0);

        // 총 배달완료가 화면에 존재하므로 이를 1순위로 사용하고,
        // 렌더링 누락 시 시간대 합계를 보조값으로 사용합니다.
        const complete = allDayComplete > 0 ? allDayComplete : hourlyTotal;

        out.push({
          name,
          phone,
          userId,
          status,
          complete,
          reject,
          cancel,
          riderFault,
          hourly,
          slotMorning,
          slotAfternoon,
          slotEvening,
          slotMidnight,
          allDayComplete,
          metricCount: metricNums.length,
          hourHeaderCount: hours.length,
          hourlyTotal,
          __raw:texts
        });
      }

      return out;
    }
    """)

def parse_row_lines(row_lines):
    """
    read_dom_rows의 정밀 파서가 시간헤더를 충분히 못 읽었을 때 사용하는 신규 UI fallback.
    신규 고정열 순서: 이름 → 운행상태 → 아이디 → 휴대폰번호.
    휴대폰 뒤 숫자: 총완료1 + SLA16 + 슬롯4 + 시간외1 + 시간대24.
    """
    lines = [norm(x) for x in row_lines if norm(x)]
    phone_idx = None

    for idx, line in enumerate(lines):
        if is_phone(line):
            phone_idx = idx
            break

    if phone_idx is None:
        return None

    phone = lines[phone_idx]

    # 운행상태
    status = "운행 종료"
    status_idx = None
    for idx, item in enumerate(lines[:phone_idx]):
        compact = item.replace(" ", "")
        if compact in ("운행중", "운행종료"):
            status_idx = idx
            status = "운행중" if compact == "운행중" else "운행 종료"
            break

    # 이름: 신규 구조에서는 운행상태 왼쪽이 이름 컬럼.
    name = ""
    name_candidates = lines[:status_idx] if status_idx is not None else lines[:phone_idx]
    for item in reversed(name_candidates):
        if not is_bad_name(item) and not is_phone(item):
            name = item
            break

    if not name or is_bad_name(name):
        return None

    # 아이디: 운행상태와 휴대폰번호 사이의 마지막 유효 텍스트.
    user_id = ""
    id_candidates = lines[(status_idx + 1 if status_idx is not None else 0):phone_idx]
    for item in reversed(id_candidates):
        if item != name and not is_bad_name(item) and not is_phone(item):
            user_id = item
            break

    # 휴대폰번호 뒤의 숫자만 뽑아 신규 UI 순서대로 해석.
    nums = []
    for item in lines[phone_idx + 1:]:
        s = str(item).replace(",", "").strip()
        if re.fullmatch(r"-?\d{1,7}", s):
            nums.append(to_int(s))

    # 신규 UI 앞 실적 22칸 + 시간대 24칸이 이상적입니다.
    if len(nums) < 22:
        return None

    all_day_complete = nums[0] if len(nums) > 0 else 0
    reject = nums[5] if len(nums) > 5 else 0
    cancel = nums[9] if len(nums) > 9 else 0
    rider_fault = nums[13] if len(nums) > 13 else 0

    hourly = [0] * 24
    hour_values = nums[22:46]
    for h, value in enumerate(hour_values[:24]):
        hourly[h] = value

    hourly_total = sum(hourly)
    complete = all_day_complete if all_day_complete > 0 else hourly_total

    sla = split_hourly_by_sla(hourly)

    # 배민 신규 UI의 앞 실적영역에는 SLA 슬롯별 완료가 이미 존재합니다.
    # 시간대 24칸이 렌더링되지 않아 합산값이 전부 0인 DP에서는
    # 슬롯별 완료 4개를 구간실적 fallback으로 사용합니다.
    slot_values = {
        "morning": nums[17] if len(nums) > 17 else 0,
        "afternoon": nums[18] if len(nums) > 18 else 0,
        "evening": nums[19] if len(nums) > 19 else 0,
        "midnight": nums[20] if len(nums) > 20 else 0,
    }
    slot_sum = sum(to_int(slot_values.get(p, 0)) for p in PERIODS)
    if (
        len(nums) >= 21
        and sum(to_int(sla.get(p, 0)) for p in PERIODS) == 0
        and slot_sum > 0
        and (complete <= 0 or slot_sum <= complete)
    ):
        for p in PERIODS:
            sla[p] = to_int(slot_values[p])

    is_online = status_online(status)

    return {
        "name": name,
        "phone": phone,
        "userId": user_id,
        "team": team_of(name, phone, user_id),
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

            slot_values = {
                "morning": to_int(group.get("slotMorning", 0)),
                "afternoon": to_int(group.get("slotAfternoon", 0)),
                "evening": to_int(group.get("slotEvening", 0)),
                "midnight": to_int(group.get("slotMidnight", 0)),
            }
            slot_sum = sum(slot_values.values())
            metric_count = to_int(group.get("metricCount", 0))

            complete = to_int(group.get("complete", 0))

            # 고정 인덱스 슬롯 fallback은 앞 실적 컬럼이 충분히 렌더링된 경우에만 사용합니다.
            # 또한 슬롯 합계가 총완료보다 큰 비정상 매칭은 절대 채택하지 않습니다.
            slot_fallback_valid = (
                metric_count >= 21
                and slot_sum > 0
                and (complete <= 0 or slot_sum <= complete)
            )
            if (
                sum(to_int(sla.get(p, 0)) for p in PERIODS) == 0
                and slot_fallback_valid
            ):
                for p in PERIODS:
                    sla[p] = slot_values[p]

            reject = to_int(group.get("reject", 0))
            cancel = to_int(group.get("cancel", 0))
            rider_fault = to_int(group.get("riderFault", 0))
            is_online = status_online(group.get("status", ""))
            rider = {
                "name": group.get("name", ""),
                "phone": group.get("phone", ""),
                "userId": group.get("userId", ""),
                "team": team_of(group.get("name", ""), group.get("phone", ""), group.get("userId", "")),
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



def rider_identity_keys(rider):
    """강한 기사 식별키. 이름만 같은 동명이인은 절대 합치지 않습니다."""
    rider = rider or {}
    keys = []
    phone = normalize_mobile_phone(rider.get("phone", ""))
    user_id = norm(rider.get("userId", "")).lower()
    user_phone = normalize_mobile_phone(user_id)
    if phone:
        keys.append(("identity", phone))
    if user_id:
        keys.append(("userId", user_id))
    if user_phone:
        keys.append(("identity", user_phone))
    return list(dict.fromkeys(keys))


def rider_partial_phone_fragments(rider):
    out = []
    for value in ((rider or {}).get("phone", ""), (rider or {}).get("userId", "")):
        frag = phone_like_fragment(value)
        if frag:
            out.append(frag)
    return list(dict.fromkeys(out))


def rider_valid_phones(rider):
    out = []
    for value in ((rider or {}).get("phone", ""), (rider or {}).get("userId", "")):
        phone = normalize_mobile_phone(value)
        if phone:
            out.append(phone)
    return list(dict.fromkeys(out))


def likely_same_rider_by_partial_phone(a, b):
    """같은 이름 + 정상번호와 잘린번호가 직접 이어질 때만 보조 병합합니다."""
    a, b = a or {}, b or {}
    if not norm(a.get("name", "")) or norm(a.get("name", "")) != norm(b.get("name", "")):
        return False
    av, bv = rider_valid_phones(a), rider_valid_phones(b)
    af, bf = rider_partial_phone_fragments(a), rider_partial_phone_fragments(b)
    if av and bv and set(av).isdisjoint(set(bv)):
        return False
    def matches(valids, frags):
        return any(full.startswith(frag) or full.endswith(frag) for full in valids for frag in frags)
    return matches(av, bf) or matches(bv, af)

def rider_quality_score(rider):
    """중복 카드 중 실적/신원 데이터가 더 온전한 행을 우선합니다."""
    rider = rider or {}
    hourly = rider.get("hourly") or []
    return (
        0 if rider.get("placeholder") else 1000000,
        to_int(rider.get("complete", 0)),
        to_int(rider.get("morning", 0)) + to_int(rider.get("afternoon", 0)) + to_int(rider.get("evening", 0)) + to_int(rider.get("midnight", 0)),
        sum(to_int(v) for v in hourly[:24]),
        1000 if rider.get("isOnline") else 0,
        100 if normalize_mobile_phone(rider.get("phone", "")) else 0,
        len(norm(rider.get("userId", ""))),
    )

def merge_duplicate_riders(a, b):
    """동일 기사로 판정된 두 행을 하나로 정리합니다."""
    a, b = dict(a or {}), dict(b or {})
    if rider_quality_score(b) > rider_quality_score(a):
        base, other = b, a
    else:
        base, other = a, b
    base = dict(base)
    if not normalize_mobile_phone(base.get("phone", "")) and normalize_mobile_phone(other.get("phone", "")):
        base["phone"] = other.get("phone")
    for key in ("name", "userId", "status", "team"):
        if not norm(base.get(key, "")) and norm(other.get(key, "")):
            base[key] = other.get(key)
    if not base.get("hourly") and other.get("hourly"):
        base["hourly"] = other.get("hourly")
    return base

def dedupe_riders(riders, log_prefix=""):
    """강한 키로 병합 후, 같은 이름+잘린번호가 1:1로 명확할 때만 보조 병합합니다."""
    result, key_to_index = [], {}
    duplicate_count = 0
    for rider in riders or []:
        if not isinstance(rider, dict):
            continue
        keys = rider_identity_keys(rider)
        matched = sorted({key_to_index[k] for k in keys if k in key_to_index})
        if not matched:
            idx = len(result)
            result.append(rider)
            for k in keys:
                key_to_index[k] = idx
            continue
        keep_idx = matched[0]
        result[keep_idx] = merge_duplicate_riders(result[keep_idx], rider)
        duplicate_count += 1
        for extra_idx in reversed(matched[1:]):
            result[keep_idx] = merge_duplicate_riders(result[keep_idx], result[extra_idx])
            result.pop(extra_idx)
        key_to_index = {}
        for i, row in enumerate(result):
            for k in rider_identity_keys(row):
                key_to_index[k] = i

    changed = True
    while changed:
        changed = False
        for i, row in enumerate(list(result)):
            if i >= len(result): break
            candidates = [j for j, other in enumerate(result) if j != i and likely_same_rider_by_partial_phone(row, other)]
            if len(candidates) != 1:
                continue
            j = candidates[0]
            keep, drop = min(i, j), max(i, j)
            result[keep] = merge_duplicate_riders(result[keep], result[drop])
            result.pop(drop)
            duplicate_count += 1
            changed = True
            break

    if duplicate_count:
        prefix = f"{log_prefix} " if log_prefix else ""
        debug_log(f"{prefix}중복 기사 {duplicate_count}건 제거 완료")
    return result

# ===== TNT EMERGENCY RESTORE BASELINE 2026-09 =====
def ensure_required_rider_cards(riders):
    # 실제 배민비즈 수집에 없는 과거 명단 기사카드는 강제로 만들지 않습니다.
    # 실제 수집된 기사 row는 전화번호 표기 형식과 무관하게 모두 유지합니다.
    return list(riders or [])

def _wait_history_rows(page, timeout_seconds=HISTORY_RENDER_TIMEOUT):
    """기사 신원 + 실적 컬럼이 함께 안정된 뒤 수집합니다.

    예전 방식은 기사 수/첫기사/끝기사만 같으면 약 0.35초 뒤 바로 진행했습니다.
    배민 표는 신원 컬럼이 먼저 뜨고 실적 컬럼이 나중에 렌더링될 수 있어
    기사카드는 정상인데 실적이 0/오독되는 문제가 생길 수 있습니다.
    """
    started = time.monotonic()
    deadline = started + timeout_seconds
    last_signature = None
    stable_hits = 0
    last_rows = []

    while time.monotonic() < deadline:
        try:
            rows = read_dom_rows(page)
        except Exception:
            rows = []

        last_rows = rows or last_rows
        elapsed = time.monotonic() - started

        if rows:
            usable = [r for r in rows if not (isinstance(r, dict) and r.get("__debugSkip"))]
            if usable:
                def ident(row):
                    return (
                        normalize_phone(row.get("phone", ""))
                        or norm(row.get("userId", ""))
                        or norm(row.get("name", ""))
                    )

                total_complete = sum(to_int(r.get("complete", 0)) for r in usable if isinstance(r, dict))
                total_hourly = sum(to_int(r.get("hourlyTotal", 0)) for r in usable if isinstance(r, dict))
                total_slots = sum(
                    to_int(r.get("slotMorning", 0))
                    + to_int(r.get("slotAfternoon", 0))
                    + to_int(r.get("slotEvening", 0))
                    + to_int(r.get("slotMidnight", 0))
                    for r in usable if isinstance(r, dict)
                )
                metric_counts = [
                    to_int(r.get("metricCount", 0))
                    for r in usable if isinstance(r, dict)
                ]
                min_metric_count = min(metric_counts) if metric_counts else 0
                hour_header_count = max(
                    [to_int(r.get("hourHeaderCount", 0)) for r in usable if isinstance(r, dict)] or [0]
                )

                # complete가 있는데 시간대/슬롯 소스가 둘 다 없는 행은 아직 부분 렌더링으로 봅니다.
                partial_metric_rows = sum(
                    1
                    for r in usable
                    if isinstance(r, dict)
                    and to_int(r.get("complete", 0)) > 0
                    and to_int(r.get("hourlyTotal", 0)) == 0
                    and (
                        to_int(r.get("slotMorning", 0))
                        + to_int(r.get("slotAfternoon", 0))
                        + to_int(r.get("slotEvening", 0))
                        + to_int(r.get("slotMidnight", 0))
                    ) == 0
                )

                signature = (
                    len(usable),
                    ident(usable[0]),
                    ident(usable[-1]),
                    total_complete,
                    total_hourly,
                    total_slots,
                    min_metric_count,
                    hour_header_count,
                    partial_metric_rows,
                )

                if signature == last_signature:
                    stable_hits += 1
                else:
                    last_signature = signature
                    stable_hits = 0

                # 실적까지 3회 연속 동일 + 최소 1초 렌더 유예.
                # 실적이 있는 기사 중 부분 렌더 행이 남아 있으면 timeout까지 기다립니다.
                if elapsed >= 1.0 and stable_hits >= 2 and partial_metric_rows == 0:
                    return rows

        elif elapsed >= 1.2:
            return []

        time.sleep(0.18)

    # timeout 시 마지막 상태를 반환하되, 이후 품질 게이트에서 이상 수집은 업로드 차단합니다.
    if last_rows:
        return last_rows
    try:
        return read_dom_rows(page)
    except Exception:
        return []


def _history_page_matches(page, page_no):
    try:
        u = urlparse(page.url)
        q = parse_qs(u.query)
        return (
            "/delivery/history" in u.path
            and q.get("page", [""])[0] == str(page_no)
            and q.get("size", [""])[0] == "100"
        )
    except Exception:
        return False



# ===== TNT BAEMIN DELIVERY-STATUS API DIRECT V3 2026-09 =====

def history_url_for_page(page_no=0):
    return (
        "https://deliverycenter.baemin.com/delivery/history"
        f"?page={int(page_no)}&size={BAEMIN_HISTORY_PAGE_SIZE}&orderName=name&orderBy=asc"
        "&name=&userId=&phoneNumber=&riderStatus="
    )


def _is_delivery_status_response(response):
    """배달현황 화면이 실제로 사용하는 delivery-status XHR/fetch 응답만 잡습니다."""
    try:
        if response.status != 200:
            return False
        if "delivery-status" not in (response.url or "").lower():
            return False
        resource_type = (response.request.resource_type or "").lower()
        return resource_type in ("xhr", "fetch")
    except Exception:
        return False


def _load_delivery_status_page(page, page_no):
    """지정 페이지를 열고 그 화면이 실제 수신한 delivery-status JSON을 반환합니다."""
    url = history_url_for_page(page_no)
    try:
        with page.expect_response(
            _is_delivery_status_response,
            timeout=BAEMIN_API_RESPONSE_TIMEOUT_MS,
        ) as response_info:
            page.goto(url, wait_until="domcontentloaded")

        response = response_info.value
        payload = response.json()
    except Exception as exc:
        raise RuntimeError(f"배민 delivery-status API 수신 실패: {page_no + 1}페이지 · {exc}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"배민 delivery-status 응답 형식 오류: {page_no + 1}페이지")
    if not isinstance(payload.get("data"), list):
        raise RuntimeError(f"배민 delivery-status data 누락: {page_no + 1}페이지")

    actual_page = to_int(payload.get("page", page_no))
    if actual_page != page_no:
        raise RuntimeError(
            f"배민 delivery-status 페이지 불일치: 요청 {page_no}, 응답 {actual_page}"
        )

    return payload, response.url


def _api_hourly_to_clock24(hourly_completed):
    """
    배민 신규 API는 영업 흐름을 hour=6..32 형태로 내려줄 수 있습니다.
    24~32는 다음날 00~08시이므로 hour % 24로 합쳐 TNT의 00~23 배열로 정규화합니다.

    이 방식이면:
      hourly[0:9]  = 00~08 미포함
      hourly[9:24] = 09~23 포함실적
    이 되고, 6~8시 및 다음날 00~08시가 모두 정확히 미포함에 들어갑니다.
    """
    hourly = [0] * 24
    raw_total = 0

    for item in hourly_completed or []:
        if not isinstance(item, dict):
            continue
        raw_hour = to_int(item.get("hour", -1))
        count = to_int(item.get("count", 0))
        if raw_hour < 0 or raw_hour > 48:
            raise RuntimeError(f"배민 시간대 hour 값 오류: {raw_hour}")
        if count < 0:
            raise RuntimeError(f"배민 시간대 count 값 오류: {count}")
        hourly[raw_hour % 24] += count
        raw_total += count

    return hourly, raw_total


def _api_required_int(obj, key, rider_name):
    if key not in obj:
        raise RuntimeError(f"배민 API 필드 누락: {rider_name} · {key}")
    return to_int(obj.get(key, 0))


def rider_from_delivery_status_api(row):
    """delivery-status의 기사 1명을 TNT 기존 기사카드 스키마로 변환합니다."""
    if not isinstance(row, dict):
        raise RuntimeError("배민 API 기사행 형식 오류")

    name = norm(row.get("name", ""))
    phone = norm(row.get("phoneNumber", ""))
    user_id = norm(row.get("userId", ""))

    if not name or is_bad_name(name):
        raise RuntimeError(f"배민 API 기사 이름 오류: {name!r}")

    # ===== TNT API INVALID PHONE FALLBACK V3 2026-09 =====
    # 배민 원본에서 일부 기사 전화번호 자체가 비정상 값(예: 999-....)으로 내려올 수 있습니다.
    # 이 경우 기사실적 전체 DP를 차단하지 않고, 배민 userId를 안정 식별자로 사용합니다.
    # phone 원문은 화면/원본 확인용으로 그대로 보존하고 canonical_rider_key/teamMap은
    # 기존 로직대로 정상 010번호가 아니면 자동으로 uid_ 키를 사용합니다.
    valid_phone = normalize_mobile_phone(phone)
    if not valid_phone:
        if not user_id:
            raise RuntimeError(
                f"배민 API 기사 식별자 오류: {name} · 비정상 휴대폰 {phone!r} · userId 없음"
            )
        debug_log(
            f"[배민 API] 비정상 휴대폰 원본 유지 · {name} · {phone!r} · uid={user_id}"
        )

    status_obj = row.get("status") or {}
    status_desc = norm(status_obj.get("desc", ""))
    is_online = status_desc.replace(" ", "") == "운행중"

    acc = row.get("deliveryAcceptanceCount")
    peak = row.get("deliveryPeakTimeCount")
    hourly_completed = row.get("hourlyCompleted")

    if not isinstance(acc, dict):
        raise RuntimeError(f"배민 API deliveryAcceptanceCount 누락: {name}")
    if not isinstance(peak, dict):
        raise RuntimeError(f"배민 API deliveryPeakTimeCount 누락: {name}")
    if not isinstance(hourly_completed, list):
        raise RuntimeError(f"배민 API hourlyCompleted 누락: {name}")

    # 현재 배민 신규 API의 원본 필드. 추정/보정하지 않습니다.
    included_complete = _api_required_int(acc, "totalComplete", name)
    all_day_complete = _api_required_int(acc, "allDayComplete", name)
    sla_out_complete = _api_required_int(acc, "slaOutComplete", name)

    morning = _api_required_int(peak, "morning", name)
    afternoon = _api_required_int(peak, "afternoon", name)
    evening = _api_required_int(peak, "evening", name)
    midnight = _api_required_int(peak, "midnight", name)

    hourly, raw_hourly_total = _api_hourly_to_clock24(hourly_completed)
    hourly_excluded = sum(hourly[0:9])
    hourly_included = sum(hourly[9:24])

    # 사용자 기준과 배민 원본이 한 기사 단위에서 모두 일치해야만 저장합니다.
    if all_day_complete != included_complete + sla_out_complete:
        raise RuntimeError(
            f"배민 API 완료합 불일치: {name} · 전체 {all_day_complete} "
            f"!= 포함 {included_complete} + 미포함 {sla_out_complete}"
        )
    if morning + afternoon + evening + midnight != included_complete:
        raise RuntimeError(
            f"배민 API 구간합 불일치: {name} · 구간합 "
            f"{morning + afternoon + evening + midnight} != 포함 {included_complete}"
        )
    if raw_hourly_total != all_day_complete:
        raise RuntimeError(
            f"배민 API 시간대합 불일치: {name} · 시간대합 {raw_hourly_total} "
            f"!= 전체 {all_day_complete}"
        )
    if hourly_excluded != sla_out_complete:
        raise RuntimeError(
            f"배민 API 미포함 불일치: {name} · 00~08합 {hourly_excluded} "
            f"!= 미포함 {sla_out_complete}"
        )
    if hourly_included != included_complete:
        raise RuntimeError(
            f"배민 API 포함실적 불일치: {name} · 09~23합 {hourly_included} "
            f"!= 포함 {included_complete}"
        )

    # 기존 TNT 수락률 정책은 그대로 유지: 푸드 SLA 실패건을 사용합니다.
    reject = to_int(acc.get("foodReject", acc.get("totalReject", 0)))
    cancel = to_int(acc.get("foodCancel", acc.get("totalCancel", 0)))
    rider_fault = to_int(acc.get("foodRiderFault", acc.get("totalRiderFault", 0)))

    morning_excluded = sum(hourly[6:9])
    midnight_excluded = sum(hourly[0:6])
    accept_rate = calc_accept_rate(all_day_complete, reject, cancel, rider_fault)

    return {
        "name": name,
        "phone": phone,
        "userId": user_id,
        "team": team_of(name, phone, user_id),
        "status": "운행중" if is_online else "운행 종료",
        "isOnline": is_online,
        "complete": all_day_complete,
        "reject": reject,
        "cancel": cancel,
        "riderFault": rider_fault,
        "morning": morning,
        "afternoon": afternoon,
        "evening": evening,
        "midnight": midnight,
        "morningExcluded": morning_excluded,
        "midnightExcluded": midnight_excluded,
        "excluded": sla_out_complete,
        "hourly": hourly,
        "acceptRate": accept_rate,
        "warning": accept_rate < TARGET_ACCEPT_RATE,
    }


def _api_total_signature(payload):
    total = payload.get("deliveryStatusTotalResponse") or {}
    return (
        to_int(payload.get("total", 0)),
        to_int(payload.get("totalPage", 0)),
        to_int(total.get("totalCount", 0)),
        to_int(total.get("allDayComplete", 0)),
        to_int(total.get("totalCompleted", 0)),
        to_int(total.get("slaOutComplete", 0)),
        to_int(total.get("totalFoodRejected", 0)),
        to_int(total.get("totalFoodCanceled", 0)),
        to_int(total.get("totalFoodRiderFault", 0)),
    )


def _page_api_totals(payload):
    """
    deliveryStatusTotalResponse는 여러 페이지 DP에서 '해당 페이지 subtotal'로 내려옵니다.
    페이지별 원본 rows 합과 subtotal을 먼저 1:1 검증합니다.
    """
    aggregate = payload.get("deliveryStatusTotalResponse") or {}
    rows = payload.get("data") or []

    if not isinstance(aggregate, dict):
        raise RuntimeError("배민 API 페이지합계 응답 누락")
    if not isinstance(rows, list):
        raise RuntimeError("배민 API 페이지 기사목록 누락")

    row_all = 0
    row_included = 0
    row_excluded = 0
    row_reject = 0
    row_cancel = 0
    row_fault = 0

    for row in rows:
        acc = (row or {}).get("deliveryAcceptanceCount") or {}
        row_all += to_int(acc.get("allDayComplete", 0))
        row_included += to_int(acc.get("totalComplete", 0))
        row_excluded += to_int(acc.get("slaOutComplete", 0))
        row_reject += to_int(acc.get("foodReject", acc.get("totalReject", 0)))
        row_cancel += to_int(acc.get("foodCancel", acc.get("totalCancel", 0)))
        row_fault += to_int(acc.get("foodRiderFault", acc.get("totalRiderFault", 0)))

    expected_all = _api_required_int(aggregate, "allDayComplete", "페이지합계")
    expected_included = _api_required_int(aggregate, "totalCompleted", "페이지합계")
    expected_excluded = _api_required_int(aggregate, "slaOutComplete", "페이지합계")
    expected_reject = to_int(aggregate.get("totalFoodRejected", 0))
    expected_cancel = to_int(aggregate.get("totalFoodCanceled", 0))
    expected_fault = to_int(aggregate.get("totalFoodRiderFault", 0))

    if row_all != expected_all:
        raise RuntimeError(
            f"배민 API 페이지 전체완료 불일치: 기사합 {row_all} != 페이지합 {expected_all}"
        )
    if row_included != expected_included:
        raise RuntimeError(
            f"배민 API 페이지 포함실적 불일치: 기사합 {row_included} != 페이지합 {expected_included}"
        )
    if row_excluded != expected_excluded:
        raise RuntimeError(
            f"배민 API 페이지 미포함 불일치: 기사합 {row_excluded} != 페이지합 {expected_excluded}"
        )
    if row_reject != expected_reject:
        raise RuntimeError(
            f"배민 API 페이지 푸드거절 불일치: 기사합 {row_reject} != 페이지합 {expected_reject}"
        )
    if row_cancel != expected_cancel:
        raise RuntimeError(
            f"배민 API 페이지 푸드취소 불일치: 기사합 {row_cancel} != 페이지합 {expected_cancel}"
        )
    if row_fault != expected_fault:
        raise RuntimeError(
            f"배민 API 페이지 라이더귀책 불일치: 기사합 {row_fault} != 페이지합 {expected_fault}"
        )

    if expected_all != expected_included + expected_excluded:
        raise RuntimeError(
            f"배민 API 페이지 산식 불일치: {expected_all} != "
            f"{expected_included} + {expected_excluded}"
        )

    return {
        "rowCount": len(rows),
        "allDayComplete": expected_all,
        "includedComplete": expected_included,
        "excludedComplete": expected_excluded,
        "reject": expected_reject,
        "cancel": expected_cancel,
        "fault": expected_fault,
    }


def _validate_api_totals(riders, page_payloads):
    """
    전체 기사합을 검증합니다.

    중요:
    - payload["total"] / totalPage 는 센터 전체 pagination 정보입니다.
    - deliveryStatusTotalResponse 는 다중 페이지 DP에서 각 페이지 subtotal입니다.
    따라서 첫 페이지 subtotal을 센터 전체합으로 비교하면 안 됩니다.
    """
    if not page_payloads:
        raise RuntimeError("배민 API 페이지 응답 없음")

    first_payload = page_payloads[0]
    expected_count = to_int(first_payload.get("total", 0))
    total_pages = max(1, to_int(first_payload.get("totalPage", 1)))

    if total_pages != len(page_payloads):
        raise RuntimeError(
            f"배민 API 페이지 수 불일치: 응답 {len(page_payloads)} != totalPage {total_pages}"
        )

    page_summaries = [_page_api_totals(p) for p in page_payloads]

    subtotal_count = sum(x["rowCount"] for x in page_summaries)
    subtotal_all = sum(x["allDayComplete"] for x in page_summaries)
    subtotal_included = sum(x["includedComplete"] for x in page_summaries)
    subtotal_excluded = sum(x["excludedComplete"] for x in page_summaries)
    subtotal_reject = sum(x["reject"] for x in page_summaries)
    subtotal_cancel = sum(x["cancel"] for x in page_summaries)
    subtotal_fault = sum(x["fault"] for x in page_summaries)

    actual_all = sum(to_int(r.get("complete", 0)) for r in riders)
    actual_period = sum(
        to_int(r.get("morning", 0))
        + to_int(r.get("afternoon", 0))
        + to_int(r.get("evening", 0))
        + to_int(r.get("midnight", 0))
        for r in riders
    )
    actual_excluded = sum(to_int(r.get("excluded", 0)) for r in riders)
    actual_reject = sum(to_int(r.get("reject", 0)) for r in riders)
    actual_cancel = sum(to_int(r.get("cancel", 0)) for r in riders)
    actual_fault = sum(to_int(r.get("riderFault", 0)) for r in riders)

    if subtotal_count != expected_count:
        raise RuntimeError(
            f"배민 API 기사수 불일치: 페이지합 {subtotal_count} != 전체 {expected_count}"
        )
    if len(riders) != expected_count:
        raise RuntimeError(
            f"배민 API 기사중복/누락: 정리후 {len(riders)} != 전체 {expected_count}"
        )

    checks = [
        ("전체완료", actual_all, subtotal_all),
        ("포함실적", actual_period, subtotal_included),
        ("미포함", actual_excluded, subtotal_excluded),
        ("푸드거절", actual_reject, subtotal_reject),
        ("푸드취소", actual_cancel, subtotal_cancel),
        ("라이더귀책", actual_fault, subtotal_fault),
    ]
    for label, actual, expected in checks:
        if actual != expected:
            raise RuntimeError(
                f"배민 API {label} 불일치: 기사합 {actual} != 페이지합계 {expected}"
            )

    if subtotal_all != subtotal_included + subtotal_excluded:
        raise RuntimeError(
            f"배민 API 전체 산식 불일치: {subtotal_all} != "
            f"{subtotal_included} + {subtotal_excluded}"
        )

    return {
        "totalCount": expected_count,
        "allDayComplete": subtotal_all,
        "includedComplete": subtotal_included,
        "excludedComplete": subtotal_excluded,
        "totalPages": total_pages,
    }



def collect_all_pages_by_api(page):
    """
    배민비즈 화면이 실제 호출하는 delivery-status XHR을 직접 수신합니다.
    DOM 셀 순서/x좌표/가상스크롤은 기사실적에 전혀 사용하지 않습니다.
    """
    last_error = None

    for attempt in range(1, BAEMIN_API_STABLE_RETRY + 1):
        try:
            first_payload, first_api_url = _load_delivery_status_page(page, 0)
            total_pages = max(1, to_int(first_payload.get("totalPage", 1)))
            if total_pages > MAX_PAGES:
                raise RuntimeError(f"배민 API 페이지 수 초과: {total_pages}")

            page_payloads = [first_payload]
            for page_no in range(1, total_pages):
                payload, _ = _load_delivery_status_page(page, page_no)
                page_payloads.append(payload)

            # 여러 페이지인 DP는 수집 도중 실적이 바뀌지 않았는지 page 0을 한 번 더 확인합니다.
            if total_pages > 1:
                confirm_payload, _ = _load_delivery_status_page(page, 0)
                if _api_total_signature(confirm_payload) != _api_total_signature(first_payload):
                    raise RuntimeError("수집 중 배민 실적이 변경됨 · 전체 페이지 재수집")

            riders = []
            for payload in page_payloads:
                for row in payload.get("data") or []:
                    riders.append(rider_from_delivery_status_api(row))

            riders = dedupe_riders(riders, "배민 API")
            api_meta = _validate_api_totals(riders, page_payloads)

            riders = ensure_required_rider_cards(riders)
            riders = dedupe_riders(riders, "카드 보강 후")
            riders = finalize_rider_identity_and_teams(riders)

            api_meta["apiUrl"] = first_api_url
            api_meta["source"] = "baemin_delivery_status_api"
            return riders, api_meta

        except Exception as exc:
            last_error = exc
            if attempt < BAEMIN_API_STABLE_RETRY:
                debug_log(f"배민 API 재수집 {attempt}/{BAEMIN_API_STABLE_RETRY}: {exc}")
                time.sleep(0.35)
                continue
            break

    raise RuntimeError(f"배민 API 원본수집 실패: {last_error}")


def collect_all_pages_by_dom(page):
    base_url = page.url
    all_riders = []

    for page_no in range(MAX_PAGES):
        target_url = set_page_number(base_url, page_no)
        debug_log(f"{page_no + 1}페이지 이동: {target_url}")

        # change_center가 이미 첫 history 페이지를 열어둔 경우 중복 navigation을 생략합니다.
        if not _history_page_matches(page, page_no):
            page.goto(target_url, wait_until="domcontentloaded")

        if "size=100" not in page.url:
            fixed_url = set_page_number(page.url, page_no)
            debug_log("100개 보기 강제 적용:", fixed_url)
            page.goto(fixed_url, wait_until="domcontentloaded")

        row_groups = _wait_history_rows(page)
        riders = parse_dom_rows(row_groups)

        debug_log(f"{page_no + 1}페이지 DOM 행 수: {len(row_groups)}")
        debug_skips = [g for g in row_groups if isinstance(g, dict) and g.get('__debugSkip')]
        if debug_skips:
            debug_log(f"{page_no + 1}페이지 스킵 후보 행 수: {len(debug_skips)}")
            for ds in debug_skips[:10]:
                debug_log('스킵행:', ds.get('reason'), ds.get('name', ''), ds.get('phone', ''), ds.get('raw', [])[:12])
        debug_log(f"{page_no + 1}페이지 읽은 기사 수: {len(riders)}")
        if riders:
            debug_log(f"{page_no + 1}페이지 첫/끝 기사: {riders[0]['name']} / {riders[-1]['name']}")

        if page_no == 0 and len(riders) == 0:
            debug_log("DOM 샘플:")
            for idx, row in enumerate(row_groups[:3]):
                debug_log(idx, row[:20])

        if len(riders) == 0:
            debug_log("빈 페이지라서 수집 종료")
            break

        before_count = len(all_riders)
        all_riders.extend(riders)
        all_riders = dedupe_riders(all_riders, f"{page_no + 1}페이지")
        new_count = len(all_riders) - before_count

        debug_log(f"{page_no + 1}페이지 신규 고유 기사 수: {new_count}")

        if new_count == 0:
            debug_log("새 고유 기사 없음. 마지막 페이지로 판단하고 종료")
            break

    all_riders = dedupe_riders(all_riders, "최종 수집")
    all_riders = ensure_required_rider_cards(all_riders)
    all_riders = dedupe_riders(all_riders, "카드 보강 후")
    all_riders = finalize_rider_identity_and_teams(all_riders)
    debug_log(f"전체 카드 기사 수: {len(all_riders)}")
    phones = [normalize_phone(r.get("phone", "")) for r in all_riders if r.get("phone")]
    if len(phones) != len(set(phones)):
        debug_log("중복 휴대폰 감지:", [p for p in sorted(set(phones)) if phones.count(p) > 1])
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
    target_weekday = schedule_weekday(bd)
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
        print("[경고] weekly 파일 손상 - 새로 생성")
    return []


def week_start_wednesday(date_value):
    """수요일~화요일 주차 기준의 시작일을 반환합니다."""
    days_since_wed = (date_value.weekday() - 2) % 7
    return date_value - timedelta(days=days_since_wed)


def current_week_dates(now):
    start = week_start_wednesday(business_date(now))
    return [start + timedelta(days=i) for i in range(7)]


def target_total_by_period_for_date(date_value):
    target_weekday = schedule_weekday(date_value)
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


def save_weekly_snapshot(data, config=None):
    """01시 확정 시점에 해당 businessDate의 주간 기록을 1회 저장합니다.

    business_date()는 06시 전까지 전날을 가리키므로 01시 저장은 전날 확정 기록이 됩니다.
    같은 날짜가 이미 있으면 01시 확정값으로 덮어씁니다.
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
    riders = dedupe_riders(riders, "Firebase 업로드 직전")
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
        "areas": ["달서A", "달서B", "중구A"],
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




def append_collector_error(config, *, duration_seconds=0.0, cycle_no=0, error=""):
    """Collector 오류를 DP별 최근 이력으로 저장합니다. 개인정보/기사 데이터는 저장하지 않습니다."""
    slug = config.get("slug", "")
    if not slug:
        return
    now = datetime.now().astimezone()
    event_id = now.strftime("%Y%m%dT%H%M%S%f")
    payload = {
        "eventId": event_id,
        "collectorId": COLLECTOR_ID,
        "area": config.get("area", slug),
        "slug": slug,
        "centerCode": config.get("center_code", ""),
        "occurredAt": now.isoformat(timespec="seconds"),
        "durationMs": int(max(0.0, duration_seconds) * 1000),
        "cycleNo": int(cycle_no or 0),
        "error": str(error or "")[:500],
    }
    try:
        init_firebase()
        ref = db.reference(f"{COLLECTOR_ERROR_ROOT}/{COLLECTOR_ID}/{slug}")
        ref.child(event_id).set(payload)
        # 무한 증가 방지: DP별 최근 COLLECTOR_ERROR_KEEP개만 유지
        raw = ref.get() or {}
        if isinstance(raw, dict) and len(raw) > COLLECTOR_ERROR_KEEP:
            for old_key in sorted(raw.keys())[:-COLLECTOR_ERROR_KEEP]:
                ref.child(old_key).delete()
    except Exception as exc:
        print(f"[경고] {config.get('area', slug)} 오류이력 기록 실패: {exc}")


def update_collector_status(config, *, state, duration_seconds=0.0, cycle_no=0, error=""):
    """DP별 Collector 상태를 Firebase의 작은 상태 전용 경로에 기록합니다."""
    now_text = datetime.now().astimezone().isoformat(timespec="seconds")
    slug = config.get("slug", "")
    if not slug:
        return
    payload = {
        "collectorId": COLLECTOR_ID,
        "area": config.get("area", slug),
        "slug": slug,
        "centerCode": config.get("center_code", ""),
        "lastAttemptAt": now_text,
        "lastAttemptState": state,
        "lastDurationMs": int(max(0.0, duration_seconds) * 1000),
        "cycleNo": int(cycle_no or 0),
        "error": str(error or "")[:500],
        "targetCycleSeconds": CYCLE_TARGET_SECONDS,
    }
    if state == "OK":
        payload["lastSuccessAt"] = now_text
        payload["error"] = ""
    try:
        init_firebase()
        db.reference(f"{COLLECTOR_STATUS_ROOT}/{COLLECTOR_ID}/{slug}").update(payload)
    except Exception as exc:
        # 상태 기록 실패가 실제 수집을 중단시키면 안 됩니다.
        print(f"[경고] {config.get('area', slug)} 상태 기록 실패: {exc}")


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
        # 실시간 경로에는 주간 이력 덩어리를 절대 포함하지 않습니다.
        # /live 는 기존 관제판 호환용, /live-lite 는 신규 저트래픽 관제판용입니다.
        lite_data = dict(data)
        lite_data.pop("weekly", None)
        lite_data.pop("availableWeeks", None)
        lite_data.pop("weeklySummary", None)
        uploaded_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lite_data.setdefault("collectorMeta", {})["uploadedAt"] = uploaded_at
        payload_bytes = len(json.dumps(lite_data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        lite_data["collectorMeta"]["payloadBytes"] = payload_bytes
        init_firebase()
        db.reference(config["live_path"]).set(lite_data)
        lite_path = f"/live-lite/{config['slug']}"
        db.reference(lite_path).set(lite_data)

        debug_log(f"Firebase 실시간 경량 업로드 완료: {config['live_path']}")
        debug_log(f"Firebase 실시간 경량 업로드 완료: {lite_path}")
        debug_log(f"LIVE payload: {payload_bytes:,} bytes ({payload_bytes/1024:.1f} KB)")
    except Exception as e:
        print("[오류] Firebase 업로드 실패")
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
        debug_log("커밋할 변경사항 없음")
        return

    push = subprocess.run(
        ["git", "push"],
        cwd=BASE_DIR,
        capture_output=True,
        text=True
    )

    debug_log(push.stdout)
    debug_log(push.stderr)



def is_excluded_rider(rider):
    """탈퇴 지사 기사는 전화번호/userId가 일치할 때만 제외합니다."""
    for key in rider_team_keys(rider.get("name", ""), rider.get("phone", ""), rider.get("userId", ""), include_name=False):
        if key in EXCLUDED_IDENTITY_KEYS:
            return True
    return False



def validate_collection_quality(riders, data, config):
    """부분 렌더/오독 데이터가 Firebase의 정상 데이터를 덮어쓰지 않도록 차단합니다."""
    if not riders:
        raise RuntimeError("수집 품질검사 실패: 기사 0명")

    performance_rows = [r for r in riders if to_int(r.get("complete", 0)) > 0]
    missing_period_rows = []
    impossible_rows = []

    for r in performance_rows:
        period_sum = sum(to_int(r.get(p, 0)) for p in PERIODS)
        excluded = to_int(r.get("excluded", 0))
        complete = to_int(r.get("complete", 0))

        if period_sum + excluded == 0:
            missing_period_rows.append(r)

        # 구간+미포함 합계가 총완료를 넘으면 컬럼 오독 가능성이 큽니다.
        if period_sum + excluded > complete + 2:
            impossible_rows.append(r)

    # 실적 있는 기사 중 15% 이상이 구간값 0이면 부분 렌더로 간주.
    if performance_rows:
        missing_limit = max(3, int(len(performance_rows) * 0.15))
        if len(missing_period_rows) > missing_limit:
            names = ", ".join(norm(r.get("name", "")) for r in missing_period_rows[:8])
            raise RuntimeError(
                f"수집 품질검사 실패: 실적은 있으나 구간값이 없는 기사 "
                f"{len(missing_period_rows)}/{len(performance_rows)}명 · {names}"
            )

    if len(impossible_rows) > 2:
        names = ", ".join(norm(r.get("name", "")) for r in impossible_rows[:8])
        raise RuntimeError(
            f"수집 품질검사 실패: 구간합계가 총완료보다 큰 기사 {len(impossible_rows)}명 · {names}"
        )

    total = data.get("total") or {}
    total_complete = to_int(total.get("complete", 0))
    total_periods = sum(to_int(total.get(p, 0)) for p in PERIODS)
    total_excluded = to_int(total.get("excluded", 0))

    if total_periods + total_excluded > total_complete + max(5, int(total_complete * 0.05)):
        raise RuntimeError(
            f"수집 품질검사 실패: 전체 구간합 {total_periods}+미포함 {total_excluded} "
            f"> 전체완료 {total_complete}"
        )

    # 이전 정상 로컬 데이터와 같은 영업일이면 급격한 하락을 차단합니다.
    previous_path = BASE_DIR / f"data_{config['slug']}.json"
    if previous_path.exists():
        try:
            previous = json.loads(previous_path.read_text(encoding="utf-8"))
            if previous.get("businessDate") == data.get("businessDate"):
                prev_total = previous.get("total") or {}
                prev_count = to_int(prev_total.get("count", 0))
                prev_complete = to_int(prev_total.get("complete", 0))
                new_count = to_int(total.get("count", 0))

                if prev_count >= 20 and new_count < int(prev_count * 0.55):
                    raise RuntimeError(
                        f"수집 품질검사 실패: 기사 수 급감 {prev_count}명 → {new_count}명"
                    )
                if prev_complete >= 20 and total_complete < int(prev_complete * 0.50):
                    raise RuntimeError(
                        f"수집 품질검사 실패: 당일 완료 급감 {prev_complete} → {total_complete}"
                    )
        except RuntimeError:
            raise
        except Exception as exc:
            debug_log(f"이전 데이터 품질 비교 생략: {exc}")

    debug_log(
        f"[수집품질 OK] {config['area']} · 기사 {len(riders)}명 · "
        f"실적기사 {len(performance_rows)}명 · 완료 {total_complete} · "
        f"구간합 {total_periods} · 미포함 {total_excluded}"
    )


def run_update(page, config=None):
    global VERIFIED_CENTER_CODE
    update_started_mono = time.monotonic()
    collected_at = datetime.now()
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

    riders, api_meta = collect_all_pages_by_api(page)
    if EXCLUDED_IDENTITY_KEYS:
        before_count = len(riders)
        riders = [r for r in riders if not is_excluded_rider(r)]
        removed = before_count - len(riders)
        if removed:
            debug_log(f"{AREA_NAME} 탈퇴 지사 기사 제외: {removed}명")
    if len(riders) == 0:
        raise RuntimeError("기사 데이터를 못 읽었습니다.")

    data = make_data(riders, config)
    validate_collection_quality(riders, data, config)
    collection_duration_ms = int((time.monotonic() - update_started_mono) * 1000)
    data["collectorMeta"] = {
        "collectorId": COLLECTOR_ID,
        "centerCode": config.get("center_code", ""),
        "collectedAt": collected_at.strftime("%Y-%m-%d %H:%M:%S"),
        "collectionDurationMs": collection_duration_ms,
        "targetCycleSeconds": CYCLE_TARGET_SECONDS,
        "source": api_meta.get("source", "baemin_delivery_status_api"),
        "apiPages": api_meta.get("totalPages", 0),
        "apiTotalCount": api_meta.get("totalCount", 0),
    }

    # 수집 직후부터 권역값을 검증하여 다른 권역 덮어쓰기를 차단합니다.
    if data.get("area") != config["area"] or data.get("slug") != config["slug"]:
        raise RuntimeError(
            f"수집 권역 불일치: {data.get('area')}/{data.get('slug')} "
            f"!= {config['area']}/{config['slug']}"
        )

    # 주간 기록은 매일 01시대에 권역별 1회만 확정 저장/업로드합니다.
    # 01시는 business_date()상 전날이므로 전날 최종 기록이 저장됩니다.
    now_for_weekly = datetime.now()
    weekly_business_date = str(business_date(now_for_weekly))
    slug = config["slug"]
    if now_for_weekly.hour == WEEKLY_SNAPSHOT_HOUR and WEEKLY_SAVED_BUSINESS_DATES.get(slug) != weekly_business_date:
        save_weekly_snapshot(data, config)
        upload_json(WEEKLY_FILE.name, config["weekly_path"])
        WEEKLY_SAVED_BUSINESS_DATES[slug] = weekly_business_date
        print(f"주간 확정 저장 완료: {config['weekly_path']} / {weekly_business_date}")

    # 로컬 data 파일 호환 필드는 유지하되 Firebase 실시간 payload에서는 save_json()이 제거합니다.
    weekly = load_weekly()
    data["weekly"] = weekly
    data["availableWeeks"] = available_weeks(weekly)
    data["weeklySummary"] = weekly_summary(weekly, datetime.now(), config)
    save_json(data, config)

    debug_log(f"업로드 완료: {data['updatedAt']}")
    debug_log(f"권역: {config['area']} / slug: {config['slug']}")
    debug_log(f"전체 기사 수: {data['total']['count']}")
    debug_log(f"접속중 기사 수: {data['total']['onlineCount']}")
    for team in config["team_order"]:
        debug_log(f"{team} 접속중: {data['teams'][team]['summary']['onlineCount']}")
    debug_log(
        "구간실적/목표: "
        + " | ".join(
            f"{p}={data['total'].get(p, 0)}/{sum(to_int(data['teams'][t]['targets'].get(p, 0)) for t in config['team_order'])}"
            for p in PERIODS
        )
    )
    debug_log(f"전체 완료: {data['total']['complete']}")
    debug_log(f"전체 거절: {data['total']['reject']}")
    debug_log(f"전체 취소: {data['total']['cancel']}")
    debug_log(f"수락률: {data['total']['acceptRate']}%")
    return data

def activate_center(config):
    global AREA_NAME, TEAM_ORDER, AREA_CONFIG, TEAM_MAP_PATH
    global LIVE_PATH, WEEKLY_PATH, CURRENT_SLUG, DATA_FILE, WEEKLY_FILE
    global REQUIRED_TEAM_RIDERS, TEAM_MAP_CACHE, VERIFIED_CENTER_CODE
    global IDENTITY_TEAM_MAP, NAME_TEAM_MAP, EXCLUDED_IDENTITY_KEYS
    VERIFIED_CENTER_CODE = None
    AREA_NAME = config["area"]
    CURRENT_SLUG = config["slug"]
    TEAM_ORDER = list(config["team_order"])
    AREA_CONFIG = {AREA_NAME: dict(config["area_config"])}
    TEAM_MAP_PATH = config["team_map_path"]
    LIVE_PATH = config["live_path"]
    WEEKLY_PATH = config["weekly_path"]
    REQUIRED_TEAM_RIDERS = dict(config.get("required_team_riders") or {})
    IDENTITY_TEAM_MAP = dict(config.get("identity_team_map") or {})
    NAME_TEAM_MAP = {norm(k): norm(v) for k, v in dict(config.get("name_team_map") or {}).items()}
    EXCLUDED_IDENTITY_KEYS = set(config.get("excluded_identity_keys") or [])
    DATA_FILE = BASE_DIR / f"data_{CURRENT_SLUG}.json"
    WEEKLY_FILE = BASE_DIR / f"weekly_{CURRENT_SLUG}.json"
    TEAM_MAP_CACHE = None


def _visible(locator):
    try:
        return locator.count() > 0 and locator.first.is_visible()
    except Exception:
        return False


def _selected_center_code_on_change_page(page):
    """협력사 변경 화면의 선택 박스에 표시된 현재 DP코드를 반환합니다."""
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


def _wait_center_code(page, expected_code=None, timeout_seconds=CENTER_RENDER_TIMEOUT):
    deadline = time.monotonic() + timeout_seconds
    last_code = ""
    while time.monotonic() < deadline:
        try:
            code = _selected_center_code_on_change_page(page)
        except Exception:
            code = ""
        if code:
            last_code = code
            if expected_code is None or code == expected_code:
                return code
        time.sleep(0.10)
    return last_code


def _click_center_option(page, target_code, timeout_seconds=CENTER_RENDER_TIMEOUT):
    """드롭다운 옵션이 실제 나타나는 순간 즉시 클릭합니다."""
    deadline = time.monotonic() + timeout_seconds
    script = r"""
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
    """
    while time.monotonic() < deadline:
        try:
            selected = page.evaluate(script, target_code)
        except Exception:
            selected = ""
        if selected:
            return selected
        time.sleep(0.10)
    return ""


def change_center(page, config):
    """DP코드가 실제로 바뀐 경우에만 다음 수집 단계로 진행합니다."""
    global VERIFIED_CENTER_CODE
    VERIFIED_CENTER_CODE = None

    target_code = norm(config.get("center_code", ""))
    if not re.fullmatch(r"DP\d+", target_code):
        raise RuntimeError(f"{config['area']} center_code 설정 오류: {target_code!r}")

    debug_log(f"협력사 변경 시도: {config['area']} / {target_code}")
    change_url = "https://deliverycenter.baemin.com/center/change"

    page.goto(change_url, wait_until="domcontentloaded")
    current_code = _wait_center_code(page)
    debug_log(f"변경 전 실제 협력사: {current_code or '확인 실패'}")

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
        selected = _click_center_option(page, target_code)
        if not selected:
            raise RuntimeError(f"{config['area']}({target_code}) 옵션을 찾지 못했습니다.")

        done = page.get_by_text("선택 완료", exact=True)
        if done.count() == 0 or not done.first.is_visible():
            raise RuntimeError("선택 완료 버튼을 찾지 못했습니다.")
        done.first.click()
        # 선택 저장 요청이 시작될 최소 유예만 둔 뒤, 실제 DP코드 확인으로 대기합니다.
        time.sleep(CENTER_COMMIT_GRACE)

    page.goto(change_url, wait_until="domcontentloaded")
    verified_code = _wait_center_code(page, expected_code=target_code)
    if verified_code != target_code:
        raise RuntimeError(
            f"협력사 전환 검증 실패: 목표={target_code}, 실제={verified_code or '확인 실패'}; "
            "Firebase 업로드를 차단합니다."
        )

    VERIFIED_CENTER_CODE = verified_code
    debug_log(f"협력사 변경 검증 성공: {config['area']} / {verified_code}")

    # 기사실적 화면 이동은 collect_all_pages_by_api()가 response listener를 먼저 건 뒤 수행합니다.
    # 여기서 미리 열면 핵심 delivery-status 응답을 놓칠 수 있으므로 이동하지 않습니다.
def main():
    print(f"TNT LIVE Collector · 배민 API 원본수신 V3 · {len(CENTER_CONFIGS)}DP")
    print("프로필: chrome_profile_supersonic_core_v1")

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(BASE_DIR / "chrome_profile_supersonic_core_v1"),
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

        # 자동시작 모드:
        # - 기존 Chrome 프로필의 로그인 세션이 살아 있으면 바로 수집 시작
        # - 세션이 만료되었으면 브라우저를 열어둔 채 사용자가 로그인할 때까지 대기
        print("배민비즈 로그인 상태 확인 중...")
        login_wait_started = time.monotonic()
        last_notice = 0.0
        while True:
            try:
                current_url = (page.url or "").lower()
                body_text = page.locator("body").inner_text(timeout=3000)
            except Exception:
                current_url = (page.url or "").lower()
                body_text = ""

            # 기사실적 화면에서 흔히 확인 가능한 텍스트/URL을 함께 사용.
            authenticated = (
                "/delivery/history" in current_url
                and (
                    "기사" in body_text
                    or "라이더" in body_text
                    or "협력사" in body_text
                    or "배달" in body_text
                )
            )
            if authenticated:
                break

            now_mono = time.monotonic()
            if now_mono - last_notice >= 30:
                waited = int(now_mono - login_wait_started)
                print(f"로그인 대기 중 · 브라우저에서 배민비즈 로그인해 주세요. ({waited}초)")
                last_notice = now_mono

            # 로그인/휴대폰 인증 중에는 절대 강제 이동하지 않습니다.
            # 인증 페이지를 새로고침하면 SMS 인증 입력 화면이 초기화될 수 있으므로
            # 사용자가 인증을 끝낼 때까지 현재 페이지를 그대로 유지합니다.
            time.sleep(3)

        keep_chrome_rendering(browser, page)
        print("로그인 확인 · 수집 자동 시작 · Chrome은 최소화하지 마세요.")
        print_memory_status("수집 시작")

        try:
            cycle_no = 0
            while True:
                cycle_no += 1
                cycle_started = datetime.now()
                cycle_started_mono = time.monotonic()
                print(f"\n[CYCLE {cycle_no}] 시작")
                _, cycle_private_start = process_memory_mb()
                success_count = 0
                dp_durations = []

                for idx, config in enumerate(CENTER_CONFIGS, start=1):
                    dp_started_mono = time.monotonic()
                    try:
                        keep_chrome_rendering(browser, page)
                        activate_center(config)
                        change_center(page, config)
                        keep_chrome_rendering(browser, page)
                        run_update(page, config)
                        success_count += 1
                        dp_elapsed = time.monotonic() - dp_started_mono
                        dp_durations.append(dp_elapsed)
                        update_collector_status(
                            config,
                            state="OK",
                            duration_seconds=dp_elapsed,
                            cycle_no=cycle_no,
                        )
                        if cycle_no <= MEMORY_DIAG_INITIAL_CYCLES:
                            print_memory_status(f"CYCLE {cycle_no} / {config['area']} 후", cycle_private_start)
                    except KeyboardInterrupt:
                        raise
                    except Exception as e:
                        dp_elapsed = time.monotonic() - dp_started_mono
                        dp_durations.append(dp_elapsed)
                        update_collector_status(
                            config,
                            state="ERROR",
                            duration_seconds=dp_elapsed,
                            cycle_no=cycle_no,
                            error=e,
                        )
                        append_collector_error(
                            config,
                            duration_seconds=dp_elapsed,
                            cycle_no=cycle_no,
                            error=e,
                        )
                        print(f"[{config['area']}] 오류 발생 · {dp_elapsed:.1f}초 · {e}")
                        if cycle_no <= MEMORY_DIAG_INITIAL_CYCLES:
                            print_memory_status(f"CYCLE {cycle_no} / {config['area']} 오류 후", cycle_private_start)
                        if DEBUG_LOG:
                            import traceback
                            traceback.print_exc()

                elapsed = time.monotonic() - cycle_started_mono
                remaining = max(0.0, CYCLE_TARGET_SECONDS - elapsed)
                utilization = (elapsed / CYCLE_TARGET_SECONDS) * 100 if CYCLE_TARGET_SECONDS else 0
                avg_dp = (sum(dp_durations) / len(dp_durations)) if dp_durations else 0
                safe_budget = CYCLE_TARGET_SECONDS * CYCLE_WARN_RATIO
                estimated_safe_dp = int(safe_budget // avg_dp) if avg_dp > 0 else 0

                if success_count == len(CENTER_CONFIGS):
                    print(f"[CYCLE {cycle_no} 완료] {success_count}/{len(CENTER_CONFIGS)} 정상 · {elapsed:.1f}초")
                else:
                    print(f"[CYCLE {cycle_no} 완료] {success_count}/{len(CENTER_CONFIGS)} 성공 · {elapsed:.1f}초")

                # 사이클 단위 순환참조 정리. 정상 RAM 상세로그는 DEBUG_LOG=True일 때만 표시합니다.
                gc.collect()
                print_memory_status(f"CYCLE {cycle_no} 종료", cycle_private_start)

                if elapsed > safe_budget:
                    print(f"[경고] 사이클 {elapsed:.1f}초 · 목표 여유구간 초과")
                if elapsed >= CYCLE_TARGET_SECONDS:
                    print("다음 수집 즉시 시작")
                else:
                    print(f"다음 수집 {remaining:.0f}초 후")
                    time.sleep(remaining)
        finally:
            _close_chrome_render_session()
            try:
                browser.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
