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
VERIFIED_CENTER_CODE = None
IDENTITY_TEAM_MAP = {}
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
  'identity_team_map': {'uid_shopvw': '성공드림', 'uid_qw1637': '성공드림', 'uid_yy2146': '성공드림', 'uid_doshin0000': '성공드림', 'uid_hero2000a': '성공드림', 'uid_kim1302': '성공드림', 'uid_BC97751': '성공드림', 'uid_820111': '성공드림', 'uid_kimkutak49r6': '성공드림', 'uid_wprb44': '성공드림', 'uid_shin84': '성공드림', 'uid_pna5511': '성공드림', 'uid_01093634891': '성공드림', 'uid_jieum1010': '성공드림', 'uid_sign111': '성공드림', 'uid_jwss8489': '성공드림', 'uid_sjs071021': '성공드림', 'uid_inhoshin': '성공드림', 'uid_stv77': '성공드림', 'uid_Minhlong0109': '성공드림', 'uid_injae7082': '성공드림', 'uid_jjjgw57': '성공드림', 'uid_sophia1004': '성공드림', 'uid_gil2048': '성공드림', 'uid_gil3378': '성공드림', 'uid_ggttooii': '성공드림', 'uid_cjhcjh1': '성공드림', 'uid_pee8156': '성공드림', 'uid_pwjg25': '성공드림', 'uid_ts2037': '성공드림', 'uid_djmatzzang': '성공드림', 'uid_nigimi4i': '성공드림', 'uid_gallardo007': '성공드림'}},
 {'area': '중구A',
   'slug': 'junggua',
   'aliases': ['대구중A온나1(DP2505305786)', '대구중A온나1 (DP2505305786)', '대구중A온나1', 'DP2505305786'],
   'center_code': 'DP2505305786',
   'team_order': ['슈퍼', '성공', '직영', 'BM', '상생', '나르미', '신규'],
   'area_config': {'슈퍼': 2.8, '성공': 3, '직영': 4.2, 'BM': 2, '상생': 1, '나르미': 2.0, '신규': 0},
   'team_map_path': '/settings/junggua/teamMap',
   'live_path': '/live/junggua',
   'weekly_path': '/weekly/junggua',
   'required_team_riders': {},
   'identity_team_map': {'phone_01057456300': '슈퍼', 'uid_aa57456300': '슈퍼', 'phone_01023326437': '나르미', 'uid_agiwang88': '나르미', 'phone_01089510080': '슈퍼', 'uid_won6542': '슈퍼', 'phone_01095661008': '슈퍼', 'uid_daedong1008': '슈퍼', 'phone_01083667241': '나르미', 'phone_01029972284': '나르미', 'uid_yyss0908': '나르미', 'phone_01027257069': '직영', 'uid_yuil666': '직영', 'phone_01096792722': '슈퍼', 'uid_jm3315': '슈퍼', 'phone_01095157960': '나르미', 'uid_yby9913': '나르미', 'phone_01028105684': '직영', 'uid_ansgh5684': '직영', 'phone_01085654445': '슈퍼', 'uid_bmw159357': '슈퍼', 'phone_01076637520': '나르미', 'uid_woals77s': '나르미', 'phone_01097790044': '슈퍼', 'uid_wngh1710': '슈퍼', 'phone_01092032403': '나르미', 'uid_asessnail': '나르미', 'phone_01062457690': '슈퍼', 'uid_hnm05003': '슈퍼', 'phone_01057789690': '슈퍼', 'uid_ngtm9': '슈퍼', 'phone_01071548131': '슈퍼', 'uid_fnwnfk33': '슈퍼', 'phone_01035272356': '직영', 'uid_moon1250': '직영', 'phone_01021978393': '나르미', 'phone_01055488393': '나르미', 'phone_01051217089': '슈퍼', 'uid_dream7350': '슈퍼', 'phone_01036163400': '슈퍼', 'uid_cyon2231': '슈퍼', 'phone_01093442156': '슈퍼', 'uid_kdh7631': '슈퍼', 'phone_01022877383': '슈퍼', 'uid_chols18': '슈퍼', 'phone_01082471499': '직영', 'uid_kbc1422': '직영', 'phone_01074099919': '슈퍼', 'uid_ksm108': '슈퍼', 'phone_01045846363': '나르미', 'uid_tkddlf6361': '나르미', 'phone_01090397150': '나르미', 'uid_kimsh7150': '나르미', 'phone_01095819421': '직영', 'uid_BC942145': '직영', 'phone_01090721235': '나르미', 'uid_개인정보처리방침\nCopyright ⓒ Woowa Brothers Corp All Rights Reserved_': '나르미', 'phone_01084171900': '슈퍼', 'uid_sos1900': '슈퍼', 'phone_01088588862': '직영', 'uid_mysigon2': '직영', 'phone_01044606052': '슈퍼', 'uid_kkk7285': '슈퍼', 'phone_01033310513': '나르미', 'uid_das5019': '나르미', 'phone_01091725567': '나르미', 'uid_Kys5567': '나르미', 'phone_01036966753': '슈퍼', 'uid_dudtn6753': '슈퍼', 'phone_01038148938': '슈퍼', 'uid_ko7330': '슈퍼', 'phone_01076884319': '슈퍼', 'uid_dbswo4633': '슈퍼', 'phone_01036495033': '슈퍼', 'uid_kis5033': '슈퍼', 'phone_01035271068': '슈퍼', 'uid_tjq0925': '슈퍼', 'phone_01023878546': '나르미', 'uid_wnduqdl91': '나르미', 'phone_01077419068': '나르미', 'uid_khjwj2': '나르미', 'phone_01025047344': '슈퍼', 'uid_smilemaru19': '슈퍼', 'phone_01040540117': '나르미', 'uid_shoorainbow': '나르미', 'phone_01086303485': '슈퍼', 'uid_jungh16': '슈퍼', 'phone_01035373966': '나르미', 'phone_01076343059': '직영', 'uid_ckddn456123': '직영', 'phone_01080820179': '슈퍼', 'uid_kyeongjin1': '슈퍼', 'phone_01043431800': '나르미', 'uid_pks061012': '나르미', 'phone_01079160000': '나르미', 'uid_gcpark100': '나르미', 'phone_01079637387': '슈퍼', 'uid_rktl1212': '슈퍼', 'phone_01038068348': '슈퍼', 'uid_sbeotjd': '슈퍼', 'phone_01064634980': '슈퍼', 'uid_tjdrbs11020': '슈퍼', 'phone_01082215061': '슈퍼', 'uid_epik8498': '슈퍼', 'phone_01058974243': '슈퍼', 'phone_01075765128': '슈퍼', 'uid_jrs7639': '슈퍼', 'phone_01068939625': '슈퍼', 'uid_pj0906': '슈퍼', 'phone_01081407166': '직영', 'uid_rudtnwlstn12': '직영', 'phone_01038217652': '직영', 'phone_01077361022': '나르미', 'uid_gogoterry': '나르미', 'phone_01050462797': '나르미', 'phone_01024260078': '슈퍼', 'uid_skce123': '슈퍼', 'phone_01049858252': '직영', 'uid_ahafree': '직영', 'phone_01037102977': '슈퍼', 'uid_skch01': '슈퍼', 'phone_01091519166': '직영', 'uid_zxc9166': '직영', 'phone_01072624644': '나르미', 'uid_yss0908': '나르미', 'phone_01039723064': '직영', 'uid_jaeyong1983': '직영', 'phone_01082092975': '나르미', 'uid_ascmoon': '나르미', 'phone_01091614445': '직영', 'uid_pooh3986': '직영', 'phone_01076271378': '나르미', 'uid_fmamfnan': '나르미', 'phone_01042577444': '슈퍼', 'uid_h7444': '슈퍼', 'phone_01048950609': '직영', 'uid_mylive00': '직영', 'phone_01076263146': '직영', 'uid_chsolem2': '직영', 'phone_01079049872': '슈퍼', 'uid_boo2132': '슈퍼', 'phone_01096588114': '슈퍼', 'uid_ggmomo98': '슈퍼', 'phone_01028825855': '직영', 'uid_dlrmagud': '직영', 'phone_01059094145': '슈퍼', 'uid_intherain010': '슈퍼', 'phone_01040712284': '나르미', 'phone_01058949971': '나르미', 'uid_lmh0113': '나르미', 'phone_01076109761': '슈퍼', 'uid_lesangm': '슈퍼', 'phone_01099197690': '슈퍼', 'uid_moeer': '슈퍼', 'phone_01057224644': '나르미', 'phone_01048683753': '나르미', 'uid_asd0714': '나르미', 'phone_01059474863': '슈퍼', 'uid_hn54002': '슈퍼', 'phone_01083747444': '슈퍼', 'uid_mywoals66': '슈퍼', 'phone_01054442225': '직영', 'uid_dokebi3': '직영', 'phone_01044115684': '직영', 'uid_zzunga820407': '직영', 'phone_01064988113': '슈퍼', 'uid_dlwjdqls0813': '슈퍼', 'phone_01090909466': '나르미', 'phone_01042220059': '나르미', 'uid_dlwhdejr77': '나르미', 'phone_01090893777': '나르미', 'uid_dididirmsid': '나르미', 'phone_01049380544': '슈퍼', 'uid_cdll27': '슈퍼', 'phone_01041332410': '직영', 'uid_dnjs96000': '직영', 'phone_01039704456': '나르미', 'uid_tepery': '나르미', 'phone_01025239330': '슈퍼', 'uid_roder9330': '슈퍼', 'phone_01022224512': '슈퍼', 'uid_rksek7763': '슈퍼', 'phone_01085403884': '슈퍼', 'uid_qwqw1230': '슈퍼', 'phone_01040479098': '나르미', 'uid_jikrty2621': '나르미', 'phone_01068654893': '슈퍼', 'uid_cion4893': '슈퍼', 'phone_01035064035': '나르미', 'uid_jjisik': '나르미', 'phone_01038001769': '슈퍼', 'uid_Sin69333': '슈퍼', 'phone_01094174313': '슈퍼', 'uid_gnfcp': '슈퍼', 'phone_01045339113': '슈퍼', 'uid_wolf0122': '슈퍼', 'phone_01064072855': '슈퍼', 'uid_esthell2': '슈퍼', 'phone_01039945353': '나르미', 'uid_jjk73299': '나르미', 'phone_01046452907': '슈퍼', 'uid_chome0411': '슈퍼', 'phone_01049991096': '슈퍼', 'uid_dkgee': '슈퍼', 'phone_01029915550': '슈퍼', 'uid_jin70fa': '슈퍼', 'phone_01087059260': '슈퍼', 'uid_cghzxc': '슈퍼', 'phone_01073789884': '슈퍼', 'uid_choijy9219': '슈퍼', 'phone_01089302205': '슈퍼', 'uid_chlwnstn1226': '슈퍼', 'phone_01095126282': '슈퍼', 'uid_zuno10': '슈퍼', 'phone_01099000232': '직영', 'uid_vip1128': '직영', 'phone_01044331492': '나르미', 'uid_chs33': '나르미', 'phone_01098194222': '슈퍼', 'uid_cjh2331': '슈퍼', 'phone_01056608498': '슈퍼', 'uid_epik849812': '슈퍼', 'phone_01085065130': '슈퍼', 'uid_dkagh3295': '슈퍼', 'phone_01057851012': '직영', 'uid_riuxioknu': '직영', 'phone_01028323995': '직영', 'uid_cthanhqb': '직영', 'phone_01056641307': '성공', 'uid_screenstar': '성공', 'phone_01023727221': '직영', 'uid_ss10500': '직영', 'phone_01085970060': '직영', 'uid_kts822300': '직영', 'phone_01059336512': '직영', 'uid_gywnsdpwl10': '직영', 'phone_01030397177': '상생', 'uid_zet707': '상생', 'phone_01099158611': '성공', 'uid_saz1212': '성공', 'phone_01082056416': '직영', 'uid_youjoon0407': '직영', 'phone_01056589664': '성공', 'uid_bluesens': '성공', 'phone_01035050800': 'BM', 'uid_kolon77': 'BM', 'phone_01087623602': '직영', 'uid_bjw3602': '직영', 'phone_01030585896': '성공', 'uid_3hk2212': '성공', 'phone_01056439969': '직영', 'uid_qnfehr1237': '직영', 'phone_01088407989': 'BM', 'uid_mudark623': 'BM', 'phone_01077703289': '직영', 'uid_qlsdnsl': '직영', 'phone_01033168902': '직영', 'uid_tksxkdhwna99': '직영', 'phone_01055397207': '직영', 'uid_BC720742': '직영', 'phone_01026290157': '직영', 'uid_my101001': '직영', 'phone_01072346097': '직영', 'uid_kanghiung': '직영', 'phone_01084268623': '성공', 'uid_BC862346': '성공', 'phone_01065037450': '성공', 'uid_kooja79': '성공', 'phone_01088569679': '성공', 'uid_Good9679': '성공', 'phone_01058631372': 'BM', 'uid_fks024': 'BM', 'phone_01051444441': '직영', 'uid_Asd2259': '직영', 'phone_01088146134': '상생', 'uid_korea6587': '상생', 'phone_01076335554': '직영', 'uid_bm91bm91': '직영', 'phone_01026755482': '상생', 'uid_wnsrldihy': '상생', 'phone_01045424686': '성공', 'uid_rnjs9639': '성공', 'phone_01048899272': '직영', 'uid_akroto10': '직영', 'phone_01059241664': '상생', 'uid_sky1sea97': '상생', 'phone_01098366557': 'BM', 'uid_azxs0790': 'BM', 'phone_01058615229': '상생', 'uid_ddim5004': '상생', 'phone_01075379533': '성공', 'uid_qqaazz120000': '성공', 'phone_01028115580': '성공', 'uid_beatsuya': '성공', 'phone_01084310043': '직영', 'uid_alsghd33': '직영', 'phone_01085157793': '상생', 'uid_Himemay184': '상생', 'phone_01046515916': '직영', 'uid_개인정보처리방침': '직영', 'phone_01066988781': '직영', 'uid_wizzzzz2491': '직영', 'phone_01056322414': '상생', 'uid_kzuuya': '상생', 'phone_01080989458': '직영', 'uid_namh0801': '직영', 'phone_01048297999': '성공', 'uid_byung9643': '성공', 'phone_01038064118': '직영', 'uid_win9198': '직영', 'phone_01033749936': '직영', 'uid_kbc9936': '직영', 'phone_01021655947': '성공', 'uid_Kk6021': '성공', 'phone_01082505746': '상생', 'uid_zzlccg445': '상생', 'phone_01066873099': '직영', 'uid_k7811305': '직영', 'phone_01045114445': '상생', 'uid_aasdds': '상생', 'phone_01065589422': '성공', 'uid_nice1250': '성공', 'phone_01074965436': '직영', 'uid_sksmsk22': '직영', 'phone_01021649980': '직영', 'uid_kcc518551': '직영', 'phone_01094509952': '상생', 'uid_wjdgus9887': '상생', 'phone_01034898989': '성공', 'uid_wowgma2': '성공', 'phone_01062223655': '성공', 'uid_promisel': '성공', 'phone_01084016924': 'BM', 'uid_Jongman6189': 'BM', 'phone_01062980423': 'BM', 'uid_sadf8122': 'BM', 'phone_01066652756': '직영', 'uid_zzzsss5': '직영', 'phone_01097792669': '직영', 'uid_tk770322': '직영', 'phone_01026708245': '상생', 'uid_xkdlass0245': '상생', 'phone_01045889854': '성공', 'uid_sign222': '성공', 'phone_01082552058': '직영', 'uid_hyunjin2058': '직영', 'phone_01040826360': '상생', 'uid_kimli0109': '상생', 'phone_01057183351': '상생', 'uid_fkdnrtjd': '상생', 'phone_01081806691': '성공', 'uid_coolnjc': '성공', 'phone_01067957475': '직영', 'uid_bangho0112': '직영', 'phone_01063935129': '직영', 'uid_j63935129': '직영', 'phone_01023526995': '직영', 'uid_njw0414': '직영', 'phone_01039172070': '성공', 'uid_fbtmdcks31': '성공', 'phone_01036933810': '성공', 'uid_stp21': '성공', 'phone_01022695096': 'BM', 'uid_kslove1269': 'BM', 'phone_01021948560': '직영', 'uid_j1030jhs': '직영', 'phone_01083447540': '성공', 'uid_qkrtkddlf': '성공', 'phone_01042339955': '직영', 'uid_snskwks': '직영', 'phone_01071332776': '직영', 'uid_71332776': '직영', 'phone_01072529443': '직영', 'uid_pyh9443': '직영', 'phone_01098898011': '직영', 'uid_jhan1052': '직영', 'phone_01077092461': '직영', 'uid_wogus9043': '직영', 'phone_01062089030': '상생', 'uid_popiop123': '상생', 'phone_01050601319': '성공', 'uid_opop0323': '성공', 'phone_01038226593': '성공', 'uid_pcs1803': '성공', 'phone_01073501388': '성공', 'uid_honga1388': '성공', 'phone_01051548925': '성공', 'uid_cs8925': '성공', 'phone_01048695822': '직영', 'uid_snns432': '직영', 'phone_01084451461': 'BM', 'uid_xkxl67': 'BM', 'phone_01028788705': 'BM', 'uid_qoqudgh456': 'BM', 'phone_01043125247': '상생', 'uid_abollo1': '상생', 'phone_01057734867': '성공', 'uid_tgb4ever': '성공', 'phone_01048678489': '성공', 'uid_tg4ever': '성공', 'phone_01022185625': '직영', 'uid_dnjs817': '직영', 'phone_01089479130': 'BM', 'uid_hg97507': 'BM', 'phone_01077154649': '직영', 'uid_zx0921': '직영', 'phone_01042454345': 'BM', 'uid_seoseo0314': 'BM', 'phone_01088657389': '직영', 'uid_eddie6577': '직영', 'phone_01093312498': '직영', 'uid_bogus2498': '직영', 'phone_01073973335': 'BM', 'uid_sa003114': 'BM', 'phone_01084418283': 'BM', 'uid_thdwodyd': 'BM', 'phone_01049078688': '직영', 'uid_halada011': '직영', 'phone_01064655868': '직영', 'uid_duddk6022': '직영', 'phone_01058638489': '성공', 'uid_tgs4ever': '성공', 'phone_01035002074': '성공', 'uid_aa35002074': '성공', 'phone_01095500590': 'BM', 'uid_cxz3131': 'BM', 'phone_01025248560': '성공', 'uid_Dawon51': '성공', 'phone_01058741714': '직영', 'uid_yousy1128': '직영', 'phone_01035523225': '성공', 'uid_yeoil486': '성공', 'phone_01077953316': '직영', 'uid_rkcl1234': '직영', 'phone_01096092776': '성공', 'uid_ysh2776': '성공', 'phone_01038042784': '직영', 'uid_onna2776': '직영', 'phone_01065219430': '직영', 'uid_cole9430': '직영', 'phone_01026701866': '직영', 'uid_dhkdrkdnl02': '직영', 'phone_01071446550': '직영', 'uid_eotkd93': '직영', 'phone_01036736050': '직영', 'uid_rmatja1214': '직영', 'phone_01084207505': '상생', 'uid_jjj3357': '상생', 'phone_01095337575': '직영', 'uid_aswq666': '직영', 'phone_01042343299': '상생', 'uid_3299yu3299': '상생', 'phone_01076801653': '직영', 'uid_tkddyd778': '직영', 'phone_01088861539': '직영', 'uid_aqeda': '직영', 'phone_01044336385': '직영', 'uid_gidrml12': '직영', 'phone_01046476973': '상생', 'uid_tmddyd9714': '상생', 'phone_01082820407': '성공', 'uid_BC200532': '성공', 'phone_01075099361': '성공', 'uid_lee9361': '성공', 'phone_01074053712': 'BM', 'uid_biomedics': 'BM', 'phone_01043663838': 'BM', 'uid_mystop1214': 'BM', 'phone_01085258088': '성공', 'uid_zwzwzwz': '성공', 'phone_01089567995': '성공', 'uid_nnhs6670': '성공', 'phone_01085799951': '성공', 'uid_hunt011': '성공', 'phone_01037694885': 'BM', 'uid_lee1hahaha': 'BM', 'phone_01059297202': 'BM', 'uid_r78789': 'BM', 'phone_01020440978': '성공', 'uid_Tack0957': '성공', 'phone_01095697982': '직영', 'uid_BC533812': '직영', 'phone_01082828008': '상생', 'uid_luxury8707': '상생', 'phone_01022502382': '성공', 'uid_imss119': '성공', 'phone_01090651819': '성공', 'uid_hra0318': '성공', 'phone_01026465953': '직영', 'uid_csp7687': '직영', 'phone_01044006914': '상생', 'uid_aa7096': '상생', 'phone_01049559963': '성공', 'uid_junhan0202': '성공', 'phone_01031342157': '직영', 'uid_rhfjsrjdia1': '직영', 'phone_01056974044': '상생', 'uid_ssogi1': '상생', 'phone_01027564187': '직영', 'uid_sok1038': '직영', 'phone_01035410201': '상생', 'uid_cat3434': '상생', 'phone_01053428451': '상생', 'uid_jhj845100': '상생', 'phone_01055945572': 'BM', 'uid_fiat4408': 'BM', 'phone_01055114469': '상생', 'uid_B4469011': '상생', 'phone_01021952353': '상생', 'uid_jang2535': '상생', 'phone_01035703210': '성공', 'uid_ssssb95': '성공', 'phone_01075042474': '직영', 'uid_vhtpglehs': '직영', 'phone_01059186698': '직영', 'uid_junjunghwan1': '직영', 'phone_01058408883': 'BM', 'uid_wjswls201': 'BM', 'phone_01055515588': '성공', 'uid_realdal': '성공', 'phone_01028176207': 'BM', 'uid_jun2817': 'BM', 'phone_01021889481': 'BM', 'uid_mamigirl1004': 'BM', 'phone_01057421370': '직영', 'uid_tjdgkr1370': '직영', 'phone_01051577745': 'BM', 'uid_freehug4610': 'BM', 'phone_01064783350': '상생', 'uid_mkoq80': '상생', 'phone_01048944440': 'BM', 'uid_hoya104': 'BM', 'phone_01077610715': '상생', 'uid_Kaze0715': '상생', 'phone_01021432011': '직영', 'uid_eksfk711': '직영', 'phone_01064244113': '성공', 'uid_oppyn': '성공', 'phone_01025220677': '성공', 'uid_cho0677': '성공', 'phone_01089568216': '직영', 'uid_csyyyys': '직영', 'phone_01050137594': '성공', 'uid_zezx20': '성공', 'phone_01099546312': 'BM', 'uid_ccm7577': 'BM', 'phone_01056876099': '상생', 'uid_hjjphd': '상생', 'phone_01077011158': '상생', 'uid_kdkd88': '상생', 'phone_01063895509': '직영', 'uid_hwangjoil': '직영'},
   'excluded_identity_keys': ['phone_01020582724', 'phone_01023061112', 'phone_01024348122', 'phone_01028607600', 'phone_01033651548', 'phone_01034929496', 'phone_01037959383', 'phone_01054464713', 'phone_01055535804', 'phone_01055987613', 'phone_01057430409', 'phone_01057901107', 'phone_01062852543', 'phone_01072210501', 'phone_01076736626', 'phone_01081144903', 'phone_01088832434', 'phone_01089701982', 'phone_01089831091', 'phone_01091144577', 'phone_01091895291', 'phone_01095064566', 'phone_01099665758', 'uid_31324577', 'uid_BC6626125', 'uid_Syk1232', 'uid_diqkdndlstod74', 'uid_ish2751', 'uid_kgw49280', 'uid_kingzex333', 'uid_ksh9522', 'uid_lo154800', 'uid_msigumchi', 'uid_na0507', 'uid_psy524', 'uid_qopqop86', 'uid_rerere3', 'uid_sizz104', 'uid_sky624b', 'uid_sosms2', 'uid_sslove0317', 'uid_tg850824', 'uid_tnt2772', 'uid_umkilyong', 'uid_wkdgustlr81', 'uid_yes022619']}]

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



