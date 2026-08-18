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
DATA_FILE = BASE_DIR / "data_vic.json"
HTML_FILE = BASE_DIR / "vic.html"
WEEKLY_FILE = BASE_DIR / "weekly_vic.json"

AREA_NAME = "중구A"
TEAM_ORDER = []
AREA_CONFIG = {}
TEAM_MAP_PATH = ""
TEAM_MAP_PHONE_PATH = ""
TEAM_MAP_USERID_PATH = ""
LIVE_PATH = ""
WEEKLY_PATH = ""
CURRENT_SLUG = ""
REQUIRED_TEAM_RIDERS = {}
TEAM_MAP_CACHE = None
TEAM_MAP_PHONE_CACHE = None
TEAM_MAP_USERID_CACHE = None
STATIC_TEAM_MAP = {}
STATIC_TEAM_MAP_PHONE = {}
STATIC_TEAM_MAP_USERID = {}
STATIC_TEAM_MAP_CONFLICT_NAMES = {}
VERIFIED_CENTER_CODE = None

CENTER_CONFIGS = [
    {
        "area": "중구A",
        "slug": "vic",
        "aliases": [
            "대구중A온나1(DP2505305786)",
            "대구중A온나1 (DP2505305786)",
            "대구중A온나1",
            "DP2505305786",
        ],
        "center_code": "DP2505305786",
        "team_order": ["성공", "상생", "BM", "서구", "룰랄", "미분류"],
        "area_config": {
            "성공": 3.25,
            "상생": 1.25,
            "BM": 2.25,
            "서구": 3.25,
            "룰랄": 0,
            "미분류": 0,
        },
        "team_map_path": "/settings/vic/teamMap",
        "team_map_phone_path": "/settings/vic/teamMapPhone",
        "team_map_userid_path": "/settings/vic/teamMapUserId",
        "live_path": "/live/vic",
        "weekly_path": "/weekly/vic",
        "required_team_riders": {},
        "static_team_map": {'PHAN NGOC TUAN': '서구',
 'TRAN CHI THANH': '서구',
 '구민철': '성공',
 '구범모': '성공',
 '구은미': '성공',
 '구자돈': '성공',
 '구태회': '성공',
 '권노은': 'BM',
 '권도현': 'BM',
 '권민수': '상생',
 '권성한': '서구',
 '권승창': '성공',
 '권연길': '상생',
 '권혁영': '상생',
 '권현민': '성공',
 '권현수': '룰랄',
 '김경민': '성공',
 '김경우': 'BM',
 '김규종': '상생',
 '김근년': '성공',
 '김남수': '성공',
 '김대호': '서구',
 '김도섭': '룰랄',
 '김도형': '서구',
 '김맹훈': '성공',
 '김명한': '상생',
 '김미나': '상생',
 '김민성': '서구',
 '김민수': '서구',
 '김민후': '서구',
 '김상근': '성공',
 '김성국': '서구',
 '김성훈': '서구',
 '김양수': '상생',
 '김영진': '상생',
 '김영환': '성공',
 '김용민': '서구',
 '김의진': '서구',
 '김정현': '상생',
 '김종만': 'BM',
 '김주완': '성공',
 '김지언': 'BM',
 '김지원': 'BM',
 '김지윤': '서구',
 '김지현': '서구',
 '김진우': '상생',
 '김태관': '서구',
 '김태수': '룰랄',
 '김태현': '상생',
 '김현숙': '성공',
 '김현진': '서구',
 '김형일': '상생',
 '나두환': '성공',
 '나욱성': '상생',
 '나종천': '성공',
 '류승찬': '성공',
 '명제규': '성공',
 '문용덕': '성공',
 '문지현': '성공',
 '박경신': 'BM',
 '박근우': '서구',
 '박도현': '서구',
 '박민재': 'BM',
 '박병국': '서구',
 '박상일': '성공',
 '박승일': '서구',
 '박승호': '서구',
 '박시환': 'BM',
 '박윤현': '서구',
 '박재한': '룰랄',
 '박재현': '서구',
 '박정숙': '상생',
 '박종진': '성공',
 '박종현': '상생',
 '박진영': '성공',
 '박찬빈': 'BM',
 '박찬석': '성공',
 '박찬홍': '성공',
 '박채윤': '서구',
 '박충석': '성공',
 '박태환': '룰랄',
 '박해철': 'BM',
 '배병호': 'BM',
 '배시준': '상생',
 '배용환': '성공',
 '배준형': '상생',
 '백기원': '상생',
 '백병준': '성공',
 '백상우': '성공',
 '백승호': '서구',
 '서명수': '서구',
 '서성원': 'BM',
 '서창우': '룰랄',
 '석성운': '서구',
 '성기모': '성공',
 '손성민': 'BM',
 '손성일': '성공',
 '송상민': 'BM',
 '송재용': 'BM',
 '송호전': '서구',
 '신기박': '상생',
 '신동엽': '서구',
 '신성일': '서구',
 '안다빈': '성공',
 '안동숙': '성공',
 '안명만': '성공',
 '안유준': '룰랄',
 '안창길': '서구',
 '양철우': 'BM',
 '예창완': '성공',
 '유기현': '성공',
 '유만종': 'BM',
 '유신영': '룰랄',
 '윤성철': '서구',
 '윤성현': '성공',
 '윤성훈': '성공',
 '윤영미': '서구',
 '이경훈': '서구',
 '이기환': '서구',
 '이기훈': '서구',
 '이대진': '상생',
 '이동재': '서구',
 '이명희': '상생',
 '이미화': '상생',
 '이상용': '룰랄',
 '이상하': '서구',
 '이상현': '서구',
 '이서영': '성공',
 '이승용': '상생',
 '이재갑': '성공',
 '이재근': '성공',
 '이재현': 'BM',
 '이준형': 'BM',
 '이지은': '서구',
 '이지환': '성공',
 '이지훈': '성공',
 '이충효': '성공',
 '이태건': '상생',
 '이현규': 'BM',
 '이현우': '서구',
 '이현희': '상생',
 '이효원': '성공',
 '이희진': '룰랄',
 '임순식': '성공',
 '임윤관': '성공',
 '임종훈': '상생',
 '임준한': '성공',
 '장구현': '성공',
 '장민철': '상생',
 '장성익': '서구',
 '장성제': '상생',
 '장우혁': '상생',
 '장웅': '서구',
 '장일수': 'BM',
 '장재우': '상생',
 '장종관': '상생',
 '장종율': '상생',
 '전수빈': '성공',
 '전영태': '룰랄',
 '전재구': '성공',
 '전진': 'BM',
 '정민수': '서구',
 '정병준': 'BM',
 '정상규': 'BM',
 '정석원': '서구',
 '정선우': 'BM',
 '정성학': '서구',
 '정성현': '상생',
 '정연우': '성공',
 '정영문': '성공',
 '정준영': 'BM',
 '정철우': '상생',
 '정호원': 'BM',
 '정효승': 'BM',
 '제성환': '상생',
 '조단마': '룰랄',
 '조민규': '성공',
 '조용석': '성공',
 '조희찬': '상생',
 '진영준': '성공',
 '채승용': '서구',
 '채우현': '성공',
 '채준병': 'BM',
 '채헌우': '상생',
 '최성혁': '상생',
 '최승호': '상생',
 '최웅': '성공',
 '최인기': '서구',
 '최창민': 'BM',
 '허정재': '상생',
 '홍순관': '상생',
 '홍승현': '상생',
 '홍영환': '서구',
 '황조일': '서구'},
        "static_team_map_phone": {'01020440978': '성공',
 '01020769566': '성공',
 '01021149959': '성공',
 '01021432011': '룰랄',
 '01021649980': '서구',
 '01021655947': '성공',
 '01021852042': '성공',
 '01021889481': 'BM',
 '01021915569': '서구',
 '01021948560': '서구',
 '01022185625': '서구',
 '01022502382': '성공',
 '01022616566': '서구',
 '01022695096': 'BM',
 '01023889008': '서구',
 '01024098811': '성공',
 '01024191421': '상생',
 '01024564187': '서구',
 '01025078325': '상생',
 '01025220677': '성공',
 '01025248560': '성공',
 '01026262651': '성공',
 '01026701866': '서구',
 '01026708245': '상생',
 '01026755482': '상생',
 '01027652904': '성공',
 '01028115580': '성공',
 '01028176207': 'BM',
 '01028323995': '서구',
 '01028464367': 'BM',
 '01028788705': 'BM',
 '01028911214': 'BM',
 '01030033405': '성공',
 '01030397177': '상생',
 '01030891417': '상생',
 '01033168902': '상생',
 '01035002074': '성공',
 '01035050800': 'BM',
 '01035410201': '상생',
 '01035654449': '상생',
 '01035703210': '성공',
 '01035883655': '상생',
 '01036736050': '서구',
 '01036933810': '성공',
 '01038226593': '성공',
 '01039172070': '성공',
 '01039919870': '서구',
 '01039920666': '서구',
 '01040501200': '서구',
 '01040672668': '상생',
 '01040826360': '상생',
 '01041462229': '성공',
 '01042339955': '서구',
 '01042343299': '상생',
 '01042454345': 'BM',
 '01043042290': '상생',
 '01043125247': '상생',
 '01043663838': 'BM',
 '01044006914': '상생',
 '01044336385': '서구',
 '01045114445': '상생',
 '01045424686': '성공',
 '01046476973': '상생',
 '01046515916': '서구',
 '01048164000': '성공',
 '01048678489': '성공',
 '01048899272': '룰랄',
 '01048944440': 'BM',
 '01049078688': '서구',
 '01049559963': '성공',
 '01050118988': '성공',
 '01050137594': '성공',
 '01050601319': '성공',
 '01051234567': '성공',
 '01051444441': '서구',
 '01051548925': '성공',
 '01051577745': 'BM',
 '01052522282': 'BM',
 '01053428451': '상생',
 '01054765948': '성공',
 '01055075936': '상생',
 '01055114469': '상생',
 '01055397207': '서구',
 '01055945572': 'BM',
 '01056402485': 'BM',
 '01056439969': '서구',
 '01056589664': '성공',
 '01056641307': '성공',
 '01056876099': '상생',
 '01056974044': '상생',
 '01057238008': '상생',
 '01057421370': '서구',
 '01057734867': '성공',
 '01057976442': '룰랄',
 '01058408883': 'BM',
 '01058538794': '룰랄',
 '01058615229': '상생',
 '01058627773': '룰랄',
 '01058631372': 'BM',
 '01058638489': '성공',
 '01058741714': '룰랄',
 '01059096107': 'BM',
 '01059297202': 'BM',
 '01059343137': '성공',
 '01059597632': 'BM',
 '01062089030': '상생',
 '01062843335': '룰랄',
 '01062950086': '상생',
 '01062980423': 'BM',
 '01062993655': '성공',
 '01063895509': '서구',
 '01064094333': '상생',
 '01064244113': '성공',
 '01064655868': '서구',
 '01064783350': '상생',
 '01064933050': '서구',
 '01065037450': '성공',
 '01065302304': '성공',
 '01065589422': '성공',
 '01066450996': '상생',
 '01066652756': '서구',
 '01066988781': '서구',
 '01067077209': '성공',
 '01068582771': 'BM',
 '01071146664': '성공',
 '01071446550': '서구',
 '01072733562': '서구',
 '01072861148': '성공',
 '01073501388': '성공',
 '01073973335': 'BM',
 '01074053712': 'BM',
 '01074446092': 'BM',
 '01074965436': '서구',
 '01075099361': '성공',
 '01075485726': 'BM',
 '01076698438': '성공',
 '01076801653': '룰랄',
 '01077092461': '서구',
 '01077154649': '서구',
 '01077947339': '서구',
 '01077953316': '서구',
 '01080989458': '서구',
 '01081030414': 'BM',
 '01081054147': '상생',
 '01081591929': '서구',
 '01081806691': '성공',
 '01081857995': '성공',
 '01081872153': '성공',
 '01082056416': '룰랄',
 '01082110828': '상생',
 '01082211902': '상생',
 '01082552058': '서구',
 '01082828008': '상생',
 '01083447540': '성공',
 '01083488222': '서구',
 '01083539065': '상생',
 '01083662532': '서구',
 '01084016924': 'BM',
 '01084098600': '성공',
 '01084207505': '상생',
 '01084310043': '서구',
 '01084418283': 'BM',
 '01084451461': 'BM',
 '01085157793': '상생',
 '01085195142': '룰랄',
 '01085238283': '성공',
 '01085258088': '성공',
 '01085821517': '상생',
 '01085931652': '성공',
 '01085970060': '룰랄',
 '01088407989': 'BM',
 '01088569679': '성공',
 '01088592005': '상생',
 '01088657389': '룰랄',
 '01088861539': '서구',
 '01089558851': '상생',
 '01089567995': '성공',
 '01089568216': '서구',
 '01090025476': '서구',
 '01090651819': '성공',
 '01093183405': '서구',
 '01093312498': '서구',
 '01094509952': '상생',
 '01094649471': '서구',
 '01095211379': '성공',
 '01095272748': '상생',
 '01095337575': '서구',
 '01095414565': '성공',
 '01095500590': 'BM',
 '01096092776': '성공',
 '01096911017': '서구',
 '01097538209': '성공',
 '01097622002': '서구',
 '01097792669': '서구',
 '01098366557': 'BM',
 '01098841599': '상생',
 '01098899533': '성공',
 '01099546312': 'BM',
 '01099994011': '상생'},
        "static_team_map_userid": {'01046515916': '서구',
 '01074790008': '성공',
 '11111': '서구',
 '3299yu3299': '상생',
 '50075936ekyi': '상생',
 '71332776': '서구',
 'Asd2259': '서구',
 'B4469011': '상생',
 'BC165211': '성공',
 'BC533812': '서구',
 'BC862346': '성공',
 'Dawon51': '성공',
 'Good9679': '성공',
 'Himemay184': '상생',
 'Jongman6189': 'BM',
 'Kk6021': '성공',
 'Kocomdg': '룰랄',
 'SOSSOSO90378': 'BM',
 'Tack0957': '성공',
 'aa35002074': '성공',
 'aa7096': '상생',
 'aaaqqqwww111': '성공',
 'aasdds': '상생',
 'abollo1': '상생',
 'akroto10': '룰랄',
 'alsghd33': '서구',
 'alstn100494': '상생',
 'alswo10042': 'BM',
 'andel1212': '상생',
 'apple123z': '상생',
 'aqeda': '서구',
 'aswq666': '서구',
 'azxs0790': 'BM',
 'bc720742': '서구',
 'beatsuya': '성공',
 'beforidie': '성공',
 'biomedics': 'BM',
 'bjw0316': '상생',
 'bjw3602': '서구',
 'bluesens': '성공',
 'bogus2498': '서구',
 'boull1004': '서구',
 'cana8294': '성공',
 'cat3434': '상생',
 'ccm7577': 'BM',
 'chang89': '서구',
 'cho0677': '성공',
 'choigo32': '상생',
 'ckdnd456': '성공',
 'cksqls1209': 'BM',
 'coolnjc': '성공',
 'cs8925': '성공',
 'csyyys': '서구',
 'csyyyys': '서구',
 'cthanhqb': '서구',
 'cxz3131': 'BM',
 'dahanda7': '서구',
 'ddim5004': '상생',
 'dhkdrkdnl02': '서구',
 'dhkrtm5': '상생',
 'dlwnry1': '성공',
 'dnjs817': '서구',
 'duddk6022': '서구',
 'eddie6577': '룰랄',
 'eksfk711': '룰랄',
 'eotkd93': '서구',
 'family4989': '상생',
 'fbtmdcks31': '성공',
 'fiat4408': 'BM',
 'fkdnrtjd': '상생',
 'fks024': 'BM',
 'freehug4610': 'BM',
 'ghost9566': '성공',
 'gidrml12': '서구',
 'goskm': '성공',
 'gpzldaos3': '서구',
 'gundal780721': 'BM',
 'halada011': '서구',
 'hjjphd': '상생',
 'honga1388': '성공',
 'hoya104': 'BM',
 'hra0318': '성공',
 'hsk796': '상생',
 'hwan4': '성공',
 'hwangjoil': '서구',
 'hyunjin2058': '서구',
 'imss119': '성공',
 'j1030jhs': '서구',
 'jang2535': '상생',
 'jhj845100': '상생',
 'jj199968': '성공',
 'jjj3357': '상생',
 'jjk9526': '상생',
 'jkss1730': '성공',
 'jun2817': 'BM',
 'junhan0202': '성공',
 'jym1148': '성공',
 'jyt1452': '룰랄',
 'k7811305': '서구',
 'kcc518551': '서구',
 'kdkd88': '상생',
 'key055': 'BM',
 'kimli0109': '상생',
 'kolon77': 'BM',
 'koohip': '성공',
 'kooja79': '성공',
 'kor226': 'BM',
 'korea6587': '상생',
 'kslove1269': 'BM',
 'kts822300': '룰랄',
 'kw06068': '서구',
 'lee1hahaha': '상생',
 'lee9361': '성공',
 'luxury8707': '상생',
 'mamigirl1004': 'BM',
 'mkoq80': '상생',
 'mudark623': 'BM',
 'mystop1214': 'BM',
 'nabin92': '성공',
 'nalove0721': 'BM',
 'namh0801': '서구',
 'natoaegis': '상생',
 'nice1250': '성공',
 'nike1101': '서구',
 'nnhs6670': '성공',
 'onna2776': '서구',
 'opop0323': '성공',
 'oppyn': '성공',
 'opsf1': '성공',
 'parkhot4409': '상생',
 'pcs1803': '성공',
 'pluskim': '상생',
 'popiop123': '상생',
 'promisel': '성공',
 'pyh9443': '서구',
 'qkrtkddlf': '성공',
 'qnfehr1237': '서구',
 'qoqudgh456': 'BM',
 'qqaazz120000': '성공',
 'r78789': 'BM',
 'raits2': '서구',
 'riuxioknu': '서구',
 'rkcl1234': '서구',
 'rlaeogh112233': '서구',
 'rlfma2': '룰랄',
 'rmatja1214': '서구',
 'rnjs9639': '성공',
 'sa003114': 'BM',
 'sadf8122': 'BM',
 'saz1212': '성공',
 'screenstar': '성공',
 'seg1703': '성공',
 'seoseo0314': 'BM',
 'sgsjsk': 'BM',
 'shin84': '성공',
 'sign222': '성공',
 'sksmsk22': '서구',
 'snns432': '룰랄',
 'snskwks': '서구',
 'sok1038': '서구',
 'ss10500': '서구',
 'ssogi1': '상생',
 'ssssb95': '성공',
 'stp21': '성공',
 'subinzzang9': '성공',
 'take6344': '성공',
 'tbr947': 'BM',
 'tg4ever': '성공',
 'tg5858': '상생',
 'tgb4ever': '성공',
 'tgs4ever': '성공',
 'thdwodyd': 'BM',
 'tjdgkr1370': '서구',
 'tjdgns9856': '성공',
 'tk770322': '서구',
 'tkddyd778': '룰랄',
 'tksxkdhwna99': '상생',
 'tmddyd9714': '상생',
 'utmost07': '상생',
 'whgmlcks': '상생',
 'wizzzzz2491': '서구',
 'wjdgus9887': '상생',
 'wjsrudrn': '성공',
 'wjswls201': 'BM',
 'wnsqud5643': 'BM',
 'wnsrldihy': '상생',
 'wogks3115': '룰랄',
 'wogus9043': '서구',
 'wowgma2': '상생',
 'wprb44': '성공',
 'xkdlass0245': '상생',
 'xkxl67': 'BM',
 'youjoon0407': '룰랄',
 'yousy1128': '룰랄',
 'ysh2776': '성공',
 'zet707': '상생',
 'zezx20': '성공',
 'zwzwzwz': '성공',
 'zx0921': '서구',
 'zzzsss5': '서구'},
        "static_conflict_names": {'김경수': ['BM', '성공'], '김정훈': ['상생', '성공'], '이창원': ['BM', '상생']},
    },
    {
        "area": "달서B",
        "slug": "dalseob_onna",
        "aliases": [
            "대구달서B온나(DP2602028125)",
            "대구달서B온나 (DP2602028125)",
            "대구달서B온나",
            "DP2602028125",
        ],
        "center_code": "DP2602028125",
        "team_order": ["슈", "넘", "마", "미분류"],
        "area_config": {
            "슈": 3,
            "넘": 5.5,
            "마": 4.5,
            "미분류": 0,
        },
        "team_map_path": "/settings/dalseob_onna/teamMap",
        "team_map_phone_path": "/settings/dalseob_onna/teamMapPhone",
        "team_map_userid_path": "/settings/dalseob_onna/teamMapUserId",
        "live_path": "/live/dalseob_onna",
        "weekly_path": "/weekly/dalseob_onna",
        "required_team_riders": {},
        "static_team_map": {'권휘재': '슈',
 '김경섭': '슈',
 '김도묵': '슈',
 '김동규': '슈',
 '김보성': '슈',
 '김재현': '슈',
 '김정호': '슈',
 '김종기': '슈',
 '김종찬': '슈',
 '김주동': '슈',
 '김현석': '슈',
 '노우현': '슈',
 '박무성': '슈',
 '박성우': '슈',
 '박정민': '슈',
 '배재현': '슈',
 '배준호': '슈',
 '송특근': '슈',
 '신진학': '슈',
 '심재득': '슈',
 '엄정철': '슈',
 '유영엽': '슈',
 '윤규범': '슈',
 '윤영훈': '슈',
 '윤창현': '슈',
 '이부관': '슈',
 '이재관': '슈',
 '이재상': '슈',
 '이정민': '슈',
 '이종필': '슈',
 '이혜진': '슈',
 '장근영': '슈',
 '장재근': '슈',
 '정규태': '슈',
 '정기정': '슈',
 '정우혁': '슈',
 '조승래': '슈',
 '조윤환': '슈',
 '최경민': '슈',
 '최지나': '슈',
 '최현준': '슈',
 '한주환': '슈',
 '강지우': '마',
 '곽봉수': '마',
 '구상훈': '마',
 '구용태': '마',
 '권영남': '마',
 '길태빈': '마',
 '김낙훈': '마',
 '김대환': '마',
 '김도형': '마',
 '김동욱': '마',
 '김동현': '마',
 '김서현': '마',
 '김석원': '마',
 '김숙자': '마',
 '김영우': '마',
 '김인수': '마',
 '김임식': '마',
 '김재훈': '마',
 '김지성': '마',
 '김창범': '마',
 '김형택': '마',
 '김효겸': '마',
 '김희경': '마',
 '노경진': '마',
 '노지훈': '마',
 '도수현': '마',
 '명제규': '마',
 '문성호': '마',
 '문영신': '마',
 '문용덕': '마',
 '박광용': '마',
 '박성립': '마',
 '박원희': '마',
 '박지홍': '마',
 '박한울': '마',
 '박호일': '마',
 '박효건': '마',
 '백창열': '마',
 '서봉용': '마',
 '석진국': '마',
 '소귀숙': '마',
 '손성곤': '마',
 '송인섭': '마',
 '신가희': '마',
 '신원준': '마',
 '신인호': '마',
 '신정학': '마',
 '안호식': '마',
 '여세동': '마',
 '위석훈': '마',
 '윤동근': '마',
 '윤정원': '마',
 '이강현': '마',
 '이건수': '마',
 '이경태': '마',
 '이승준': '마',
 '이영민': '마',
 '이재현': '마',
 '이전필': '마',
 '이진승': '마',
 '이진욱': '마',
 '임인재': '마',
 '임재백': '마',
 '임종헌': '마',
 '임지원': '마',
 '임지훈': '마',
 '장대웅': '마',
 '장민규': '마',
 '장예환': '마',
 '전대명': '마',
 '전승옥': '마',
 '전하경': '마',
 '전현': '마',
 '정동수': '마',
 '정동진': '마',
 '차무길': '마',
 '차성원': '마',
 '최영우': '마',
 '최종현': '마',
 '최진욱': '마',
 '피우덕': '마',
 '피우정': '마',
 '하태수': '마',
 '한희숙': '마',
 '강명원': '넘',
 '강지은': '넘',
 '권오현': '넘',
 '김대운': '넘',
 '김동국': '넘',
 '김명한': '넘',
 '김병수': '넘',
 '김수진': '넘',
 '김애선': '넘',
 '김영천': '넘',
 '김요한': '넘',
 '김용운': '넘',
 '김정근': '넘',
 '김종희': '넘',
 '김지은': '넘',
 '김태하': '넘',
 '김한수': '넘',
 '김현준': '넘',
 '김혜민': '넘',
 '남동욱': '넘',
 '남승호': '넘',
 '남윤정': '넘',
 '노재권': '넘',
 '도인환': '넘',
 '마경민': '넘',
 '박기석': '넘',
 '박민우': '넘',
 '박세창': '넘',
 '박영식': '넘',
 '배동식': '넘',
 '배서후': '넘',
 '배정열': '넘',
 '서강원': '넘',
 '서영태': '넘',
 '신명섭': '넘',
 '우효상': '넘',
 '유호성': '넘',
 '윤민석': '넘',
 '이대겸': '넘',
 '이동석': '넘',
 '이동혁': '넘',
 '이선노': '넘',
 '이영희': '넘',
 '이윤재': '넘',
 '이은성': '넘',
 '이재헌': '넘',
 '이주호': '넘',
 '이철우': '넘',
 '이태훈': '넘',
 '이헌재': '넘',
 '임승범': '넘',
 '임현석': '넘',
 '장정석': '넘',
 '정수영': '넘',
 '조영웅': '넘',
 '천재원': '넘',
 '최영진': '넘',
 '최윤호': '넘',
 '한동훈': '넘',
 '황홍섭': '넘'},
        "static_team_map_phone": {'01093075450': '슈',
 '01044887604': '슈',
 '01021312227': '슈',
 '01071166009': '슈',
 '01062535620': '슈',
 '01076976964': '슈',
 '01031138989': '슈',
 '01037032226': '슈',
 '01059583950': '슈',
 '01077884324': '슈',
 '01057358625': '슈',
 '01074477485': '슈',
 '01054988784': '슈',
 '01026943061': '슈',
 '01040079796': '슈',
 '01088848776': '슈',
 '01039689408': '슈',
 '01087958240': '슈',
 '01025312180': '슈',
 '01077389311': '슈',
 '01058595537': '슈',
 '01032858005': '슈',
 '01084835024': '슈',
 '01059653950': '슈',
 '01021097444': '슈',
 '01064536684': '슈',
 '01085602100': '슈',
 '01041524052': '슈',
 '01043881274': '슈',
 '01084783537': '슈',
 '01023925248': '슈',
 '01046750207': '슈',
 '01079797638': '슈',
 '01028911235': '슈',
 '01031318326': '슈',
 '01062420150': '슈',
 '01095703626': '슈',
 '01055050090': '슈',
 '01076891799': '슈',
 '01072837586': '슈',
 '01033811118': '슈',
 '01089985200': '슈',
 '01081452662': '마',
 '01034035666': '마',
 '01029715979': '마',
 '01088802220': '마',
 '01084310366': '마',
 '01046370533': '마',
 '01091358666': '마',
 '01039060637': '마',
 '01064164141': '마',
 '01041364623': '마',
 '01021759295': '마',
 '01094371746': '마',
 '01081722116': '마',
 '01081386301': '마',
 '01059413830': '마',
 '01079059775': '마',
 '01082017104': '마',
 '01035527722': '마',
 '01085633555': '마',
 '01067017578': '마',
 '01066580060': '마',
 '01049662369': '마',
 '01082548759': '마',
 '01021981360': '마',
 '01098026123': '마',
 '01021149959': '마',
 '01076461411': '마',
 '01023693778': '마',
 '01026262651': '마',
 '01073722699': '마',
 '01095523207': '마',
 '01048681804': '마',
 '01093634891': '마',
 '01020198386': '마',
 '01033193330': '마',
 '01080545557': '마',
 '01085855590': '마',
 '01075132883': '마',
 '01050117788': '마',
 '01021558489': '마',
 '01099999314': '마',
 '01028352581': '마',
 '01067181119': '마',
 '01059165869': '마',
 '01047936948': '마',
 '01049913477': '마',
 '01044251191': '마',
 '01050495151': '마',
 '01088029986': '마',
 '01080290148': '마',
 '01099224911': '마',
 '01089407675': '마',
 '01059489929': '마',
 '01030529302': '마',
 '01097656696': '마',
 '01049485656': '마',
 '01062423200': '마',
 '01044247889': '마',
 '01025878487': '마',
 '01051617970': '마',
 '01058368764': '마',
 '01096303978': '마',
 '01088650664': '마',
 '01025600756': '마',
 '01055558519': '마',
 '01076976853': '마',
 '01021558386': '마',
 '01099503910': '마',
 '01059546206': '마',
 '01094432934': '마',
 '01027326644': '마',
 '01049556667': '마',
 '01020043698': '마',
 '01071282322': '마',
 '01044442048': '마',
 '01099443778': '마',
 '01058348961': '마',
 '01095414782': '마',
 '01044945744': '마',
 '01064526236': '마',
 '01068162229': '마',
 '01094949564': '마',
 '01095543509': '마',
 '01068716671': '마',
 '01058787714': '넘',
 '01022992074': '넘',
 '01088539693': '넘',
 '01089281913': '넘',
 '01038604005': '넘',
 '01053174896': '넘',
 '01048388533': '넘',
 '01030578074': '넘',
 '01085861501': '넘',
 '01035231200': '넘',
 '01071088375': '넘',
 '01058417569': '넘',
 '01059544501': '넘',
 '01048064883': '넘',
 '01054273601': '넘',
 '01066705551': '넘',
 '01066721758': '넘',
 '01084583660': '넘',
 '01064854283': '넘',
 '01041891535': '넘',
 '01056504943': '넘',
 '01095896718': '넘',
 '01027653338': '넘',
 '01053324399': '넘',
 '01080711085': '넘',
 '01044492194': '넘',
 '01083926818': '넘',
 '01038029569': '넘',
 '01049991979': '넘',
 '01066690833': '넘',
 '01054043777': '넘',
 '01096535597': '넘',
 '01097287484': '넘',
 '01044448699': '넘',
 '01029640378': '넘',
 '01049828882': '넘',
 '01081779214': '넘',
 '01033653988': '넘',
 '01064650252': '넘',
 '01034304869': '넘',
 '01058869507': '넘',
 '01044614442': '넘',
 '01084453270': '넘',
 '01021147732': '넘',
 '01084159157': '넘',
 '01079804033': '넘',
 '01098599955': '넘',
 '01090687818': '넘',
 '01055732053': '넘',
 '01056560857': '넘',
 '01036055133': '넘',
 '01095757800': '넘',
 '01097503660': '넘',
 '01039004014': '넘',
 '01033537644': '넘',
 '01083177376': '넘',
 '01084717983': '넘',
 '01039106527': '넘'},
        "static_team_map_userid": {'gnlwo1066': '슈',
 'qwert7397': '슈',
 'next3000': '슈',
 '1119kdk': '슈',
 'sung6253': '슈',
 'ssjj12': '슈',
 'new3188': '슈',
 'bs6602': '슈',
 'chanor7444': '슈',
 'rlawnehd12': '슈',
 'stay77': '슈',
 'a74477485': '슈',
 'parkms12': '슈',
 'star007c': '슈',
 'pjm830514': '슈',
 'wogus2747': '슈',
 'tlfnql11': '슈',
 'ch1538': '슈',
 'jh2180': '슈',
 'zz2750': '슈',
 'qwe1236': '슈',
 'usj7410': '슈',
 'sisisi5024': '슈',
 'chris1882': '슈',
 'h7444': '슈',
 'boss6684': '슈',
 'icismul': '슈',
 'qaws2001': '슈',
 'ljml1004': '슈',
 'plpo1118': '슈',
 'lhj1050': '슈',
 'gy890525': '슈',
 'sni233': '슈',
 'conan45': '슈',
 'jkj3412': '슈',
 'juh0150': '슈',
 'j95703626': '슈',
 'cyh1817': '슈',
 'che85741': '슈',
 'goqkfkrl1595': '슈',
 'plpo111818': '슈',
 'gkswnghks496': '슈',
 'buk11129': '마',
 'qw1637': '마',
 'gagaga10': '마',
 'yy2146': '마',
 'wardin0424': '마',
 'gtb0310': '마',
 'power3190': '마',
 'kdh8702': '마',
 'doshin0000': '마',
 'hero2000a': '마',
 'donghyun2325': '마',
 'shaftksh80': '마',
 'yoyo2519': '마',
 'kim1302': '마',
 'dwc10304': '마',
 'BC97751': '마',
 '820111': '마',
 'kjsnam': '마',
 'odxk12': '마',
 'ksots99': '마',
 'kknd0406': '마',
 'kimkutak49r6': '마',
 'ngj437901': '마',
 'njh7296': '마',
 'dsh6908': '마',
 'wprb44': '마',
 'jok454': '마',
 'oppa2465': '마',
 'shin84': '마',
 'wwopww1': '마',
 '1041224242': '마',
 'ab1643': '마',
 '1093634891': '마',
 'wardin86': '마',
 'pikhoil': '마',
 'pkskqq': '마',
 'jieum1010': '마',
 'aquineus1974': '마',
 'sign111': '마',
 'jwss8489': '마',
 'gon1052': '마',
 'youcuwaru': '마',
 'sook0219': '마',
 'cave0708': '마',
 'inhoshin': '마',
 'ealran2': '마',
 'an1191': '마',
 'jj5151': '마',
 'stv77': '마',
 'ehdrms12312': '마',
 'Minhlong0109': '마',
 'wake7675': '마',
 'leegunsu': '마',
 '30522': '마',
 'lee71047217': '마',
 'youngmin852': '마',
 'pp1073pp': '마',
 'trzkiss': '마',
 'zerius08': '마',
 'jw4404': '마',
 'injae7082': '마',
 'sexking': '마',
 '1088650664': '마',
 'ddw02003': '마',
 'mppm1': '마',
 'ddww0408': '마',
 'wkd123455': '마',
 'BC391011': '마',
 'skaa1999': '마',
 'teras': '마',
 'jhk7791': '마',
 'jh9132': '마',
 'nnjdsnn': '마',
 'J2322': '마',
 'gil2048': '마',
 'ggttooii': '마',
 'duddndla51': '마',
 'cjhcjh1': '마',
 'kittyou': '마',
 'kk1685515': '마',
 'pee8156': '마',
 'pwjg25': '마',
 'ts2037': '마',
 'gallardo007': '마',
 'kmo7714': '넘',
 'gaga651210': '넘',
 'koh4016': '넘',
 'daewoon83': '넘',
 'eldrnek2002': '넘',
 'kmh8767': '넘',
 'raven03': '넘',
 'ksj3975': '넘',
 'ksun0213': '넘',
 'manbok0023': '넘',
 'yohan810': '넘',
 'abc2137': '넘',
 'maxturn': '넘',
 'koseela': '넘',
 'kth1234': '넘',
 'a5551': '넘',
 'kimhj1983': '넘',
 'minwoong0306': '넘',
 'nkazya4283': '넘',
 'jabara123': '넘',
 'nyj661011': '넘',
 'nja4577': '넘',
 'sega22': '넘',
 'akrudals': '넘',
 'gs940407': '넘',
 'gooming': '넘',
 'xkxk1121': '넘',
 'duud4532': '넘',
 '1049991979': '넘',
 'qotjgn1313': '넘',
 'bae1102': '넘',
 'rkddnjs589': '넘',
 'pado8575': '넘',
 'bvhgy': '넘',
 'This0378': '넘',
 'yniii7777': '넘',
 'mine9101': '넘',
 'leedg3832': '넘',
 'eww2356': '넘',
 'zzkk3430': '넘',
 'daehanc': '넘',
 'wwwf13': '넘',
 'dbswo1': '넘',
 'qwaskong': '넘',
 'luckyboy0808': '넘',
 'BC403344': '넘',
 'lte820717': '넘',
 'Hunjae79': '넘',
 'tmdqja1234': '넘',
 'limhsda': '넘',
 'shuang5133': '넘',
 '5667257a': '넘',
 'dytpq85': '넘',
 'metalangelic': '넘',
 'kim701208': '넘',
 'Ykkoo': '넘',
 'kkolk': '넘',
 'skyhhs2001': '넘'},
        "static_conflict_names": {},
    },
]

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


