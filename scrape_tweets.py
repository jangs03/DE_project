"""
twscrape 트윗 스크래핑 스크립트
- 쿠키 인증 방식 (Cloudflare 우회)
- 중복 제거 (tweet ID 기준 / 기존 CSV 포함)
- CSV 500개마다 자동 저장 (append 방식)
- 약품별 × 연도별 CSV 파일 분리 저장
- 시작 쿼리 / 시작 구간 선택 가능 (중간부터 재개)
"""

import asyncio
import csv
import os
from datetime import datetime, timezone
from twscrape import API
from twscrape.logger import set_log_level

# ══════════════════════════════════════════════════════════
#  계정 정보 (직접 입력)
# ══════════════════════════════════════════════════════════
X_USERNAME       = "syeon891692"        # 트위터 아이디
X_PASSWORD       = "dlghkdueowkdtjdus"   # 트위터 비밀번호
X_EMAIL          = "seoyeonj378@gmail.com"       # 구글 이메일
X_EMAIL_PASSWORD = "dlghkdueowkdtjdus"     # 구글 비밀번호

# 브라우저 쿠키 (Cloudflare 우회용)
# Chrome → F12 → Application → Cookies → https://x.com
AUTH_TOKEN = "426b6943cd0a435293a6481a406c36f7753f2812"
CT0_TOKEN  = "9e193c1de8b4aad8ffeee369f3f59368128b19d4b26b25d28d8455b84a149c315c0b26fd47bf88458d7c0262973d83171ffce6478e2215900c08f8c8db5be6c81714e21c5ee06db41fa64ec5e5bb0b3f"


# ══════════════════════════════════════════════════════════
#  ★ 시작 위치 선택 (실행 시 터미널에서 입력)
# ══════════════════════════════════════════════════════════

def select_start_position():
    """실행 시 터미널에서 시작 쿼리와 구간을 선택"""

    query_labels = [q["label"] for q in QUERIES]
    since_dates  = [dr["since"] for dr in DATE_RANGES]

    print("\n" + "=" * 60)
    print("★ 시작 위치 선택")
    print("=" * 60)

    # ── 쿼리 선택 ──────────────────────────────────────────
    print("\n[쿼리 선택] 어떤 쿼리부터 시작할까요?")
    print("  0. 처음부터 전체 실행")
    for i, label in enumerate(query_labels, 1):
        print(f"  {i}. {label}")

    while True:
        try:
            q_input = input("\n번호 입력 (0~6): ").strip()
            q_idx   = int(q_input)
            if 0 <= q_idx <= len(query_labels):
                break
            print(f"  0~{len(query_labels)} 사이 숫자를 입력하세요.")
        except ValueError:
            print("  숫자를 입력하세요.")

    start_query_label = None if q_idx == 0 else query_labels[q_idx - 1]

    # ── 날짜 구간 선택 ─────────────────────────────────────
    print("\n[구간 선택] 어느 날짜 구간부터 시작할까요?")
    print("  0. 첫 구간부터 전체 실행")
    for i, dr in enumerate(DATE_RANGES, 1):
        print(f"  {i}. {dr['since']} ~ {dr['until']}")

    while True:
        try:
            d_input = input("\n번호 입력 (0~8): ").strip()
            d_idx   = int(d_input)
            if 0 <= d_idx <= len(DATE_RANGES):
                break
            print(f"  0~{len(DATE_RANGES)} 사이 숫자를 입력하세요.")
        except ValueError:
            print("  숫자를 입력하세요.")

    start_since_date = None if d_idx == 0 else since_dates[d_idx - 1]

    # ── 선택 확인 ──────────────────────────────────────────
    print("\n" + "-" * 60)
    print("선택 확인")
    print(f"  시작 쿼리 : {start_query_label if start_query_label else '처음부터 전체'}")
    print(f"  시작 구간 : {start_since_date if start_since_date else '첫 구간부터 전체'}")
    print("-" * 60)
    confirm = input("이대로 시작할까요? (y/n): ").strip().lower()
    if confirm != "y":
        print("다시 선택합니다...\n")
        return select_start_position()

    return start_query_label, start_since_date

# ══════════════════════════════════════════════════════════
#  수집 설정
# ══════════════════════════════════════════════════════════