def keep_chrome_rendering(context, page):
    """Chrome 창을 최소화하지 않고 화면 바깥으로 이동해 렌더링을 계속 유지합니다."""
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
        print(f"{AREA_NAME} teamMap 팀명 마이그레이션 완료: {len(updates)}명")
        for rider_name, team in list(updates.items())[:20]:
            print(f"  {rider_name} -> {team}")
    else:
        print(f"{AREA_NAME} teamMap 팀명 마이그레이션: 변경 없음")

    TEAM_MAP_CACHE = migrated
    return migrated


def firebase_safe_key(value):
    """Firebase key 금지문자를 제거한 안정적인 문자열을 만듭니다."""
    value = norm(value)
    return re.sub(r'[.#$\[\]/]', '_', value)


def rider_team_keys(name, phone="", user_id="", include_name=True):
    """동명이인 충돌 방지를 위해 고유 식별키를 우선 반환합니다.

    우선순위:
      1) 전화번호
      2) 배민 userId
      3) 기존 이름 key (하위 호환)
    """
    keys = []
    phone_key = normalize_phone(phone)
    if phone_key:
        keys.append("phone_" + phone_key)

    user_key = firebase_safe_key(user_id)
    if user_key:
        keys.append("uid_" + user_key)

    name_key = norm(name)
    if include_name and name_key:
        keys.append(name_key)

    return keys


