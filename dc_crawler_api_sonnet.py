"""
디시인사이드 마운자로 갤러리 크롤러 (페이지 기준 + Web Unlocker API)

✅ 페이지 목록에서 존재하는 글만 추출 → 본문 수집 (비용 절약)
✅ BrightData Web Unlocker API로 IP 차단 완전 우회
✅ 동시 20개 비동기 병렬 요청
✅ 50개마다 CSV + MongoDB 저장
✅ 실시간 모니터링 모드 (--monitor)

사용법:
    pip install aiohttp beautifulsoup4 pandas pymongo

    python dc_mounjaro_crawler.py                          # 전체 수집
    python dc_mounjaro_crawler.py --monitor                # 30분마다 모니터링
    python dc_mounjaro_crawler.py --monitor --interval 600 # 10분마다 모니터링
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import pandas as pd
import time
import os
import ssl
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

CONCURRENCY = 20
SAVE_EVERY = 50
OUTPUT_CSV = "mounjaro_posts.csv"

MAX_RETRIES = 3
RETRY_DELAY = 3
MONITOR_INTERVAL = 1800

# ============================================================
# API Key 체크
# ============================================================
def check_api_key():
    if "여기에" in BD_API_KEY or len(BD_API_KEY) < 10:
        print("❌ BrightData API Key가 설정되지 않았습니다!")
        print("   BD_API_KEY 변수에 API Key를 붙여넣으세요.")
        return False
    return True


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
# BrightData Web Unlocker API 요청 (비동기)
# ============================================================
async def fetch_via_unlocker(session, target_url, retries=MAX_RETRIES):
    for attempt in range(retries):
        try:
            async with session.post(
                BD_API_URL,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {BD_API_KEY}",
                },
                json={
                    "zone": BD_ZONE,
                    "url": target_url,
                    "format": "raw",
                },
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status == 200:
                    return await resp.text()
                elif resp.status == 404:
                    return None
                elif resp.status == 429:
                    wait = RETRY_DELAY * (attempt + 1) + random.uniform(1, 3)
                    print(f"  [429] 속도 제한 — {wait:.0f}초 대기...")
                    await asyncio.sleep(wait)
                else:
                    if attempt < retries - 1:
                        await asyncio.sleep(RETRY_DELAY)
                    else:
                        return None
        except (aiohttp.ClientError, asyncio.TimeoutError):
            if attempt < retries - 1:
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))
            else:
                return None
    return None


# ============================================================
# ✅ [수정1] get_post_list: (posts, total_rows) 튜플 반환
#    - total_rows: 페이지에 실제 존재하는 행 수
#      → 0이면 진짜 빈 페이지 (마지막 페이지 이후)
#      → -1이면 요청 자체 실패
#    기존에는 posts 리스트만 반환해서
#    "기존 글만 있는 페이지"와 "진짜 빈 페이지"를 구분 못했음
# ============================================================
async def get_post_list(session, page: int) -> tuple[list[dict], int]:
    url = f"{BASE_URL}&page={page}"
    html = await fetch_via_unlocker(session, url)
    if not html:
        return [], -1  # -1 = 요청 실패

    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("tr.ub-content.us-post")
    total_rows = len(rows)  # 기존 글 포함 실제 행 수

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

    return posts, total_rows  # ✅ total_rows 추가 반환


# ============================================================
# 개별 글 본문 수집 (변경 없음)
# ============================================================
async def get_post_content(session, url: str) -> dict:
    html = await fetch_via_unlocker(session, url)
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
# ✅ [수정2] fetch_lists_batch: total_rows도 같이 반환
# ============================================================
async def fetch_lists_batch(session, pages, semaphore):
    async def fetch_one_page(page):
        async with semaphore:
            await asyncio.sleep(random.uniform(0.1, 0.3))
            posts, total_rows = await get_post_list(session, page)  # ✅ 튜플 언패킹
            return page, posts, total_rows  # ✅ total_rows 추가

    tasks = [fetch_one_page(p) for p in pages]
    results = await asyncio.gather(*tasks)
    results.sort(key=lambda x: x[0])
    return results


# ============================================================
# 본문 병렬 수집 (변경 없음)
# ============================================================
async def fetch_contents_batch(session, posts, semaphore):
    async def fetch_one(post):
        async with semaphore:
            await asyncio.sleep(random.uniform(0.1, 0.3))
            content = await get_post_content(session, post["링크"])
            post.update(content)
            return post
    tasks = [fetch_one(post) for post in posts]
    return await asyncio.gather(*tasks)


# ============================================================
# ✅ [수정3] crawl: 종료 조건 전면 수정
# ============================================================
async def crawl():
    print(f"{'='*60}")
    print(f"  디시인사이드 마운자로 갤러리 크롤러")
    print(f"  방식: 페이지 목록 → 본문 수집 (Web Unlocker API)")
    print(f"  페이지 범위: {START_PAGE} ~ {END_PAGE}")
    print(f"  동시 요청: {CONCURRENCY}개")
    print(f"{'='*60}\n")

    if not check_api_key():
        return

    collection = connect_mongo()
    existing_nums = load_existing_nums(collection)
    is_first_write = not os.path.exists(OUTPUT_CSV)

    if existing_nums:
        print(f"📊 기존 {len(existing_nums)}개 글 (건너뜀)\n")

    buffer = []
    total_saved = 0
    total_skipped = 0

    # ✅ [수정3-A] 카운터 분리
    #    기존: empty_count — 신규 글 0개이면 무조건 증가 (조기 종료 원인)
    #    수정: truly_empty_count — 페이지 자체에 글이 없을 때만 증가
    #          fetch_fail_count  — 요청 실패 연속 횟수
    truly_empty_count = 0
    fetch_fail_count = 0

    semaphore = asyncio.Semaphore(CONCURRENCY)

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)

    LIST_BATCH = 10

    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            for batch_start in range(START_PAGE, END_PAGE + 1, LIST_BATCH):
                batch_end = min(batch_start + LIST_BATCH - 1, END_PAGE)
                pages = list(range(batch_start, batch_end + 1))

                print(f"[목록] 페이지 {batch_start}~{batch_end} 동시 수집 중...")
                start_time = time.time()

                page_results = await fetch_lists_batch(session, pages, semaphore)

                # ✅ [수정3-B] 페이지별로 실제 empty / 실패 / 정상 분류
                batch_truly_empty = 0
                batch_fail = 0
                all_new_posts = []

                for page_num, posts, total_rows in page_results:  # ✅ total_rows 추가
                    if total_rows == -1:
                        # 요청 실패
                        batch_fail += 1
                        print(f"  ⚠️  페이지 {page_num} 요청 실패")
                    elif total_rows == 0:
                        # ✅ 진짜 빈 페이지 (마지막 페이지 이후)
                        batch_truly_empty += 1
                    else:
                        # ✅ 글은 있음 → 기존 글만 있어도 truly_empty 리셋
                        truly_empty_count = 0
                        for post in posts:
                            if post["번호"] in existing_nums:
                                total_skipped += 1
                            else:
                                all_new_posts.append(post)
                                existing_nums.add(post["번호"])

                # ✅ [수정3-C] 배치 내 모든 페이지가 진짜 빈 페이지일 때만 카운트
                if batch_truly_empty == len(pages):
                    truly_empty_count += 1
                    print(f"  ⚠️  배치 전체 빈 페이지 (연속 {truly_empty_count}회)")
                    if truly_empty_count >= 2:
                        print("  → 연속 2배치 빈 페이지 — 마지막 페이지 도달, 종료")
                        break

                # ✅ [수정3-D] 요청 실패 누적 체크
                if batch_fail > 0:
                    fetch_fail_count += batch_fail
                    if fetch_fail_count >= 10:
                        print(f"  ❌ 연속 요청 실패 {fetch_fail_count}회 — 크롤링 중단")
                        break
                else:
                    fetch_fail_count = 0

                if not all_new_posts:
                    elapsed = time.time() - start_time
                    # ✅ [수정3-E] 핵심: 신규 글 없어도 continue로 계속 진행 (종료 X)
                    print(f"       → 신규 0개 (기존 글 건너뜀: {total_skipped}개 누적) [{elapsed:.1f}초]")
                    continue

                print(f"  📝 본문 {len(all_new_posts)}개 동시 수집 중...")
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
    print(f"  CSV 파일: {OUTPUT_CSV}")
    if os.path.exists(OUTPUT_CSV):
        df = pd.read_csv(OUTPUT_CSV, encoding="utf-8-sig")
        print(f"  CSV 총 행 수: {len(df)}개")
    if collection is not None:
        doc_count = collection.count_documents({})
        print(f"  MongoDB 총 문서 수: {doc_count}개")
    print(f"{'='*60}\n")


# ============================================================
# 실시간 모니터링 (변경 없음)
# ============================================================
async def monitor(interval: int):
    print(f"{'='*60}")
    print(f"  디시인사이드 마운자로 갤러리 실시간 모니터링")
    print(f"  방식: Web Unlocker API (페이지 기준)")
    print(f"  확인 주기: {interval}초 ({interval//60}분)")
    print(f"  종료: Ctrl+C")
    print(f"{'='*60}\n")

    if not check_api_key():
        return

    collection = connect_mongo()
    existing_nums = load_existing_nums(collection)
    is_first_write = not os.path.exists(OUTPUT_CSV)

    cycle_count = 0
    total_new = 0
    semaphore = asyncio.Semaphore(CONCURRENCY)

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    try:
        while True:
            cycle_count += 1
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"{'─'*40}")
            print(f"🔄 [{now}] 모니터링 #{cycle_count}")

            connector = aiohttp.TCPConnector(ssl=ssl_ctx)
            async with aiohttp.ClientSession(connector=connector) as session:
                page_results = await fetch_lists_batch(session, [1, 2, 3], semaphore)

                new_posts = []
                for page_num, posts, total_rows in page_results:  # ✅ total_rows 언패킹
                    if total_rows <= 0:
                        continue
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