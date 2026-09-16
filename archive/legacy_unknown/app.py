import streamlit as st
import pandas as pd
from playwright.sync_api import sync_playwright
import time

st.set_page_config(page_title="달서A 실시간 실적", layout="wide")

st.title("달서A 실시간 실적 자동 집계")

DALSEO_A_RIDERS = [
    "김병철",
    "김경오",
    "김덕근",
    # 여기에 달서A 기사명 추가
]

st.info("버튼을 누르면 배민비즈 창이 열립니다. 로그인 후 기사 실적 페이지까지 이동하세요.")

if st.button("배민비즈 열고 전체 집계 시작"):
    with st.spinner("브라우저를 여는 중입니다..."):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page()

            page.goto("https://deliverycenter.baemin.com")

            st.warning("배민비즈 로그인 후 기사 실적 페이지까지 이동하세요.")
            st.warning("이동이 끝나면 이 화면으로 돌아와서 아래 안내를 기다리세요.")

            input("로그인 후 기사 실적 페이지까지 이동했으면 CMD 창에서 Enter를 누르세요...")

            all_rows = []

            while True:
                time.sleep(1)

                rows = page.locator("table tbody tr").all()

                for row in rows:
                    cells = row.locator("td").all_inner_texts()

                    if len(cells) < 6:
                        continue

                    name = cells[0].strip()

                    if name not in DALSEO_A_RIDERS:
                        continue

                    try:
                        complete = int(cells[3].replace(",", "").strip() or 0)
                        reject = int(cells[4].replace(",", "").strip() or 0)
                        cancel = int(cells[5].replace(",", "").strip() or 0)
                    except:
                        complete = 0
                        reject = 0
                        cancel = 0

                    all_rows.append({
                        "기사명": name,
                        "상태": cells[1].strip(),
                        "휴대폰": cells[2].strip(),
                        "완료": complete,
                        "거절": reject,
                        "배차취소": cancel,
                    })

                next_buttons = page.locator("button:has-text('>')")

                if next_buttons.count() == 0:
                    break

                next_button = next_buttons.last()

                if not next_button.is_enabled():
                    break

                next_button.click()
                time.sleep(1)

            browser.close()

    df = pd.DataFrame(all_rows)

    if df.empty:
        st.warning("달서A 기사 데이터가 없습니다. 기사명단을 추가하거나 페이지 위치를 확인하세요.")
        st.stop()

    df = df.drop_duplicates(subset=["기사명"], keep="first")

    col1, col2, col3 = st.columns(3)
    col1.metric("달서A 총 완료", int(df["완료"].sum()))
    col2.metric("총 거절", int(df["거절"].sum()))
    col3.metric("총 배차취소", int(df["배차취소"].sum()))

    st.subheader("달서A 기사별 실적")
    st.dataframe(df.sort_values("완료", ascending=False), use_container_width=True)