def team_of(name, phone="", user_id=""):
    global TEAM_MAP_CACHE
    name = norm(name)
    if TEAM_MAP_CACHE is None:
        try:
            TEAM_MAP_CACHE = migrate_team_map_names()
            print(f"teamMap 로드 완료: {len(TEAM_MAP_CACHE)}명 / {AREA_NAME}")
        except Exception as e:
            print("teamMap 로드/마이그레이션 실패:", e)
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
          allDayComplete,
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
            complete = to_int(group.get("complete", 0))
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



VERIFIED_DUPLICATE_RIDER_NAMES = {"박영근"}


def rider_identity_keys(rider):
    """기사 중복 판별 키.

    신규 배민 UI에서 같은 기사의 userId 값이 다른 행에서는 phone 칸으로
    밀려 읽히는 경우까지 잡습니다. 이름만 같은 동명이인은 합치지 않습니다.
    """
    rider = rider or {}
    keys = []

    phone = normalize_phone(rider.get("phone", ""))
    user_id = norm(rider.get("userId", "")).lower()
    user_digits = normalize_phone(user_id)

    if phone:
        keys.append(("identity", phone))

    if user_id:
        keys.append(("userId", user_id))

    # 실제 중복 기사로 확인된 이름만 이름 자체를 보조 신원키로 사용합니다.
    # 전체 기사에 이름키를 적용하지 않으므로 동명이인은 계속 분리됩니다.
    rider_name = norm(rider.get("name", ""))
    if rider_name in VERIFIED_DUPLICATE_RIDER_NAMES:
        keys.append(("verifiedName", rider_name))

    # userId가 전화번호 형태(10~11자리 숫자)라면 phone과 같은 신원 토큰으로도 비교.
    # 예: 박영근 A행 userId=01058974243 / B행 phone=01058974243
    if user_digits and len(user_digits) in (10, 11):
        keys.append(("identity", user_digits))

    return list(dict.fromkeys(keys))


