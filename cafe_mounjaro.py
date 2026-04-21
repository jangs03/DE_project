"""
네이버 카페 크롤러 (내부 API 활용)
대상: https://cafe.naver.com/f-e/cafes/19965504/menus/0

API: https://apis.naver.com/cafe-web/cafe-boardlist-api/v1/cafes/{cafeId}/menus/{menuId}/articles
총 게시글: 약 42,768개

✅ 네이버 카페 내부 API 사용 (Selenium 불필요)
✅ 50개마다 CSV 중간 저장 + MongoDB 업로드
✅ 이어서 크롤링 가능 (중복 건너뜀)

사전 준비:
    1. 크롬에서 네이버 로그인 → 해당 카페 접속
    2. F12 → Network → 아무 요청 클릭 → Request Headers에서 Cookie 값 복사
    3. 아래 COOKIE 변수에 붙여넣기

사용법:
    pip install requests beautifulsoup4 pandas pymongo
    python naver_cafe_crawler.py
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import json
import os
from datetime import datetime
from pymongo import MongoClient, UpdateOne
from pymongo.errors import ConnectionFailure, BulkWriteError

# ============================================================
# 설정
# ============================================================
CLUB_ID = 19965504          # 카페 ID
MENU_ID = 0                 # 0 = 전체글, 특정 게시판이면 해당 menuId
PAGE_SIZE = 50              # 한 페이지당 게시글 수 (최대 50)
START_PAGE = 1
END_PAGE = 900              # 42768개 / 50개 ≈ 856페이지

DELAY = 1.0                 # 요청 간 대기(초)
SAVE_EVERY = 50             # N개마다 CSV + DB 저장
OUTPUT_CSV = "naver_cafe_posts.csv"

# ============================================================
# 🔑 쿠키 설정 (필수!)
# ============================================================
COOKIE = "NAC=82dcBABYccci; NNB=4HNMVDOAF7BWS; page_uid=jNFoKsqo0qnkYRJzD8s-232360; _fbp=fb.1.1774849742584.757614044777659430; JSESSIONID=A13007BD7802FAA2A559BB8306A6E133; cto_bundle=pyDiUV9UVEVmY1pzR0FOQWJYJTJGNGdYaXJITURWJTJCRUU0SEFIamZEaGcyJTJCZkUzVHVCSjAwRUwlMkZrd3pZY2RUZ0NlQk9vbiUyRnIzbk00eEdUc1JQbzhIbVI3ckoza08wUmx6cHR6Z1g0V3h3TVlMVzRFSzFEWGdnOFNxTVBUUnZLeTRUampCRHVJJTJGUjBpdzB0YjNVemZuOXVMMVk0cnclM0QlM0Q; SRT30=1776771458; NACT=1; SRT5=1776772623; nid_inf=1182553410; NID_AUT=w5Z/dUSwHmG8pvSbGV/mZufZkdJtfAMhFY6Knyh0h+MKKw1FBTnNd8JHGRzL0Wxb; NID_SES=AAABgMb+I8SamxFkFz8tcSe8h68+5WuIxIsu1GlKuNKqhTZW6pjO9w7DbHWLQl3vm/KA2aM2Uvh0wjxj9WWVU+fVXBdllkSIBSpUZe0ElRLVUSTeVjsIP76wPdMWqHfkHd0yllHFkmiZ+a/WfjAJnok1DKMEwoxJtBP2+5sXq5yPhHgrXiTy+x6JNsLi+GHLYc1O/VW16ysgZRXdFxH7qIPvoKZFzCyWBIfG1OOYSt193SMLFyiB24j05Pz3j8ePwVUVTmeu8YxsWzBPz/4XCkYX3PZJLejgcpkvxdwfhKPIKOyiJsr734TMqHbOFGkKpb4EPBDtPcj0oGch8BFYnrVxJiL+cV1ngZrI5b/204VsVUzoDGd0HZr7WKfOsL8ijdMoBGRaD45mXQZqUTwrjRIgLYIg3hHGvIp7/ZptuNK1oy3bycbHHIZ0+e3CDPGD6QCBcRJnN57nUq4D/tTd647ErZ8x8TlU1aWZG/m7cUuoZCX5FkOeF2CFzFdJ3rYlqlv0cg==; BUC=8h8cUcHncMgeNBJ8ie6y6Xpo7pBFDKw5p8uex1Jgpu0="

# ============================================================
# MongoDB 설정
# ============================================================
MONGO_URI = (
    "mongodb+srv://DEproject1:sksmsskawo123!"
    "@nje-cluster.mongocluster.cosmos.azure.com/"
    "?tls=true&authMechanism=SCRAM-SHA-256"
    "&retrywrites=false&maxIdleTimeMS=120000"
)
MONGO_DB = "DEproject"
MONGO_COLLECTION = "naver_cafe"

# ============================================================
# API 엔드포인트
# ============================================================
LIST_API = f"https://apis.naver.com/cafe-web/cafe-boardlist-api/v1/cafes/{CLUB_ID}/menus/{MENU_ID}/articles"
ARTICLE_API = f"https://apis.naver.com/cafe-web/cafe-articleapi/v2.1/cafes/{CLUB_ID}/articles"

# ============================================================
# HTTP 헤더
# ============================================================
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": f"https://cafe.naver.com/f-e/cafes/{CLUB_ID}/menus/{MENU_ID}",
    "Cookie": COOKIE,
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

COLUMNS = [
    "글번호", "제목", "작성자", "날짜", "조회수", "댓글수",
    "좋아요수", "게시판명", "본문", "링크"
]


# ============================================================
# 쿠키 유효성 체크
# ============================================================
def check_cookie():
    if "여기에" in COOKIE or len(COOKIE) < 50:
        print("❌ 쿠키가 설정되지 않았습니다!")
        print()
        print("   [쿠키 가져오는 방법]")
        print("   1. 크롬에서 네이버 로그인 후 해당 카페 접속")
        print("   2. F12 → Network 탭 → Fetch/XHR 필터")
        print("   3. 페이지 새로고침 (F5)")
        print("   4. 아무 요청 클릭 → Request Headers → Cookie 값 전체 복사")
        print("   5. 이 스크립트의 COOKIE 변수에 붙여넣기")
        print()
        return False
    return True


# ============================================================
# MongoDB 연결
# ============================================================
def connect_mongo():
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
        client.admin.command("ping")
        db = client[MONGO_DB]
        collection = db[MONGO_COLLECTION]
        collection.create_index("글번호", unique=True)
        print(f"✅ MongoDB 연결 성공 — {MONGO_DB}.{MONGO_COLLECTION}")
        return collection
    except ConnectionFailure as e:
        print(f"❌ MongoDB 연결 실패: {e}")
        print("   → CSV 저장만 진행합니다.\n")
        return None


def upload_to_mongo(collection, posts: list[dict]):
    if collection is None or not posts:
        return
    operations = []
    for post in posts:
        doc = post.copy()
        doc["수집일시"] = datetime.now().isoformat()
        doc["카페ID"] = CLUB_ID
        doc["출처"] = "naver_cafe"
        operations.append(
            UpdateOne({"글번호": doc["글번호"]}, {"$set": doc}, upsert=True)
        )
    try:
        result = collection.bulk_write(operations, ordered=False)
        print(f"  🗄️  MongoDB — 신규: {result.upserted_count}개 | 업데이트: {result.modified_count}개")
    except BulkWriteError as e:
        print(f"  ⚠️  MongoDB 일부 오류: {e.details.get('writeErrors', [])[:3]}")
    except Exception as e:
        print(f"  ❌ MongoDB 업로드 실패: {e}")


# ============================================================
# 기존 수집분 로드
# ============================================================
def load_existing_nums(collection) -> set:
    nums = set()
    if os.path.exists(OUTPUT_CSV):
        try:
            df = pd.read_csv(OUTPUT_CSV, encoding="utf-8-sig", usecols=["글번호"])
            nums.update(df["글번호"].tolist())
            print(f"📂 CSV에서 {len(nums)}개 글 번호 로드")
        except Exception:
            pass
    if collection is not None:
        try:
            cursor = collection.find({}, {"글번호": 1, "_id": 0})
            db_nums = {doc["글번호"] for doc in cursor}
            nums.update(db_nums)
            if db_nums:
                print(f"📂 MongoDB에서 {len(db_nums)}개 글 번호 로드")
        except Exception:
            pass
    return nums


def save_to_csv(posts: list[dict], is_first_write: bool):
    if not posts:
        return
    df = pd.DataFrame(posts)
    df = df[[c for c in COLUMNS if c in df.columns]]
    if is_first_write:
        df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig", mode="w")
    else:
        df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig", mode="a", header=False)
    print(f"\n💾 CSV 저장 완료 — {len(posts)}개 추가 → {OUTPUT_CSV}")


# ============================================================
# 게시글 목록 수집
# ============================================================
def get_article_list(page: int) -> list[dict]:
    """
    실제 API: /cafe-boardlist-api/v1/cafes/{cafeId}/menus/{menuId}/articles
    응답 구조: result.articleList[].item
    """
    params = {
        "page": page,
        "pageSize": PAGE_SIZE,
        "sortBy": "TIME",
        "viewType": "L",
    }

    try:
        resp = SESSION.get(LIST_API, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"[ERROR] 목록 API 실패 (페이지 {page}): {e}")
        return []
    except json.JSONDecodeError:
        print(f"[ERROR] JSON 파싱 실패 (페이지 {page}) — 쿠키 만료 가능성")
        return []

    article_list = data.get("result", {}).get("articleList", [])

    posts = []
    for entry in article_list:
        item = entry.get("item", entry)  # item 안에 실제 데이터

        # 작성자 정보
        writer_info = item.get("writerInfo", {})
        nickname = writer_info.get("nickName", "")

        # 날짜 변환 (타임스탬프 → 읽기 쉬운 형태)
        timestamp = item.get("writeDateTimestamp", 0)
        if timestamp:
            date_str = datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d %H:%M:%S")
        else:
            date_str = ""

        article_id = item.get("articleId", 0)

        post = {
            "글번호": article_id,
            "제목": item.get("subject", ""),
            "작성자": nickname,
            "날짜": date_str,
            "조회수": item.get("readCount", 0),
            "댓글수": item.get("commentCount", 0),
            "좋아요수": item.get("likeCount", 0),
            "게시판명": item.get("menuName", ""),
            "링크": f"https://cafe.naver.com/ca-fe/cafes/{CLUB_ID}/articles/{article_id}",
        }
        posts.append(post)

    return posts


# ============================================================
# 개별 글 본문 수집
# ============================================================
def get_article_content(article_id: int) -> str:
    url = f"{ARTICLE_API}/{article_id}"
    params = {"useCafeId": "true"}

    try:
        resp = SESSION.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"    [WARN] 본문 실패 (글 {article_id}): {e}")
        return ""
    except json.JSONDecodeError:
        return ""

    content_html = (
        data.get("result", {})
            .get("article", {})
            .get("contentHtml", "")
    )
    if not content_html:
        content_html = (
            data.get("result", {})
                .get("article", {})
                .get("content", "")
        )

    if content_html:
        soup = BeautifulSoup(content_html, "html.parser")
        return soup.get_text(separator="\n", strip=True)

    return ""


# ============================================================
# 메인 크롤링 루프
# ============================================================
def crawl():
    print(f"{'='*60}")
    print(f"  네이버 카페 크롤러 (내부 API)")
    print(f"  카페 ID: {CLUB_ID}")
    print(f"  메뉴 ID: {MENU_ID} {'(전체글)' if MENU_ID == 0 else ''}")
    print(f"  페이지 범위: {START_PAGE} ~ {END_PAGE}")
    print(f"  페이지당: {PAGE_SIZE}개 | 중간 저장: {SAVE_EVERY}개마다")
    print(f"{'='*60}\n")

    if not check_cookie():
        return

    collection = connect_mongo()
    existing_nums = load_existing_nums(collection)
    is_first_write = not os.path.exists(OUTPUT_CSV)

    if existing_nums:
        print(f"📊 총 {len(existing_nums)}개 기존 글 (중복 건너뜀)\n")

    buffer = []
    total_saved = 0
    total_skipped = 0
    empty_count = 0  # 연속 빈 페이지 카운터

    try:
        for page in range(START_PAGE, END_PAGE + 1):
            print(f"[목록] 페이지 {page}/{END_PAGE} 수집 중...")
            posts = get_article_list(page)

            if not posts:
                empty_count += 1
                print(f"       → 게시글 없음 (연속 {empty_count}회)")
                if empty_count >= 3:
                    print("       → 연속 3회 빈 페이지 — 크롤링 종료")
                    break
                time.sleep(DELAY)
                continue

            empty_count = 0
            print(f"       → {len(posts)}개 게시글 발견")
            time.sleep(DELAY)

            for post in posts:
                if post["글번호"] in existing_nums:
                    total_skipped += 1
                    continue

                print(f"  📝 [{total_saved + len(buffer) + 1}] {post['제목'][:45]}...")
                body = get_article_content(post["글번호"])
                post["본문"] = body
                time.sleep(DELAY)

                buffer.append(post)
                existing_nums.add(post["글번호"])

                if len(buffer) >= SAVE_EVERY:
                    save_to_csv(buffer, is_first_write)
                    upload_to_mongo(collection, buffer)
                    total_saved += len(buffer)
                    is_first_write = False
                    buffer = []
                    print(f"  ✅ 누적: CSV {total_saved}개 | 건너뜀 {total_skipped}개\n")

    except KeyboardInterrupt:
        print(f"\n\n⚠️  사용자 중단 — 버퍼에 남은 {len(buffer)}개 저장 중...")

    if buffer:
        save_to_csv(buffer, is_first_write)
        upload_to_mongo(collection, buffer)
        total_saved += len(buffer)

    print(f"\n{'='*60}")
    print(f"  크롤링 완료!")
    print(f"{'='*60}")
    print(f"  CSV 신규 저장: {total_saved}개")
    print(f"  중복 건너뜀: {total_skipped}개")
    print(f"  CSV 파일: {OUTPUT_CSV}")

    if os.path.exists(OUTPUT_CSV):
        df = pd.read_csv(OUTPUT_CSV, encoding="utf-8-sig")
        print(f"  CSV 총 행 수: {len(df)}개")

    if collection is not None:
        doc_count = collection.count_documents({})
        print(f"  MongoDB 총 문서 수: {doc_count}개")

    print(f"{'='*60}\n")


# ============================================================
# API 테스트
# ============================================================
def test_api():
    """API 연결 테스트. 실행: python -c "from naver_cafe_crawler import test_api; test_api()" """
    print("🔍 API 연결 테스트 중...\n")

    if not check_cookie():
        return

    # 테스트 1: 목록 API
    print("[테스트 1] 게시글 목록 API")
    posts = get_article_list(1)
    if posts:
        print(f"  ✅ 성공 — {len(posts)}개 게시글")
        print(f"  예시: [{posts[0]['게시판명']}] {posts[0]['제목'][:50]}")
        print(f"  작성자: {posts[0]['작성자']} | 날짜: {posts[0]['날짜']}")
        print(f"  조회: {posts[0]['조회수']} | 댓글: {posts[0]['댓글수']}")
    else:
        print("  ❌ 실패 — 쿠키를 다시 확인해 주세요")
        return

    # 테스트 2: 본문 API
    if posts:
        print(f"\n[테스트 2] 본문 API (글번호: {posts[0]['글번호']})")
        body = get_article_content(posts[0]["글번호"])
        if body:
            print(f"  ✅ 성공 — 본문 길이: {len(body)}자")
            print(f"  미리보기: {body[:100]}...")
        else:
            print("  ⚠️  본문 비어있음 — 비공개 글이거나 본문 API 확인 필요")

    print("\n✅ 테스트 완료!")


if __name__ == "__main__":
    crawl()
