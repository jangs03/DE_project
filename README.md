# 💊 DC Mounjaro Gallery Crawler

디시인사이드 [마운자로 마이너갤러리](https://gall.dcinside.com/mgallery/board/lists/?id=mounjaro) 게시글을 수집하는 Python 크롤러입니다.  
GLP-1 약물(마운자로, 위고비 등) 관련 사용자 후기·부작용·경험담을 텍스트 데이터로 수집하여 분석에 활용할 수 있습니다.

---

## 📌 주요 기능

| 기능 | 설명 |
|------|------|
| **게시글 목록 수집** | 글 번호, 제목, 작성자, 날짜, 조회수, 추천수, 댓글수 |
| **본문 텍스트 수집** | 각 게시글 본문 전문 + 이미지 수 |
| **50개 단위 중간 저장** | 크롤링 중단/에러 발생 시 데이터 유실 방지 |
| **이어서 크롤링** | 기존 CSV의 글 번호를 읽어 중복 수집 방지 |
| **키워드 필터링** | 특정 키워드가 포함된 게시글만 선별 수집 |
| **Ctrl+C 안전 종료** | 수동 중단 시 버퍼 데이터를 저장 후 종료 |

---

## 🛠 환경 설정

### 요구사항

- Python 3.9+
- pip

### 설치

```bash
# 1. 레포지토리 클론
git clone https://github.com/<your-org>/dc-mounjaro-crawler.git
cd dc-mounjaro-crawler

# 2. 가상환경 생성 (권장)
python -m venv venv
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows

# 3. 의존성 설치
pip install -r requirements.txt
```

### requirements.txt

```
requests>=2.31.0
beautifulsoup4>=4.12.0
pandas>=2.0.0
```

> Excel 출력이 필요하면 `openpyxl`도 추가하세요.

---

## 🚀 실행 방법

### 기본 실행

```bash
python dc_mounjaro_crawler.py
```

실행하면 아래와 같은 로그가 출력됩니다:

```
============================================================
  디시인사이드 마운자로 갤러리 크롤러
  페이지 범위: 1 ~ 30
  중간 저장 단위: 50개마다
  키워드 필터: 없음 (전체 수집)
============================================================

[목록] 페이지 1/30 수집 중...
       → 20개 게시글 발견
  📝 [1] 마운자로 2주차 후기...
  📝 [2] 5mg 올렸는데 부작용이...
  ...

💾 중간 저장 완료 — 50개 추가 → mounjaro_posts.csv
  ✅ 누적 저장: 50개 | 건너뜀: 0개
```

### 이어서 크롤링

중간에 중단되었거나 추가 페이지를 수집하고 싶을 때, 그대로 다시 실행하면 됩니다.

```bash
# 기존 CSV가 있으면 자동으로 중복 건너뜀
python dc_mounjaro_crawler.py
```

```
📂 기존 CSV에서 150개 글 번호 로드 완료 (중복 건너뜀)
```

---

## ⚙️ 설정값 가이드

스크립트 상단의 설정값을 수정하여 크롤링 범위와 동작을 조절합니다.

```python
# ============================================================
# 설정
# ============================================================
GALLERY_ID = "mounjaro"       # 갤러리 ID
GALLERY_TYPE = "mgallery"     # mgallery(마이너) / board(정규)

START_PAGE = 1                # 시작 페이지
END_PAGE = 30                 # 끝 페이지 (페이지당 약 20개 게시글)

DELAY = 1.5                   # 요청 간 대기 시간(초)

KEYWORD_FILTER = []           # 키워드 필터 (빈 리스트 = 전체 수집)
SAVE_EVERY = 50               # N개마다 CSV 중간 저장
OUTPUT_CSV = "mounjaro_posts.csv"
```

### 설정값 상세 설명

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `GALLERY_ID` | `"mounjaro"` | 디시인사이드 갤러리 ID. URL의 `?id=` 뒤에 오는 값 |
| `GALLERY_TYPE` | `"mgallery"` | `mgallery` = 마이너갤러리, `board` = 정규갤러리 |
| `START_PAGE` | `1` | 크롤링 시작 페이지 (1 = 최신글) |
| `END_PAGE` | `30` | 크롤링 마지막 페이지. 페이지당 약 20개 글 기준, 30페이지 ≈ 600개 |
| `DELAY` | `1.5` | 요청 사이 대기(초). **1.0 미만으로 낮추지 마세요** (IP 차단 위험) |
| `KEYWORD_FILTER` | `[]` | `["후기", "부작용"]` 처럼 설정하면 제목에 해당 키워드가 포함된 글만 수집 |
| `SAVE_EVERY` | `50` | 중간 저장 단위. 메모리가 부족하면 줄이고, I/O를 줄이려면 늘리세요 |
| `OUTPUT_CSV` | `"mounjaro_posts.csv"` | 출력 파일명 |

### 다른 갤러리에 적용하기

다른 갤러리를 크롤링하려면 `GALLERY_ID`와 `GALLERY_TYPE`만 변경하면 됩니다.

```python
# 예: 위고비 갤러리 (마이너)
GALLERY_ID = "wegovy"
GALLERY_TYPE = "mgallery"

# 예: 다이어트 갤러리 (정규)
GALLERY_ID = "diet"
GALLERY_TYPE = "board"
```

---

## 📊 출력 데이터

### CSV 컬럼 구조

| 컬럼 | 타입 | 설명 | 예시 |
|------|------|------|------|
| `번호` | int | 게시글 고유 번호 | `12345` |
| `제목` | str | 게시글 제목 | `마운자로 2주차 후기` |
| `작성자` | str | 닉네임 또는 ID | `ㅇㅇ` |
| `날짜` | str | 작성일시 | `2026-04-15 14:30:00` |
| `조회수` | str | 조회 수 | `523` |
| `추천수` | str | 추천 수 | `3` |
| `댓글수` | str | 댓글 수 | `12` |
| `본문` | str | 게시글 본문 전문 (텍스트만) | `5mg에서 시작했는데...` |
| `이미지수` | int | 본문에 포함된 이미지 수 | `2` |
| `링크` | str | 게시글 URL | `https://gall.dcinside.com/...` |

### 출력 예시

```
번호,제목,작성자,날짜,조회수,추천수,댓글수,본문,이미지수,링크
12345,마운자로 2주차 후기,ㅇㅇ,2026-04-15 14:30:00,523,3,12,"5mg에서 시작했는데...",2,https://...
12344,부작용 질문,다이어터,2026-04-15 13:10:00,210,1,5,"구역감이 심한데...",0,https://...
```

---

## ⚠️ 주의사항

### IP 차단 방지

- `DELAY`를 **1.0초 이상** 유지하세요. 권장값은 `1.5`입니다.
- 단시간에 수백 페이지를 긁으면 IP가 차단될 수 있습니다.
- 차단 시 수 시간~하루 후 자동 해제되지만, 반복되면 장기 차단될 수 있습니다.
- 대량 수집이 필요하면 `DELAY`를 `2.0~3.0`으로 올리고 여러 날에 걸쳐 나눠서 실행하세요.

### 사이트 구조 변경

- 디시인사이드는 HTML 구조를 주기적으로 변경합니다.
- 크롤러가 갑자기 동작하지 않으면 아래 CSS 셀렉터를 확인해 주세요:

```python
# 확인해야 할 셀렉터 목록
"tr.ub-content.us-post"          # 게시글 행
"td.gall_num"                    # 글 번호
"td.gall_tit a"                  # 제목 + 링크
"td.gall_tit a.reply_numbox span"  # 댓글 수
"td.gall_writer span.nickname"   # 작성자
"td.gall_date"                   # 날짜
"td.gall_count"                  # 조회수
"td.gall_recommend"              # 추천수
"div.write_div"                  # 본문 영역
```

### 데이터 윤리

- 수집한 데이터는 **내부 분석 목적**으로만 사용하세요.
- 개인정보(작성자 닉네임 등)가 포함되어 있으므로 외부 공개 시 **익명화 처리**가 필요합니다.
- 디시인사이드의 이용약관을 확인하고, 상업적 사용 시 법적 검토를 거치세요.

---

## 🧩 프로젝트 구조

```
dc-mounjaro-crawler/
├── dc_mounjaro_crawler.py   # 메인 크롤러 스크립트
├── requirements.txt         # Python 의존성
├── README.md                # 이 문서
├── mounjaro_posts.csv       # 출력 파일 (실행 후 생성, .gitignore에 추가 권장)
└── .gitignore
```

### 권장 .gitignore

```
venv/
__pycache__/
*.csv
*.xlsx
.env
```

---

## 🔧 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `[ERROR] 페이지 N 요청 실패` | IP 차단 또는 네트워크 오류 | `DELAY`를 늘리고 시간을 두고 재실행 |
| 수집된 게시글이 0개 | 사이트 구조 변경 | 브라우저 개발자도구로 셀렉터 확인 후 수정 |
| CSV에 빈 본문이 많음 | 삭제된 글 또는 비밀글 | 정상 동작. 해당 글은 본문 접근 불가 |
| `UnicodeDecodeError` | CSV 인코딩 문제 | `utf-8-sig`로 저장되므로 Excel에서 바로 열림 |
| 중복 데이터 발생 | 기존 CSV 손상 | CSV 삭제 후 처음부터 재실행 |

---

## 📈 수집 후 활용 예시

```python
import pandas as pd

df = pd.read_csv("mounjaro_posts.csv", encoding="utf-8-sig")

# 부작용 관련 글만 필터
side_effects = df[df["본문"].str.contains("부작용|구역|구토|메스꺼움|설사", na=False)]

# 월별 게시글 수 추이
df["월"] = pd.to_datetime(df["날짜"]).dt.to_period("M")
monthly = df.groupby("월").size()

# 조회수 높은 상위 20개 글
top_posts = df.nlargest(20, "조회수")[["제목", "조회수", "추천수", "링크"]]
```

---

## 🤝 기여 방법

1. 이 레포를 Fork합니다.
2. Feature 브랜치를 생성합니다 (`git checkout -b feature/add-comment-crawl`).
3. 변경사항을 커밋합니다 (`git commit -m "feat: 댓글 크롤링 기능 추가"`).
4. 브랜치에 Push합니다 (`git push origin feature/add-comment-crawl`).
5. Pull Request를 생성합니다.

---

## 📝 License

MIT License — 자유롭게 사용하되, 데이터 수집 시 관련 법규와 사이트 이용약관을 준수하세요.