def rider_quality_score(rider):
    """중복 카드 중 실적/신원 데이터가 더 온전한 행을 우선합니다."""
    rider = rider or {}
    hourly = rider.get("hourly") or []
    return (
        0 if rider.get("placeholder") else 1000000,
        100000 if rider.get("isOnline") else 0,
        to_int(rider.get("complete", 0)),
        to_int(rider.get("morning", 0)) + to_int(rider.get("afternoon", 0))
        + to_int(rider.get("evening", 0)) + to_int(rider.get("midnight", 0)),
        sum(to_int(v) for v in hourly[:24]),
        len(normalize_phone(rider.get("phone", ""))),
        len(norm(rider.get("userId", ""))),
    )


def merge_duplicate_riders(a, b):
    """동일 기사로 판정된 두 행을 하나로 정리합니다."""
    a = dict(a or {})
    b = dict(b or {})
    if rider_quality_score(b) > rider_quality_score(a):
        base, other = b, a
    else:
        base, other = a, b
    base = dict(base)

    for key in ("name", "phone", "userId", "status", "team"):
        if not norm(base.get(key, "")) and norm(other.get(key, "")):
            base[key] = other.get(key)

    if not base.get("hourly") and other.get("hourly"):
        base["hourly"] = other.get("hourly")
    return base


