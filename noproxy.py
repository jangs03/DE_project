"""
디시인사이드 마운자로 갤러리 크롤러 (프록시 없음, 직접 연결)

✅ 저병렬 순차 수집 (차단 방지)
✅ User-Agent 로테이션
✅ 요청 간 2~5초 랜덤 대기
✅ 50개마다 CSV + MongoDB 저장
✅ 실시간 모니터링 모드 (--monitor)
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import pandas as pd
import time
import os
import random
import argparse
from datetime import datetime
from pymongo import MongoClient, UpdateOne
from pymongo.errors import ConnectionFailure, BulkWriteError

# ============================================================
# 설정
# ============================================================
GALLERY_ID = "mounjaro"
GALLERY_TYPE = "mgallery"
BASE_URL = f"https://gall.dcinside.com/{GALLERY_TYPE}/board/lists/?id={GALLERY_ID}"

START_PAGE = 1
END_PAGE = 1900

# 🔽 프록시 없이 쓸 때는 낮춰야 합니다
CONCURRENCY = 4             # 동시 요청 수 (2~3 권장)
REQUEST_DELAY_MIN = 2.0     # 최소 대기 시간 (초)
REQUEST_DELAY_MAX = 4.0     # 최대 대기 시간 (초)

SAVE_EVERY = 50
OUTPUT_CSV = "mounjaro_posts.csv"

MAX_RETRIES = 3
RETRY_DELAY = 5
BLOCK_COOLDOWN = 60         # 429/차단 감지 시 대기 시간 (초)
MONITOR_INTERVAL = 1800

# ============================================================
# User-Agent 로테이션
# ============================================================
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36 Edg/117.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36 OPR/102.0.0.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
]


def get_random_ua() -> str:
    return random.choice(USER_AGENTS)


# ============================================================
# MongoDB 설정
# ============================================================
MONGO_URI = (

)
MONGO_DB = "DEproject"
MONGO_COLLECTION = "dc_test"

COLUMNS = ["번호", "제목", "작성자", "날짜", "조회수", "추천수", "댓글수", "본문", "이미지수", "링크"]


# ============================================================
# MongoDB
# ============================================================
def connect_mongo():
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
        client.admin.command("ping")
        db = client[MONGO_DB]
        collection = db[MONGO_COLLECTION]
        collection.create_index("번호", unique=True)
        print(f"✅ MongoDB 연결 성공 — {MONGO_DB}.{MONGO_COLLECTION}")
        return collection
    except ConnectionFailure as e:
        print(f"❌ MongoDB 연결 실패: {e}")
        return None


def upload_to_mongo(collection, posts):
    if collection is None or not posts:
        return
    operations = []
    for post in posts:
        doc = post.copy()
        doc["수집일시"] = datetime.now().isoformat()
        doc["갤러리"] = GALLERY_ID
        doc["출처"] = "dcinside"
        operations.append(UpdateOne({"번호": doc["번호"]}, {"$set": doc}, upsert=True))
    try:
        result = collection.bulk_write(operations, ordered=False)
        print(f"  🗄️  MongoDB — 신규: {result.upserted_count}개 | 업데이트: {result.modified_count}개")
    except BulkWriteError as e:
        print(f"  ⚠️  MongoDB 일부 오류: {e.details.get('writeErrors', [])[:3]}")
    except Exception as e:
        print(f"  ❌ MongoDB 업로드 실패: {e}")


def load_existing_nums(collection) -> set:
    nums = set()
    if os.path.exists(OUTPUT_CSV):
        try:
            df = pd.read_csv(OUTPUT_CSV, encoding="utf-8-sig", usecols=["번호"])
            nums.update(df["번호"].tolist())
            print(f"📂 CSV에서 {len(nums)}개 글 번호 로드")
        except Exception:
            pass
    if collection is not None:
        try:
            cursor = collection.find({}, {"번호": 1, "_id": 0})
            db_nums = {doc["번호"] for doc in cursor}
            nums.update(db_nums)
            if db_nums:
                print(f"📂 MongoDB에서 {len(db_nums)}개 글 번호 로드")
        except Exception:
            pass
    return nums


def save_to_csv(posts, is_first_write):
    if not posts:
        return
    df = pd.DataFrame(posts)
    df = df[[c for c in COLUMNS if c in df.columns]]
    if is_first_write:
        df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig", mode="w")
    else:
        df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig", mode="a", header=False)
    print(f"\n💾 CSV 저장 — {len(posts)}개 추가 → {OUTPUT_CSV}")


# ============================================================
# GET 요청 (프록시 없이, 직접 연결)
# ============================================================
async def fetch_url(session, target_url, retries=MAX_RETRIES):
    headers_base = {
        "Referer": "https://gall.dcinside.com",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
    }

    for attempt in range(retries):
        headers = {**headers_base, "User-Agent": get_random_ua()}

        try:
            async with session.get(
                target_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    return await resp.text()
                elif resp.status == 404:
                    return None
                elif resp.status == 429:
                    # 속도 제한 — 긴 대기
                    wait = BLOCK_COOLDOWN + random.uniform(5, 15)
                    print(f"  [429] 속도 제한 — {wait:.0f}초 대기...")
                    await asyncio.sleep(wait)
                elif resp.status in (403, 503):
                    # 차단 감지 — 더 긴 대기
                    wait = BLOCK_COOLDOWN * 2 + random.uniform(10, 30)
                    print(f"  [{resp.status}] 차단 감지 — {wait:.0f}초 대기...")
                    await asyncio.sleep(wait)
                else:
                    if attempt < retries - 1:
                        await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                    else:
                        print(f"  ⚠️  HTTP {resp.status} — {target_url[-60:]}")
                        return None
        except asyncio.TimeoutError:
            if attempt < retries - 1:
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))
            else:
                print(f"  ❌ 타임아웃 — {target_url[-60:]}")
                return None
        except aiohttp.ClientError as e:
            if attempt < retries - 1:
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))
            else:
                print(f"  ❌ 요청 실패: {type(e).__name__}")
                return None
    return None


# ============================================================
# 1단계: 목록 페이지에서 게시글 정보 추출
# ============================================================
async def get_post_list(session, page: int) -> list[dict]:
    url = f"{BASE_URL}&page={page}"
    html = await fetch_url(session, url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
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

            full_link = f"https://gall.dcinside.com{link}" if link.startswith("/") else link

            posts.append({
                "번호": int(post_num),
                "제목": title,
                "댓글수": reply_count,
                "작성자": writer,
                "날짜": date_str,
                "조회수": view_count,
                "추천수": recommend,
                "링크": full_link,
            })
        except Exception:
            continue

    return posts


# ============================================================
# 2단계: 개별 글 본문 수집
# ============================================================
async def get_post_content(session, url: str) -> dict:
    html = await fetch_url(session, url)
    if not html:
        return {"본문": "", "이미지수": 0}

    soup = BeautifulSoup(html, "html.parser")
    content_el = soup.select_one("div.write_div")
    if content_el:
        for tag in content_el.select("script, style, iframe"):
            tag.decompose()
        body_text = content_el.get_text(separator="\n", strip=True)
        img_count = len(content_el.select("img"))
    else:
        body_text = ""
        img_count = 0

    return {"본문": body_text, "이미지수": img_count}


# ============================================================
# 목록 페이지 병렬 수집 (저병렬 + 긴 대기)
# ============================================================
async def fetch_lists_batch(session, pages, semaphore):
    async def fetch_one_page(page):
        async with semaphore:
            await asyncio.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))
            return page, await get_post_list(session, page)
    tasks = [fetch_one_page(p) for p in pages]
    results = await asyncio.gather(*tasks)
    results.sort(key=lambda x: x[0])
    return results


# ============================================================
# 본문 병렬 수집 (저병렬 + 긴 대기)
# ============================================================
async def fetch_contents_batch(session, posts, semaphore):
    async def fetch_one(post):
        async with semaphore:
            await asyncio.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))
            content = await get_post_content(session, post["링크"])
            post.update(content)
            return post
    tasks = [fetch_one(post) for post in posts]
    completed = []
    total = len(tasks)
    for idx, task in enumerate(asyncio.as_completed(tasks), start=1):
        completed.append(await task)
        if idx % 10 == 0 or idx == total:
            print(f"    ... 본문 진행 {idx}/{total}")
    return completed


# ============================================================
# 메인 크롤링
# ============================================================
async def crawl():
    print(f"{'='*60}")
    print(f"  디시인사이드 마운자로 갤러리 크롤러 (프록시 없음)")
    print(f"  페이지 범위: {START_PAGE} ~ {END_PAGE}")
    print(f"  동시 요청: {CONCURRENCY}개 | 요청 간격: {REQUEST_DELAY_MIN}~{REQUEST_DELAY_MAX}초")
    print(f"{'='*60}\n")

    collection = connect_mongo()
    existing_nums = load_existing_nums(collection)
    is_first_write = not os.path.exists(OUTPUT_CSV)

    if existing_nums:
        print(f"📊 기존 {len(existing_nums)}개 글 (건너뜀)\n")

    buffer = []
    total_saved = 0
    total_skipped = 0
    empty_count = 0
    semaphore = asyncio.Semaphore(CONCURRENCY)

    # 직접 연결 — SSL 검증 유지
    connector = aiohttp.TCPConnector(limit=CONCURRENCY * 2)

    # 목록 페이지를 5개씩 묶어서 처리 (원본 10 → 5로 축소)
    LIST_BATCH = 5

    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            for batch_start in range(START_PAGE, END_PAGE + 1, LIST_BATCH):
                batch_end = min(batch_start + LIST_BATCH - 1, END_PAGE)
                pages = list(range(batch_start, batch_end + 1))

                print(f"[목록] 페이지 {batch_start}~{batch_end} 수집 중...")
                start_time = time.time()

                page_results = await fetch_lists_batch(session, pages, semaphore)

                all_new_posts = []
                for page_num, posts in page_results:
                    for post in posts:
                        if post["번호"] in existing_nums:
                            total_skipped += 1
                        else:
                            all_new_posts.append(post)
                            existing_nums.add(post["번호"])

                if not all_new_posts:
                    empty_count += 1
                    elapsed = time.time() - start_time
                    print(f"       → 신규 0개 (건너뜀 {total_skipped}개) [{elapsed:.1f}초]")
                    if empty_count >= 3:
                        print("       → 연속 3회 빈 결과 — 크롤링 종료")
                        break
                    continue

                empty_count = 0

                print(f"  📝 본문 {len(all_new_posts)}개 수집 중...")
                await fetch_contents_batch(session, all_new_posts, semaphore)

                buffer.extend(all_new_posts)
                elapsed = time.time() - start_time
                print(f"       → {len(all_new_posts)}개 수집 완료 [{elapsed:.1f}초]")

                while len(buffer) >= SAVE_EVERY:
                    batch_to_save = buffer[:SAVE_EVERY]
                    buffer = buffer[SAVE_EVERY:]
                    save_to_csv(batch_to_save, is_first_write)
                    upload_to_mongo(collection, batch_to_save)
                    total_saved += len(batch_to_save)
                    is_first_write = False
                    print(f"  ✅ 누적: {total_saved}개 | 건너뜀 {total_skipped}개\n")

        except KeyboardInterrupt:
            print(f"\n\n⚠️  사용자 중단 — 버퍼에 남은 {len(buffer)}개 저장 중...")

    if buffer:
        save_to_csv(buffer, is_first_write)
        upload_to_mongo(collection, buffer)
        total_saved += len(buffer)

    print(f"\n{'='*60}")
    print(f"  크롤링 완료!")
    print(f"{'='*60}")
    print(f"  수집 성공: {total_saved}개")
    print(f"  기존 건너뜀: {total_skipped}개")
    if os.path.exists(OUTPUT_CSV):
        df = pd.read_csv(OUTPUT_CSV, encoding="utf-8-sig")
        print(f"  CSV 총 행 수: {len(df)}개")
    if collection is not None:
        doc_count = collection.count_documents({})
        print(f"  MongoDB 총 문서 수: {doc_count}개")
    print(f"{'='*60}\n")


# ============================================================
# 실시간 모니터링
# ============================================================
async def monitor(interval: int):
    print(f"{'='*60}")
    print(f"  디시인사이드 마운자로 갤러리 실시간 모니터링 (프록시 없음)")
    print(f"  확인 주기: {interval}초 ({interval//60}분)")
    print(f"  종료: Ctrl+C")
    print(f"{'='*60}\n")

    collection = connect_mongo()
    existing_nums = load_existing_nums(collection)
    is_first_write = not os.path.exists(OUTPUT_CSV)

    cycle_count = 0
    total_new = 0
    semaphore = asyncio.Semaphore(CONCURRENCY)

    try:
        while True:
            cycle_count += 1
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"{'─'*40}")
            print(f"🔄 [{now}] 모니터링 #{cycle_count}")

            connector = aiohttp.TCPConnector(limit=CONCURRENCY * 2)
            async with aiohttp.ClientSession(connector=connector) as session:
                page_results = await fetch_lists_batch(session, [1, 2, 3], semaphore)

                new_posts = []
                for page_num, posts in page_results:
                    for post in posts:
                        if post["번호"] not in existing_nums:
                            new_posts.append(post)
                            existing_nums.add(post["번호"])

                if new_posts:
                    print(f"  🆕 새 글 {len(new_posts)}개 발견! 본문 수집 중...")
                    await fetch_contents_batch(session, new_posts, semaphore)

                    save_to_csv(new_posts, is_first_write)
                    upload_to_mongo(collection, new_posts)
                    is_first_write = False
                    total_new += len(new_posts)

                    for post in new_posts:
                        print(f"    📝 [{post['번호']}] {post['제목'][:50]}")
                else:
                    print(f"  — 새 글 없음")

            print(f"  📊 누적 신규: {total_new}개 | 추적 중: {len(existing_nums)}개")
            print(f"  ⏳ {interval}초 후 재확인...\n")
            await asyncio.sleep(interval)

    except KeyboardInterrupt:
        print(f"\n\n⚠️  모니터링 종료")
        print(f"  총 {cycle_count}회 확인 | 신규 수집: {total_new}개")


# ============================================================
# 실행
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="디시인사이드 마운자로 갤러리 크롤러")
    parser.add_argument("--monitor", action="store_true", help="실시간 모니터링 모드")
    parser.add_argument("--interval", type=int, default=MONITOR_INTERVAL, help="모니터링 주기 (초, 기본 1800)")
    args = parser.parse_args()

    if args.monitor:
        asyncio.run(monitor(args.interval))
    else:
        asyncio.run(crawl())
