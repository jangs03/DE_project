"""
twscrape 트윗 스크래핑 스크립트
- 쿠키 인증 방식 (Cloudflare 우회)
- 중복 제거 (tweet ID 기준)
- MongoDB 배치 저장 (100개마다 자동 저장)
- 날짜 구간별 분할 크롤링 (트윗 작성 시기별)
- 키워드: mounjaro, wegovy (각 25000개)
"""

import asyncio
import json
import csv
import os
from datetime import datetime, timezone
from twscrape import API
from twscrape.logger import set_log_level
from pymongo import MongoClient, UpdateOne
from pymongo.errors import BulkWriteError

# ── 설정 ──────────────────────────────────────────────────────────────────────

KEYWORDS           = ["mounjaro", "wegovy"]   # ozempic 제외
TWEETS_PER_KEYWORD = 25000                    # 키워드당 목표 수집 수
BATCH_SIZE         = 100                      # MongoDB 배치 저장 단위
OUTPUT_DIR         = "output"
ACCOUNTS_DB        = "accounts.db"

# ── 날짜 구간 설정 (트윗 작성 시기별 분할 크롤링) ────────────────────────────
# 오래된 구간부터 최신 순으로 수집
# 각 구간당 수집 한도 = TWEETS_PER_KEYWORD // len(DATE_RANGES)
DATE_RANGES = [
    ("2022-01-01", "2022-12-31"),   # 2022년
    ("2023-01-01", "2023-06-30"),   # 2023년 상반기
    ("2023-07-01", "2023-12-31"),   # 2023년 하반기
    ("2024-01-01", "2024-06-30"),   # 2024년 상반기
    ("2024-07-01", "2024-12-31"),   # 2024년 하반기
    ("2025-01-01", "2025-06-30"),   # 2025년 상반기
    ("2025-07-01", "2025-12-31"),   # 2025년 하반기
    ("2026-01-01", "2026-04-07"),   # 2026년 (현재까지)
]

# ── 계정 / DB 정보 (직접 입력) ────────────────────────────────────────────────


# MongoDB 연결 URI
MONGO_URI  = "mongodb+srv://jangs03:<wkdtjdus>@cluster0.jimeyod.mongodb.net/?appName=Cluster0"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── MongoDB 연결 ──────────────────────────────────────────────────────────────

def get_mongo_collection(keyword: str):
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    col = client["tweet_scraper"][keyword]
    col.create_index("id", unique=True)
    return client, col

def batch_upsert(col, batch: list[dict]) -> int:
    if not batch:
        return 0
    ops = [UpdateOne({"id": doc["id"]}, {"$set": doc}, upsert=True) for doc in batch]
    try:
        result = col.bulk_write(ops, ordered=False)
        return result.upserted_count
    except BulkWriteError as e:
        return e.details.get("nInserted", 0)

# ── 트윗 파싱 ─────────────────────────────────────────────────────────────────

def parse_tweet(tweet, keyword: str) -> dict:
    return {
        "id":            tweet.id,
        "keyword":       keyword,
        "date":          tweet.date.isoformat() if tweet.date else None,
        "username":      tweet.user.username    if tweet.user else None,
        "display_name":  tweet.user.displayname if tweet.user else None,
        "content":       tweet.rawContent,
        "language":      tweet.lang,
        "reply_count":   tweet.replyCount,
        "retweet_count": tweet.retweetCount,
        "like_count":    tweet.likeCount,
        "quote_count":   tweet.quoteCount,
        "view_count":    tweet.viewCount,
        "source":        tweet.source,
        "url":           tweet.url,
        "is_retweet":    tweet.retweetedTweet   is not None,
        "is_reply":      tweet.inReplyToTweetId is not None,
        "scraped_at":    datetime.now(timezone.utc).isoformat(),
    }

# ── 파일 저장 (백업) ──────────────────────────────────────────────────────────

def save_to_json(data: list[dict], filename: str):
    if not data:
        return
    path = os.path.join(OUTPUT_DIR, f"{filename}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  [파일] JSON -> {path}")