def dedupe_riders(riders, log_prefix=""):
    """
    phone 또는 userId가 같은 경우에만 같은 기사로 합칩니다.
    이름만 같은 동명이인은 서로 다른 기사로 그대로 유지합니다.
    """
    result = []
    key_to_index = {}
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

        # phone / userId가 서로 다른 기존 카드에 각각 걸린 비정상 케이스까지 하나로 병합
        for extra_idx in reversed(matched[1:]):
            result[keep_idx] = merge_duplicate_riders(result[keep_idx], result[extra_idx])
            result.pop(extra_idx)

        # 배열 인덱스가 바뀔 수 있으므로 맵 재구성
        key_to_index = {}
        for i, row in enumerate(result):
            for k in rider_identity_keys(row):
                key_to_index[k] = i

    if duplicate_count:
        prefix = f"{log_prefix} " if log_prefix else ""
        print(f"{prefix}중복 기사 {duplicate_count}건 제거 완료")

    return result

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

        before_count = len(all_riders)
        all_riders.extend(riders)
        all_riders = dedupe_riders(all_riders, f"{page_no + 1}페이지")
        new_count = len(all_riders) - before_count

        print(f"{page_no + 1}페이지 신규 고유 기사 수: {new_count}")

        if new_count == 0:
            print("새 고유 기사 없음. 마지막 페이지로 판단하고 종료")
            break

    all_riders = dedupe_riders(all_riders, "최종 수집")
    all_riders = ensure_required_rider_cards(all_riders)
    all_riders = dedupe_riders(all_riders, "카드 보강 후")
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