def effective_weekday(date_value):
    """Special Day가 지정된 날짜는 실제 요일 대신 지정 요일 기준을 사용합니다."""
    if hasattr(date_value, "strftime"):
        key = date_value.strftime("%Y-%m-%d")
    else:
        key = str(date_value)
    if key in SPECIAL_DAY_TARGET_WEEKDAY:
        return int(SPECIAL_DAY_TARGET_WEEKDAY[key])
    return date_value.weekday()


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
    weekend = effective_weekday(date_value) >= 5

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
    weekend = effective_weekday(business_date(now)) >= 5

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



def team_of(name, phone=None, user_id=None):
    global TEAM_MAP_CACHE, TEAM_MAP_PHONE_CACHE, TEAM_MAP_USERID_CACHE

    clean_name = norm(name)
    phone_key = normalize_phone(phone)
    clean_user_id = norm(user_id)

    if TEAM_MAP_CACHE is None:
        try:
            init_firebase()
            TEAM_MAP_CACHE = db.reference(TEAM_MAP_PATH).get() or {}
            TEAM_MAP_PHONE_CACHE = db.reference(TEAM_MAP_PHONE_PATH).get() or {}
            TEAM_MAP_USERID_CACHE = db.reference(TEAM_MAP_USERID_PATH).get() or {}

            TEAM_MAP_CACHE = {norm(k): norm(v) for k, v in TEAM_MAP_CACHE.items()}
            TEAM_MAP_PHONE_CACHE = {
                normalize_phone(k): norm(v) for k, v in TEAM_MAP_PHONE_CACHE.items()
            }
            TEAM_MAP_USERID_CACHE = {
                norm(k): norm(v) for k, v in TEAM_MAP_USERID_CACHE.items()
            }
            print(
                f"teamMap 로드 완료: 이름 {len(TEAM_MAP_CACHE)}명 / "
                f"전화 {len(TEAM_MAP_PHONE_CACHE)}명 / "
                f"ID {len(TEAM_MAP_USERID_CACHE)}명"
            )
        except Exception as exc:
            print("teamMap 로드 실패:", exc)
            TEAM_MAP_CACHE = {}
            TEAM_MAP_PHONE_CACHE = {}
            TEAM_MAP_USERID_CACHE = {}

    mapped = None

    # 관제 화면에서 직접 저장한 설정을 우선합니다.
    if phone_key:
        mapped = TEAM_MAP_PHONE_CACHE.get(phone_key)
    if mapped not in TEAM_ORDER and clean_user_id:
        mapped = TEAM_MAP_USERID_CACHE.get(clean_user_id)
    if mapped not in TEAM_ORDER:
        mapped = TEAM_MAP_CACHE.get(clean_name)
    if mapped in TEAM_ORDER:
        return mapped

    # 업로드된 엑셀 명단을 파일 내부에 포함한 고정 매핑입니다.
    if phone_key:
        mapped = STATIC_TEAM_MAP_PHONE.get(phone_key)
    if mapped not in TEAM_ORDER and clean_user_id:
        mapped = STATIC_TEAM_MAP_USERID.get(clean_user_id)
    if mapped not in TEAM_ORDER and clean_name not in STATIC_TEAM_MAP_CONFLICT_NAMES:
        mapped = STATIC_TEAM_MAP.get(clean_name)
    if mapped in TEAM_ORDER:
        return mapped

    return "미분류"

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
        let statusCell = nearestCell(
          row,
          identityHeaders.status,
          c => /운행\s*(중|종료)/.test(c.text.replace(/\s+/g,'')),
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
    """오늘 권역 전체 및 팀별 실적을 weekly 파일에 즉시 갱신합니다.

    같은 businessDate는 최신값으로 덮어쓰고, 다른 날짜는 계속 보존합니다.
    저장 후 파일을 다시 읽어 해당 날짜가 실제 기록됐는지 검증합니다.
    """
    config = config or {
        "area": AREA_NAME,
        "slug": CURRENT_SLUG,
        "team_order": TEAM_ORDER,
    }

    weekly = load_weekly()
    if not isinstance(weekly, list):
        weekly = []

    today_key = str(data["businessDate"])
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

        "total": dict(data["total"]),
        "teams": team_rows,
    }

    # businessDate 기준으로 무조건 오늘 값을 최신값으로 교체
    by_date = {}
    for item in weekly:
        if isinstance(item, dict) and item.get("businessDate"):
            by_date[str(item["businessDate"])] = item
    by_date[today_key] = row

    weekly = [by_date[k] for k in sorted(by_date.keys())][-730:]

    # 중간에 프로세스가 끊겨도 기존 파일이 깨지지 않도록 임시파일 -> replace
    tmp_file = WEEKLY_FILE.with_suffix(WEEKLY_FILE.suffix + ".tmp")
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(weekly, f, ensure_ascii=False, indent=2)
        f.flush()
    tmp_file.replace(WEEKLY_FILE)

    # 저장 검증
    verify = load_weekly()
    saved = next(
        (x for x in verify if isinstance(x, dict) and str(x.get("businessDate")) == today_key),
        None
    )
    if not saved:
        raise RuntimeError(f"주간기록 저장 검증 실패: {WEEKLY_FILE.name} / {today_key}")

    if int(saved.get("totalComplete", -1)) != int(data["total"]["complete"]):
        raise RuntimeError(
            f"주간기록 값 검증 실패: {today_key} "
            f"saved={saved.get('totalComplete')} current={data['total']['complete']}"
        )

    print(
        f"주간기록 저장 확인: {WEEKLY_FILE.name} / {today_key} / "
        f"완료 {saved.get('totalComplete', 0)} / 팀 {len(saved.get('teams') or {})}개"
    )
    return weekly


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
        "areas": ["중구A", "달서B"],
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

        # 업로드 직후 Firebase weekly 경로를 직접 읽어 오늘 기록이 존재하는지 확인합니다.
        init_firebase()
        remote_weekly = db.reference(config["weekly_path"]).get()
        if not isinstance(remote_weekly, list):
            # Firebase 배열이 dict 형태로 반환되는 경우도 허용
            if isinstance(remote_weekly, dict):
                remote_weekly = [v for _, v in sorted(remote_weekly.items(), key=lambda x: str(x[0]))]
            else:
                remote_weekly = []

        today_key = str(data.get("businessDate", ""))
        remote_today = next(
            (x for x in remote_weekly if isinstance(x, dict) and str(x.get("businessDate")) == today_key),
            None
        )

        if not remote_today:
            # upload_json 결과가 반영되지 않은 경우 직접 set으로 복구
            with open(expected_weekly_file, "r", encoding="utf-8") as f:
                local_weekly = json.load(f)
            db.reference(config["weekly_path"]).set(local_weekly)
            remote_weekly = db.reference(config["weekly_path"]).get() or []
            if isinstance(remote_weekly, dict):
                remote_weekly = [v for _, v in sorted(remote_weekly.items(), key=lambda x: str(x[0]))]
            remote_today = next(
                (x for x in remote_weekly if isinstance(x, dict) and str(x.get("businessDate")) == today_key),
                None
            )

        if not remote_today:
            raise RuntimeError(
                f"Firebase 주간기록 검증 실패: {config['weekly_path']} / {today_key}"
            )

        print(f"Firebase 업로드 완료: {config['live_path']} ← {expected_data_file.name}")
        print(
            f"Firebase 주간기록 확인: {config['weekly_path']} / "
            f"{today_key} / 완료 {remote_today.get('totalComplete', 0)}"
        )
    except Exception:
        print("Firebase 업로드/주간기록 검증 실패")
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

    riders = collect_all_pages_by_dom(page)
    if len(riders) == 0:
        raise RuntimeError("기사 데이터를 못 읽었습니다.")

    data = make_data(riders, config)

    # 수집 직후부터 권역값을 검증하여 다른 권역 덮어쓰기를 차단합니다.
    if data.get("area") != config["area"] or data.get("slug") != config["slug"]:
        raise RuntimeError(
            f"수집 권역 불일치: {data.get('area')}/{data.get('slug')} "
            f"!= {config['area']}/{config['slug']}"
        )

    weekly = save_weekly_if_close(data, config)
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
    global AREA_NAME, TEAM_ORDER, AREA_CONFIG
    global TEAM_MAP_PATH, TEAM_MAP_PHONE_PATH, TEAM_MAP_USERID_PATH
    global LIVE_PATH, WEEKLY_PATH, CURRENT_SLUG, DATA_FILE, WEEKLY_FILE
    global REQUIRED_TEAM_RIDERS
    global TEAM_MAP_CACHE, TEAM_MAP_PHONE_CACHE, TEAM_MAP_USERID_CACHE
    global STATIC_TEAM_MAP, STATIC_TEAM_MAP_PHONE
    global STATIC_TEAM_MAP_USERID, STATIC_TEAM_MAP_CONFLICT_NAMES
    global VERIFIED_CENTER_CODE

    VERIFIED_CENTER_CODE = None
    AREA_NAME = config["area"]
    CURRENT_SLUG = config["slug"]
    TEAM_ORDER = list(config["team_order"])
    AREA_CONFIG = {AREA_NAME: dict(config["area_config"])}

    TEAM_MAP_PATH = config["team_map_path"]
    TEAM_MAP_PHONE_PATH = config["team_map_phone_path"]
    TEAM_MAP_USERID_PATH = config["team_map_userid_path"]

    LIVE_PATH = config["live_path"]
    WEEKLY_PATH = config["weekly_path"]
    REQUIRED_TEAM_RIDERS = dict(config.get("required_team_riders") or {})

    STATIC_TEAM_MAP = dict(config.get("static_team_map") or {})
    STATIC_TEAM_MAP_PHONE = dict(config.get("static_team_map_phone") or {})
    STATIC_TEAM_MAP_USERID = dict(config.get("static_team_map_userid") or {})
    STATIC_TEAM_MAP_CONFLICT_NAMES = dict(config.get("static_conflict_names") or {})

    DATA_FILE = BASE_DIR / f"data_{CURRENT_SLUG}.json"
    WEEKLY_FILE = BASE_DIR / f"weekly_{CURRENT_SLUG}.json"

    TEAM_MAP_CACHE = None
    TEAM_MAP_PHONE_CACHE = None
    TEAM_MAP_USERID_CACHE = None

    print(
        f"권역 활성화: {AREA_NAME} / {CURRENT_SLUG} / "
        f"팀={TEAM_ORDER} / Firebase={LIVE_PATH}"
    )

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
    print("VIC 성공드림 중구A + 달서B 통합 DOM 자동 수집기 - 화면 밖 백그라운드 모드")
    print("대상 권역:", ", ".join(c["area"] for c in CENTER_CONFIGS))
    print("Chrome 프로필:", BASE_DIR / "chrome_profile_vic")

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(BASE_DIR / "chrome_profile_vic"),
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

        print("1. 열린 배민비즈 창에서 성공드림 계정으로 로그인하세요.")
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
                print(f"{REFRESH_SECONDS}초 후 다시 중구A부터 수집합니다.")
                time.sleep(REFRESH_SECONDS)
        finally:
            try:
                browser.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