OUTPUT_DIR       = "output"
ACCOUNTS_DB      = "accounts.db"
BATCH_SIZE       = 500    # 이 개수마다 CSV에 저장
TARGET_PER_RANGE = 3125   # 날짜 구간당 목표 수집 수

# ══════════════════════════════════════════════════════════
#  날짜 구간 (8개)
# ══════════════════════════════════════════════════════════

DATE_RANGES = [
    {"since": "2022-01-01", "until": "2022-12-31", "year_tag": "2022"},
    {"since": "2023-01-01", "until": "2023-06-30", "year_tag": "2023"},
    {"since": "2023-07-01", "until": "2023-12-31", "year_tag": "2023"},
    {"since": "2024-01-01", "until": "2024-06-30", "year_tag": "2024"},
    {"since": "2024-07-01", "until": "2024-12-31", "year_tag": "2024"},
    {"since": "2025-01-01", "until": "2025-06-30", "year_tag": "2025"},
    {"since": "2025-07-01", "until": "2025-12-31", "year_tag": "2025"},
    {"since": "2026-01-01", "until": "2026-04-07", "year_tag": "2026"},
]

# ══════════════════════════════════════════════════════════
#  검색 쿼리 6개
# ══════════════════════════════════════════════════════════

QUERIES = [
    {
        "label": "wegovy_weight",
        "drug":  "wegovy",
        "query": '("Wegovy" OR semaglutide) ("lost" OR pounds OR lbs OR appetite OR progress OR "week 1" OR "week 2") -stock -news -ad lang:en -is:retweet',
    },
    {
        "label": "wegovy_experience",
        "drug":  "wegovy",
        "query": '("Wegovy" OR semaglutide) (review OR experience OR "week" OR "month" OR started OR using) -stock -news -ad lang:en -is:retweet',
    },
    {
        "label": "wegovy_sideeffects",
        "drug":  "wegovy",
        "query": '("Wegovy" OR semaglutide) ("side effects" OR nausea OR vomiting OR diarrhea OR constipation OR fatigue) -stock -news -ad lang:en -is:retweet',
    },
    {
        "label": "mounjaro_weight",
        "drug":  "mounjaro",
        "query": '("Mounjaro" OR tirzepatide) ("lost" OR pounds OR lbs OR appetite OR progress OR "week 1" OR "week 2") -stock -news -ad lang:en -is:retweet',
    },
    {
        "label": "mounjaro_experience",
        "drug":  "mounjaro",
        "query": '("Mounjaro" OR tirzepatide) (review OR experience OR "week" OR "month" OR started OR using) -stock -news -ad lang:en -is:retweet',
    },
    {
        "label": "mounjaro_sideeffects",
        "drug":  "mounjaro",
        "query": '("Mounjaro" OR tirzepatide) ("side effects" OR nausea OR vomiting OR diarrhea OR constipation OR fatigue) -stock -news -ad lang:en -is:retweet',
    },
]

CSV_FIELDS = [
    "id", "query_label", "drug", "query_type",
    "date", "username", "display_name",
    "content", "language", "reply_count", "retweet_count",
    "like_count", "quote_count", "view_count",
    "source", "url", "is_retweet", "is_reply", "scraped_at",
]

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ══════════════════════════════════════════════════════════
#  시작 위치 필터링
# ══════════════════════════════════════════════════════════

def get_active_queries(start_label) -> list:
    """start_label 이후의 쿼리만 반환"""
    if start_label is None:
        return QUERIES
    labels = [q["label"] for q in QUERIES]
    if start_label not in labels:
        return QUERIES
    return QUERIES[labels.index(start_label):]

def get_active_ranges(start_since, is_first_query: bool) -> list:
    """start_since 이후의 구간만 반환. 첫 번째 쿼리에서만 적용."""
    if start_since is None or not is_first_query:
        return DATE_RANGES
    sinces = [dr["since"] for dr in DATE_RANGES]
    if start_since not in sinces:
        return DATE_RANGES
    return DATE_RANGES[sinces.index(start_since):]

# ══════════════════════════════════════════════════════════
#  CSV 파일명 생성
# ══════════════════════════════════════════════════════════

def get_csv_path(drug: str, year_tag: str) -> str:
    return os.path.join(OUTPUT_DIR, f"{drug}_{year_tag}.csv")

