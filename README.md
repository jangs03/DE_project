# 🐦 트윗 스크래핑 프로젝트 — 환경설정 가이드

> Wegovy · Mounjaro 트윗 수집 스크립트 (twscrape)

---

## 📋 목차

1. [사전 준비](#1-사전-준비)
2. [Python 설치 확인](#2-python-설치-확인)
3. [라이브러리 설치](#3-라이브러리-설치)
4. [프로젝트 폴더 구성](#4-프로젝트-폴더-구성)
5. [X(Twitter) 쿠키 추출](#5-xtwitter-쿠키-추출)
6. [twscrape 버그 수정](#6-twscrape-버그-수정-최초-1회)
7. [코드에 계정 정보 입력](#7-코드에-계정-정보-입력)
8. [스크립트 실행](#8-스크립트-실행)
9. [시작 위치 선택](#9-시작-위치-선택)
10. [저장 파일 구조](#10-저장-파일-구조)
11. [자주 발생하는 문제](#11-자주-발생하는-문제)
12. [팀 협업 주의사항](#12-팀-협업-주의사항)

---

## 1. 사전 준비

### 필요한 계정
- **X(Twitter) 계정** — 스크래핑에 사용할 계정
- **Gmail 계정** — X 계정에 연동된 이메일

> ⚠️ **주의**: 본인 개인 계정 사용 시 스크래핑 감지로 일시 제한될 수 있습니다. 가능하면 별도 계정을 만들어 사용하세요.

### 필요한 소프트웨어
- Python 3.11 이상
- VSCode (권장) 또는 다른 코드 에디터
- Google Chrome (쿠키 추출용)

---

## 2. Python 설치 확인

VSCode 터미널(`Ctrl + `` `)을 열고 아래 명령어를 입력하세요.

```bash
python --version
```

`Python 3.11.x` 이상이 출력되면 정상입니다.
설치가 안 되어 있다면 [python.org](https://www.python.org/downloads/)에서 다운로드하세요.

---

## 3. 라이브러리 설치

```bash
pip install twscrape
pip install pymongo
```

> ✅ `Successfully installed twscrape-...` 메시지가 뜨면 정상입니다.

---

## 4. 프로젝트 폴더 구성

공유받은 파일들을 아래 구조로 정리해주세요.
- 이 레포지토리를 다운받으시면 경로가 자동 설정됩니다.
- DE_prj1 파일을 바탕화면에 둬주세요.
- 처음 실행 전 VSC 터미널에서 cd "경로\"바탕 화면"\DE_prj1"를 통해 파일내로 이동합니다.

```
DE_prj1/
├── scrape_tweets.py        ← 메인 스크립트
└── output/                 ← CSV 파일 저장 폴더 (없으면 자동 생성)
    ├── wegovy_2022.csv
    ├── wegovy_2023.csv
    ├── ...                 ← 공유받은 기존 CSV 파일들 
    └── mounjaro_2026.csv
```

> 📁 **중요**: 기존 CSV 파일들을 반드시 `output/` 폴더 안에 넣어야 중복 제거가 작동합니다.

---

## 5. X(Twitter) 쿠키 추출

Cloudflare 차단을 우회하기 위해 브라우저 쿠키를 직접 사용합니다.

| 단계 | 내용 |
|------|------|
| 1 | Chrome에서 `x.com` 접속 후 로그인 |
| 2 | `F12` → 개발자 도구 열기 |
| 3 | 상단 **Application** 탭 클릭 |
| 4 | 왼쪽 패널 **Cookies** → `https://x.com` 클릭 |
| 5 | `auth_token` 값 더블클릭 후 전체 복사 (약 40자) |
| 6 | `ct0` 값 더블클릭 후 전체 복사 (약 160자) |

> ⚠️ **쿠키는 며칠~몇 주마다 만료됩니다.** 수집량이 계속 0개이면 이 과정을 다시 진행해 새 쿠키를 코드에 입력하세요.

---

## 6. twscrape 버그 수정

twscrape의 JS 파싱 버그를 수동으로 패치해야 합니다.
- ‼️‼️‼️js 파싱 값은 일회성(주기적으로 바뀜)이므로 데이터 수집이 안될때마다 제일 먼저 이 버그를 의심하셔야 합니다!

### 6-1. xclid.py 파일 위치 찾기

```bash
python -c "import twscrape; import os; print(os.path.dirname(twscrape.__file__))"
```

출력된 경로 + `\xclid.py` 가 수정할 파일입니다.

### 6-2. 최신 JS 파일명 찾기

Chrome에서 `x.com` 접속 후 **Network 탭** (`F12`)에서 `ondemand.s` 검색 후 새로고침(f5):

결과로 나오는 `ondemand.s.xxxxxxxx.js` 형태의 파일명을 복사합니다.

### 6-3. PowerShell에서 패치 적용

아래 명령어의 경로와 파일명을 실제 값으로 바꿔서 실행:

```powershell
$file = "C:\위에서_나온_경로\twscrape\xclid.py"
(Get-Content $file -Raw) -replace 'ondemand\.s\.[a-f0-9]+\.js', 'ondemand.s.‼️여기에_실제파일명.js' | Set-Content $file
```

적용 확인:
- 출력창에 위에서 입력한 xxxxxxxx값이 있는지 확인
```powershell
Select-String -Path $file -Pattern "ondemand"
```

> 🔄 **이후에도 0개 수집이 반복되면** JS 파일명이 바뀐 것입니다. 6-2 → 6-3을 다시 진행하세요.

---

## 7. 코드에 계정 정보 입력

`scrape_tweets.py` 파일을 VSCode로 열고 상단의 계정 정보를 수정합니다.

```python
# ══ 계정 정보 (직접 입력) ══
X_USERNAME       = "본인_트위터_아이디"
X_PASSWORD       = "본인_트위터_비밀번호"
X_EMAIL          = "본인_구글_이메일@gmail.com"
X_EMAIL_PASSWORD = "본인_구글_비밀번호"

# 5번에서 복사한 쿠키값
AUTH_TOKEN = "복사한_auth_token_값"
CT0_TOKEN  = "복사한_ct0_값"
```

---

## 8. 스크립트 실행

```powershell
# 1. 프로젝트 폴더로 이동
cd "C:\Users\사용자명\DE_prj1"

# 2. DB 초기화 (처음 실행하거나 계정 문제 발생 시)
Remove-Item accounts.db

# 3. 실행
python scrape_tweets.py
```

실행하면 터미널에서 시작 위치 선택 화면이 나타납니다.

---

## 9. 시작 위치 선택

실행 후 터미널에서 아래와 같이 선택합니다.

```
[쿼리 선택] 어떤 쿼리부터 시작할까요?
  0. 처음부터 전체 실행
  1. wegovy_weight
  2. wegovy_experience
  3. wegovy_sideeffects
  4. mounjaro_weight
  5. mounjaro_experience
  6. mounjaro_sideeffects

번호 입력 (0~6): 1

[구간 선택] 어느 날짜 구간부터 시작할까요?
  0. 첫 구간부터 전체 실행
  1. 2022-01-01 ~ 2022-12-31
  2. 2023-01-01 ~ 2023-06-30
  3. 2023-07-01 ~ 2023-12-31
  4. 2024-01-01 ~ 2024-06-30
  5. 2024-07-01 ~ 2024-12-31
  6. 2025-01-01 ~ 2025-06-30
  7. 2025-07-01 ~ 2025-12-31
  8. 2026-01-01 ~ 2026-04-07

번호 입력 (0~8): 3

이대로 시작할까요? (y/n): y
```

> 💡 **중간에 끊겼다면** CSV에서 마지막으로 수집된 날짜를 확인 후 해당 구간부터 재시작하면 됩니다.

---

## 10. 저장 파일 구조

수집된 트윗은 **약품별 × 연도별** 총 10개 CSV 파일에 저장됩니다.

| 파일명 | 내용 |
|--------|------|
| `wegovy_2022.csv` | Wegovy 관련 트윗 (2022년) |
| `wegovy_2023.csv` | Wegovy 관련 트윗 (2023년) |
| `wegovy_2024.csv` | Wegovy 관련 트윗 (2024년) |
| `wegovy_2025.csv` | Wegovy 관련 트윗 (2025년) |
| `wegovy_2026.csv` | Wegovy 관련 트윗 (2026년) |
| `mounjaro_2022.csv` | Mounjaro 관련 트윗 (2022년) |
| `mounjaro_2023.csv` | Mounjaro 관련 트윗 (2023년) |
| `mounjaro_2024.csv` | Mounjaro 관련 트윗 (2024년) |
| `mounjaro_2025.csv` | Mounjaro 관련 트윗 (2025년) |
| `mounjaro_2026.csv` | Mounjaro 관련 트윗 (2026년) |

### CSV 주요 컬럼

| 컬럼명 | 설명 | 예시 |
|--------|------|------|
| `id` | 트윗 고유 ID | `1234567890` |
| `query_label` | 수집에 사용된 쿼리 | `wegovy_weight` |
| `drug` | 약품명 | `wegovy` / `mounjaro` |
| `query_type` | 쿼리 유형 | `weight` / `experience` / `sideeffects` |
| `date` | 트윗 작성일 | `2024-03-15T10:23:00` |
| `username` | 작성자 아이디 | `user123` |
| `content` | 트윗 본문 | `Started Wegovy last week...` |
| `like_count` | 좋아요 수 | `42` |
| `scraped_at` | 수집 시각 (UTC) | `2026-04-08T03:21:00` |

---

## 11. 자주 발생하는 문제
- 에러발생 코드를 카톡으로 알려주시면 답변드릴 수 있는 문제는 답변드리고 같이 해결하도록 노력해보겠습니다!

| 증상 | 원인 | 해결 방법 |
|------|------|-----------|
| 수집량이 모두 0개 | 쿠키 만료 | [5번](#5-xtwitter-쿠키-추출) 과정을 다시 진행해 새 쿠키를 입력하세요 |
| `IndexError: list index out of range` | JS 파일명 변경 | [6번](#6-twscrape-버그-수정-최초-1회) 과정을 다시 진행하세요 |
| `No active accounts` | 계정 DB 오류 | `Remove-Item accounts.db` 후 재실행하세요 |
| `No account available... Next available at` | Rate limit (정상) | 그냥 두면 자동으로 재개됩니다 |
| `ModuleNotFoundError: twscrape` | 라이브러리 미설치 | `pip install twscrape` 실행하세요 |
| `Account already exists` (경고) | 정상 동작 | 무시해도 됩니다 > Remove acccount.db를 실행하시면 없어짐. |

---

## 12. 팀 협업 주의사항

- **CSV 파일 공유**: 항상 최신 CSV를 `output/` 폴더에 넣고 실행하세요. 기존 데이터를 자동으로 읽어 중복을 방지합니다.
- **역할 분담**: 같은 쿼리+구간을 동시에 여러 명이 돌리지 않도록 팀원끼리 담당 구간을 나눠주세요.
- **accounts.db 비공유**: 각자 본인 계정으로 생성합니다. GitHub에 올리지 마세요.
- **쿠키 값 비공유**: `AUTH_TOKEN`, `CT0_TOKEN`은 개인 정보입니다. GitHub push 전 반드시 삭제하세요.
- **중복 걱정 없음**: 기존 CSV의 ID를 자동으로 로드하므로 여러 번 돌려도 중복 없이 저장됩니다.

