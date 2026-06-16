import subprocess
import time
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent

COLLECTORS = [
    "d_a.py",
    "d_b.py",
    "c_a.py",
    "m_a.py",
    "s_c.py",
]

processes = {}

def start_collector(filename):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 시작: {filename}")

    p = subprocess.Popen(
        ["cmd", "/k", "python", filename],
        cwd=BASE_DIR,
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )

    processes[filename] = p

def main():
    print("SUPERSONIC 통합 수집기 매니저 시작")

    for filename in COLLECTORS:
        start_collector(filename)
        time.sleep(5)

    print("전체 수집기 실행 완료")
    print("각 창에서 로그인/권역 이동 후 Enter 누르세요.")

    while True:
        time.sleep(60)

if __name__ == "__main__":
    main()