# ══════════════════════════════════════════════════════════
#  CSV 중복 ID 로드
# ══════════════════════════════════════════════════════════

def load_existing_ids(csv_path: str) -> set:
    ids = set()
    if not os.path.exists(csv_path):
        return ids
    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if "id" in row and row["id"]:
                    ids.add(int(row["id"]))
    except Exception as e:
        print(f"  [중복체크] CSV 읽기 오류 (무시): {e}")
    return ids

# ══════════════════════════════════════════════════════════
#  CSV append 저장
# ══════════════════════════════════════════════════════════

def append_to_csv(rows: list[dict], csv_path: str):
    if not rows:
        return
    file_exists = os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)

# ══════════════════════════════════════════════════════════
#  트윗 파싱
# ══════════════════════════════════════════════════════════

def parse_tweet(tweet, label: str, drug: str) -> dict:
    query_type = label.split("_", 1)[1] if "_" in label else ""
    return {
        "id":            tweet.id,
        "query_label":   label,
        "drug":          drug,
        "query_type":    query_type,
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

# ══════════════════════════════════════════════════════════
#  구간별 스크래핑
# ══════════════════════════════════════════════════════════

async def scrape_period(
    api:        API,
    label:      str,
    drug:       str,
    base_query: str,
    since:      str,
    until:      str,
    year_tag:   str,
    limit:      int,
    seen_ids:   set,
) -> int:
    csv_path = get_csv_path(drug, year_tag)
    query    = f"{base_query} since:{since} until:{until}"
    print(f"    [{since} ~ {until}] 목표: {limit}개 → {drug}_{year_tag}.csv")

    batch       = []
    total       = 0
    skipped     = 0
    batch_saved = 0

    async for tweet in api.search(query, limit=limit):
        if tweet.id in seen_ids:
            skipped += 1
            continue
        seen_ids.add(tweet.id)

        batch.append(parse_tweet(tweet, label, drug))
        total += 1

        if len(batch) >= BATCH_SIZE:
            append_to_csv(batch, csv_path)
            batch_saved += len(batch)
            print(f"      → CSV 저장: +{len(batch)}개 (누적 {batch_saved}개) | 중복 제외: {skipped}개")
            batch.clear()

    if batch:
        append_to_csv(batch, csv_path)
        batch_saved += len(batch)
        batch.clear()

    print(f"    → 구간 완료: {total}개 수집 | CSV 저장: {batch_saved}개 | 중복 제외: {skipped}개")
    return total

# ══════════════════════════════════════════════════════════
#  쿼리별 전체 스크래핑
# ══════════════════════════════════════════════════════════

async def scrape_query(api: API, q: dict, global_seen: set, is_first_query: bool, start_since) -> int:
    label      = q["label"]
    drug       = q["drug"]
    base_query = q["query"]

    print(f"\n{'='*60}")
    print(f"[{label}] 스크래핑 시작")
    print(f"  저장 형식 : {drug}_{{연도}}.csv")
    if is_first_query and start_since:
        print(f"  시작 구간 : {start_since} 부터")
    print(f"{'='*60}")

    grand_total = 0
    for dr in get_active_ranges(start_since, is_first_query):
        count = await scrape_period(
            api, label, drug, base_query,
            dr["since"], dr["until"], dr["year_tag"],
            TARGET_PER_RANGE, global_seen,
        )
        grand_total += count

    print(f"\n[{label}] 완료 → 총 {grand_total:,}개 수집")
    return grand_total

# ══════════════════════════════════════════════════════════
#  xclid.py 자동 패치
# ══════════════════════════════════════════════════════════

def patch_xclid():
    # twscrape xclid.py 버그 자동 패치 - unquoted JSON keys 처리
    # X(Twitter) JS 파일명이 바뀌어도 자동으로 대응합니다.
    import twscrape as _tw

    xclid_path = os.path.join(os.path.dirname(_tw.__file__), "xclid.py")

    with open(xclid_path, "r", encoding="utf-8") as f:
        src = f.read()

    if "fixed_scripts = re.sub" in src:
        print("[패치] xclid.py 이미 패치되어 있습니다.")
        return

    target = '            raise Exception("Failed to parse scripts") from e'
    if target not in src:
        print("[패치] 패치 대상을 찾지 못했습니다. twscrape 버전을 확인하세요.")
        return

    replacement = "\n".join([
        "            # Fix: unquoted JSON keys (Twitter malformed JSON)",
        "            try:",
        "                import re as _re",
        "                fixed_scripts = _re.sub(",
        "                    r'([,\\{])(\\s*)([\\w$]+)(\\s*):(?=\\s*\")',",
        "                    r'\\1\\2\"\\3\"\\4:',",
        "                    scripts",
        "                )",
        "                for k, v in json.loads(fixed_scripts).items():",
        "                    yield script_url(k, f\"{v}a\")",
        "            except Exception:",
        "                raise Exception(\"Failed to parse scripts\") from e",
    ])

    patched = src.replace(target, replacement)
    with open(xclid_path, "w", encoding="utf-8") as f:
        f.write(patched)
    print("[패치] xclid.py 패치 완료!")


# ══════════════════════════════════════════════════════════
#  메인
# ══════════════════════════════════════════════════════════

async def main():
    set_log_level("INFO")

    # xclid.py 자동 패치
    patch_xclid()

    # 터미널에서 시작 위치 선택
    START_QUERY_LABEL, START_SINCE_DATE = select_start_position()

    active_queries = get_active_queries(START_QUERY_LABEL)
    drugs          = list(dict.fromkeys(q["drug"] for q in QUERIES))
    year_tags      = list(dict.fromkeys(dr["year_tag"] for dr in DATE_RANGES))
    csv_files      = [f"{d}_{y}.csv" for d in drugs for y in year_tags]

    print("\n" + "=" * 60)
    print("트윗 스크래핑 시작")
    print(f"  쿼리 수    : {len(active_queries)}개 / 전체 {len(QUERIES)}개")
    print(f"  날짜 구간  : {len(DATE_RANGES)}개")
    print(f"  구간당 목표: {TARGET_PER_RANGE:,}개")
    print(f"  CSV 저장   : {BATCH_SIZE}개마다 자동 저장")
    if START_QUERY_LABEL:
        print(f"  ★ 시작 쿼리: {START_QUERY_LABEL} 부터")
    if START_SINCE_DATE:
        print(f"  ★ 시작 구간: {START_SINCE_DATE} 부터 (첫 쿼리만)")
    print(f"  출력 파일  : {len(csv_files)}개")
    for f in csv_files:
        print(f"    - output/{f}")
    print("=" * 60)

    # X 계정 등록
    api = API(ACCOUNTS_DB)
    cookies = f"auth_token={AUTH_TOKEN}; ct0={CT0_TOKEN}"
    print(f"\n[계정] '{X_USERNAME}' 등록 중...")
    await api.pool.add_account(
        username=X_USERNAME,
        password=X_PASSWORD,
        email=X_EMAIL,
        email_password=X_EMAIL_PASSWORD,
        cookies=cookies,
    )
    print("[계정] 등록 완료!\n")

    # 시작 전 모든 기존 CSV에서 ID 로드
    print("[중복체크] 기존 CSV 파일에서 ID 로드 중...")
    global_seen: set = set()
    for drug in drugs:
        for year_tag in year_tags:
            path = get_csv_path(drug, year_tag)
            ids  = load_existing_ids(path)
            if ids:
                print(f"  {drug}_{year_tag}.csv → {len(ids):,}개")
            global_seen.update(ids)
    print(f"[중복체크] 총 기존 ID {len(global_seen):,}개 로드 완료\n")

    # 스크래핑 실행
    start_time = datetime.now()
    results    = {}

    for i, q in enumerate(active_queries):
        count = await scrape_query(api, q, global_seen, is_first_query=(i == 0), start_since=START_SINCE_DATE)
        results[q["label"]] = count

    # 최종 요약
    elapsed = datetime.now() - start_time
    print("\n" + "=" * 60)
    print("스크래핑 완료 요약")
    print("=" * 60)
    for label, count in results.items():
        print(f"  {label:30s}: {count:,}개")
    print(f"  {'합계':30s}: {sum(results.values()):,}개")
    print(f"  소요 시간  : {elapsed}")
    print(f"  저장 위치  : ./{OUTPUT_DIR}/")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