def is_excluded_rider(rider):
    """탈퇴 지사 기사는 전화번호/userId가 일치할 때만 제외합니다."""
    for key in rider_team_keys(rider.get("name", ""), rider.get("phone", ""), rider.get("userId", ""), include_name=False):
        if key in EXCLUDED_IDENTITY_KEYS:
            return True
    return False


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

    riders = collect_all_pages_by_dom(page)
    if EXCLUDED_IDENTITY_KEYS:
        before_count = len(riders)
        riders = [r for r in riders if not is_excluded_rider(r)]
        removed = before_count - len(riders)
        if removed:
            print(f"{AREA_NAME} 탈퇴 지사 기사 제외: {removed}명")
    if len(riders) == 0:
        raise RuntimeError("기사 데이터를 못 읽었습니다.")

    data = make_data(riders, config)

    # 수집 직후부터 권역값을 검증하여 다른 권역 덮어쓰기를 차단합니다.
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
    global IDENTITY_TEAM_MAP, EXCLUDED_IDENTITY_KEYS
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


def change_center(page, config):
    """DP코드가 실제로 바뀐 경우에만 다음 수집 단계로 진행합니다."""
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
    print("SUPERSONIC 통합 다권역 DOM 자동 수집기 - 화면 밖 백그라운드 모드")
    print("대상 권역:", ", ".join(c["area"] for c in CENTER_CONFIGS))

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(BASE_DIR / "chrome_profile_supersonic"),
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

        print("1. 열린 배민비즈 창에서 슈퍼소닉 계정으로 로그인하세요.")
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
                print(f"{REFRESH_SECONDS}초 후 다시 달서A부터 수집합니다.")
                time.sleep(REFRESH_SECONDS)
        finally:
            try:
                browser.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