def save_to_csv(data: list[dict], filename: str):
    if not data:
        return
    path = os.path.join(OUTPUT_DIR, f"{filename}.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
    print(f"  [파일] CSV  -> {path}")

# ── 구간별 스크래핑 ───────────────────────────────────────────────────────────

async def scrape_period(
    api: API,
    keyword: str,
    since: str,
    until: str,
    limit: int,
    seen_ids: set,
    col,
) -> list[dict]:
    """단일 날짜 구간 스크래핑 + MongoDB 배치 저장"""
    query = f"{keyword} lang:en -is:retweet since:{since} until:{until}"
    print(f"  [{keyword}] {since} ~ {until} | 목표: {limit}개")

    all_tweets = []
    batch      = []
    skipped    = 0
    db_total   = 0

    async for tweet in api.search(query, limit=limit):
        if tweet.id in seen_ids:
            skipped += 1
            continue
        seen_ids.add(tweet.id)

        parsed = parse_tweet(tweet, keyword)
        all_tweets.append(parsed)
        batch.append(parsed)

        if len(batch) >= BATCH_SIZE:
            inserted = batch_upsert(col, batch)
            db_total += inserted
            batch.clear()

    if batch:
        db_total += batch_upsert(col, batch)
        batch.clear()

    print(f"    -> 수집: {len(all_tweets)}개 | MongoDB: {db_total}개 | 중복 제외: {skipped}개")
    return all_tweets


async def scrape_keyword(api: API, keyword: str, total_limit: int, seen_ids: set) -> list[dict]:
    """날짜 구간별로 분할해서 total_limit개 수집"""
    print(f"\n{'='*55}")
    print(f"[{keyword}] 스크래핑 시작 | 총 목표: {total_limit:,}개 | {len(DATE_RANGES)}개 구간 분할")
    print(f"{'='*55}")

    # 구간당 할당량 계산
    per_period = total_limit // len(DATE_RANGES)
    remainder  = total_limit % len(DATE_RANGES)

    mongo_client, col = get_mongo_collection(keyword)
    all_tweets = []

    try:
        for i, (since, until) in enumerate(DATE_RANGES):
            # 마지막 구간에 나머지 추가
            limit = per_period + (remainder if i == len(DATE_RANGES) - 1 else 0)
            tweets = await scrape_period(api, keyword, since, until, limit, seen_ids, col)
            all_tweets.extend(tweets)

    finally:
        mongo_client.close()

    print(f"\n[{keyword}] 전체 완료 -> 총 {len(all_tweets):,}개 수집")
    return all_tweets

# ── 메인 ──────────────────────────────────────────────────────────────────────

async def main():
    set_log_level("INFO")

    # MongoDB 연결 테스트
    print("[MongoDB] 연결 테스트 중...")
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.server_info()
        client.close()
        print("[MongoDB] 연결 성공!\n")
    except Exception as e:
        print(f"[MongoDB] 연결 실패: {e}")
        return

    # X 계정 등록
    api = API(ACCOUNTS_DB)
    cookies = f"auth_token={AUTH_TOKEN}; ct0={CT0_TOKEN}"
    print(f"[계정] '{X_USERNAME}' 쿠키 방식으로 등록 중...")
    await api.pool.add_account(
        username=X_USERNAME,
        password=X_PASSWORD,
        email=X_EMAIL,
        email_password=X_EMAIL_PASSWORD,
        cookies=cookies,
    )
    print("[계정] 등록 완료!\n")

    # 스크래핑 실행
    seen_ids: set = set()
    all_results = {}
    start_time = datetime.now()

    for keyword in KEYWORDS:
        tweets = await scrape_keyword(
            api, keyword, total_limit=TWEETS_PER_KEYWORD, seen_ids=seen_ids
        )
        all_results[keyword] = tweets
        save_to_json(tweets, f"{keyword}_tweets")
        save_to_csv(tweets,  f"{keyword}_tweets")

    # 전체 통합 파일 백업
    all_tweets = [t for tweets in all_results.values() for t in tweets]
    save_to_json(all_tweets, "ALL_combined")
    save_to_csv(all_tweets,  "ALL_combined")

    # 요약
    elapsed = datetime.now() - start_time
    print("\n" + "=" * 55)
    print("스크래핑 완료 요약")
    print("=" * 55)
    print(f"  날짜 구간  : {len(DATE_RANGES)}개 구간 분할 수집")
    for kw, tweets in all_results.items():
        print(f"  {kw:12s}: {len(tweets):,}개")
    print(f"  {'합계':12s}: {len(all_tweets):,}개")
    print(f"  소요 시간  : {elapsed}")
    print(f"  MongoDB DB : tweet_scraper")
    print(f"  컬렉션     : mounjaro / wegovy")
    print(f"  파일 백업  : ./{OUTPUT_DIR}/")
    print("=" * 55)


if __name__ == "__main__":
    asyncio.run(main())
