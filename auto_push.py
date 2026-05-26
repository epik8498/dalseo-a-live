import subprocess
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent

while True:
    try:
        print("=" * 40)
        print("AUTO PUSH START")

        subprocess.run(["git", "add", "."], cwd=BASE_DIR)

        commit = subprocess.run(
            ["git", "commit", "-m", "auto push"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True
        )

        print(commit.stdout)
        print(commit.stderr)

        subprocess.run(["git", "push"], cwd=BASE_DIR)

        print("PUSH COMPLETE")
    except Exception as e:
        print("ERROR:", e)

    print("120초 후 재시도")
    time.sleep(120)
