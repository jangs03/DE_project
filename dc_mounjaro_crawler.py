"""
디시인사이드 마운자로 마이너갤러리 크롤러
https://gall.dcinside.com/mgallery/board/lists/?id=mounjaro

✅ 50개 게시글마다 CSV 중간 저장 (크롤링 중단 시 데이터 보존)
✅ 이미 수집된 글은 건너뛰기 (이어서 크롤링 가능)

사용법:
    pip install requests beautifulsoup4 pandas
    python dc_mounjaro_crawler.py
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import os
from datetime import datetime

# ============================================================
# 설정
# ============================================================
GALLERY_ID = "mounjaro"
GALLERY_TYPE = "mgallery"  # 마이너갤러리
BASE_URL = f"https://gall.dcinside.com/{GALLERY_TYPE}/board/lists/"

START_PAGE = 1
END_PAGE = 1600  # 원하는 만큼 늘리세요

DELAY = 5  # 요청 사이 대기 시간(초)

# 특정 키워드가 포함된 글만 수집하려면 여기에 추가
# 예: ["후기", "부작용", "효과"]
KEYWORD_FILTER = []

# 중간 저장 단위 (게시글 N개마다 CSV 저장)
SAVE_EVERY = 50

# 출력 파일
OUTPUT_CSV = "mounjaro_posts.csv"

# ============================================================
# 헤더 설정
# ============================================================
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://gall.dcinside.com/",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

COLUMNS = ["번호", "제목", "작성자", "날짜", "조회수", "추천수", "댓글수", "본문", "이미지수", "링크"]


# ============================================================
# 이미 수집된 글 번호 로드 (이어서 크롤링용)
# ============================================================
def load_existing_post_nums() -> set:
    """기존 CSV에서 이미 수집된 글 번호를 불러옵니다."""
    if not os.path.exists(OUTPUT_CSV):
        return set()
    try:
        df = pd.read_csv(OUTPUT_CSV, encoding="utf-8-sig", usecols=["번호"])
        existing = set(df["번호"].tolist())
        print(f"📂 기존 CSV에서 {len(existing)}개 글 번호 로드 완료 (중복 건너뜀)\n")
        return existing
    except Exception:
        return set()


# ============================================================
# CSV 저장 (append 모드)
# ============================================================
def save_to_csv(posts: list[dict], is_first_write: bool):
    """게시글 리스트를 CSV에 저장합니다. 첫 저장이면 헤더 포함."""
    if not posts:
        return

    df = pd.DataFrame(posts)
    df = df[[c for c in COLUMNS if c in df.columns]]

    if is_first_write:
        df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig", mode="w")
    else:
        df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig", mode="a", header=False)

    print(f"\n💾 중간 저장 완료 — {len(posts)}개 추가 → {OUTPUT_CSV}")


# ============================================================
# 게시판 목록 파싱
# ============================================================
def get_post_list(page: int) -> list[dict]:
    """한 페이지의 게시글 목록을 파싱합니다."""
    params = {"id": GALLERY_ID, "page": page}

    try:
        resp = SESSION.get(BASE_URL, params=params, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[ERROR] 페이지 {page} 요청 실패: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    rows = soup.select("tr.ub-content.us-post")

    posts = []
    for row in rows:
        try:
            num_el = row.select_one("td.gall_num")
            post_num = num_el.get_text(strip=True) if num_el else ""
            if not post_num.isdigit():
                continue

            title_el = row.select_one("td.gall_tit a")
            title = title_el.get_text(strip=True) if title_el else ""
            link = title_el["href"] if title_el and title_el.has_attr("href") else ""

            reply_el = row.select_one("td.gall_tit a.reply_numbox span")
            reply_count = reply_el.get_text(strip=True).strip("[]") if reply_el else "0"

            writer_el = row.select_one("td.gall_writer")
            writer = ""
            if writer_el:
                nick_el = writer_el.select_one("span.nickname, em")
                writer = nick_el.get_text(strip=True) if nick_el else writer_el.get_text(strip=True)

            date_el = row.select_one("td.gall_date")
            date_str = date_el.get("title", date_el.get_text(strip=True)) if date_el else ""

            count_el = row.select_one("td.gall_count")
            view_count = count_el.get_text(strip=True) if count_el else "0"

            recommend_el = row.select_one("td.gall_recommend")
            recommend = recommend_el.get_text(strip=True) if recommend_el else "0"

            post = {
                "번호": int(post_num),
                "제목": title,
                "댓글수": reply_count,
                "작성자": writer,
                "날짜": date_str,
                "조회수": view_count,
                "추천수": recommend,
                "링크": f"https://gall.dcinside.com{link}" if link.startswith("/") else link,
            }

            if KEYWORD_FILTER:
                if not any(kw in title for kw in KEYWORD_FILTER):
                    continue

            posts.append(post)

        except Exception as e:
            print(f"[WARN] 행 파싱 오류: {e}")
            continue

    return posts


# ============================================================
# 개별 글 본문 수집
# ============================================================
def get_post_content(url: str) -> dict:
    """개별 게시글의 본문 텍스트와 이미지 수를 가져옵니다."""
    try:
        resp = SESSION.get(url, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[ERROR] 본문 요청 실패: {url} — {e}")
        return {"본문": "", "이미지수": 0}

    soup = BeautifulSoup(resp.text, "html.parser")

    content_el = soup.select_one("div.write_div")
    if content_el:
        for tag in content_el.select("script, style, iframe"):
            tag.decompose()
        body_text = content_el.get_text(separator="\n", strip=True)
    else:
        body_text = ""

    images = content_el.select("img") if content_el else []
    img_count = len(images)

    return {"본문": body_text, "이미지수": img_count}


# ============================================================
# 메인 크롤링 루프 — 50개마다 중간 저장
# ============================================================
def crawl():
    print(f"{'='*60}")
    print(f"  디시인사이드 마운자로 갤러리 크롤러")
    print(f"  페이지 범위: {START_PAGE} ~ {END_PAGE}")
    print(f"  중간 저장 단위: {SAVE_EVERY}개마다")
    print(f"  키워드 필터: {KEYWORD_FILTER if KEYWORD_FILTER else '없음 (전체 수집)'}")
    print(f"{'='*60}\n")

    # 기존 수집분 로드 (이어서 크롤링)
    existing_nums = load_existing_post_nums()
    is_first_write = len(existing_nums) == 0

    buffer = []          # 중간 저장용 버퍼
    total_saved = 0      # 이번 실행에서 저장된 총 개수
    total_skipped = 0    # 중복으로 건너뛴 개수

    try:
        for page in range(START_PAGE, END_PAGE + 1):
            print(f"[목록] 페이지 {page}/{END_PAGE} 수집 중...")
            posts = get_post_list(page)
            print(f"       → {len(posts)}개 게시글 발견")
            time.sleep(DELAY)

            for post in posts:
                # 이미 수집된 글이면 건너뛰기
                if post["번호"] in existing_nums:
                    total_skipped += 1
                    continue

                # 본문 수집
                print(f"  📝 [{total_saved + len(buffer) + 1}] {post['제목'][:45]}...")
                content_data = get_post_content(post["링크"])
                post.update(content_data)
                time.sleep(DELAY)

                buffer.append(post)
                existing_nums.add(post["번호"])

                # 버퍼가 SAVE_EVERY에 도달하면 CSV에 저장
                if len(buffer) >= SAVE_EVERY:
                    save_to_csv(buffer, is_first_write)
                    total_saved += len(buffer)
                    is_first_write = False
                    buffer = []
                    print(f"  ✅ 누적 저장: {total_saved}개 | 건너뜀: {total_skipped}개\n")

    except KeyboardInterrupt:
        print(f"\n\n⚠️  사용자 중단 (Ctrl+C) — 버퍼에 남은 {len(buffer)}개 저장 중...")

    # 남은 버퍼 저장
    if buffer:
        save_to_csv(buffer, is_first_write)
        total_saved += len(buffer)

    # 최종 요약
    print(f"\n{'='*60}")
    print(f"  크롤링 완료!")
    print(f"{'='*60}")
    print(f"  신규 수집: {total_saved}개")
    print(f"  중복 건너뜀: {total_skipped}개")
    print(f"  저장 파일: {OUTPUT_CSV}")

    if os.path.exists(OUTPUT_CSV):
        df = pd.read_csv(OUTPUT_CSV, encoding="utf-8-sig")
        print(f"  CSV 총 행 수: {len(df)}개")
        if "날짜" in df.columns and len(df) > 0:
            print(f"  기간: {df['날짜'].min()} ~ {df['날짜'].max()}")
        if "본문" in df.columns and len(df) > 0:
            avg_len = df["본문"].str.len().mean()
            print(f"  평균 본문 길이: {avg_len:.0f}자")

    print(f"{'='*60}\n")


# ============================================================
# 실행
# ============================================================
if __name__ == "__main__":
    crawl()
