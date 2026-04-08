# 🐦 트윗 스크래핑 프로젝트 — 환경설정 가이드

> Wegovy · Mounjaro 트윗 수집 스크립트 (twscrape)

---

## 📋 목차

1. [사전 준비](#1-사전-준비)
2. [Python 설치 확인](#2-python-설치-확인)
3. [라이브러리 설치](#3-라이브러리-설치)
4. [프로젝트 폴더 구성](#4-프로젝트-폴더-구성)
5. [X(Twitter) 쿠키 추출](#5-xtwitter-쿠키-추출)
6. [twscrape 버그 수정 (필수)](#6-twscrape-버그-수정-필수--최초-1회)
7. [코드에 계정 정보 입력](#7-코드에-계정-정보-입력)
8. [스크립트 실행](#8-스크립트-실행)
9. [시작 위치 선택](#9-시작-위치-선택)
10. [저장 파일 구조](#10-저장-파일-구조)
11. [자주 발생하는 문제](#11-자주-발생하는-문제)
12. [팀 협업 주의사항](#12-팀-협업-주의사항)

---

## 1. 사전 준비

### 필요한 계정
- **X(Twitter) 계정** — 스크래핑에 사용할 계정 (개인 계정 사용 시 정지될 수 있으니 별도 계정 권장)
- **Gmail 계정** — X 계정에 연동된 이메일

> ⚠️ **계정 정지 주의**: 스크래핑 감지로 계정이 정지되면 `IndexError: list index out of range` 오류가 납니다. x.com에 직접 로그인해서 검색이 정상적으로 되는지 확인하세요. 정지됐다면 새 계정으로 교체해야 합니다.

### 필요한 소프트웨어
- Python 3.11 이상
- VSCode (권장)
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

## 6. twscrape 버그 수정 (필수 / 최초 1회)

twscrape가 x.com에 접근할 때 Cloudflare 차단으로 내부 JS 파일 URL을 자동으로 찾지 못합니다.
**URL을 직접 하드코딩**해서 이 문제를 우회해야 합니다. **모든 팀원이 반드시 적용**해야 합니다.

### 6-1. xclid.py 파일 열기

```powershell
$file = python -c "import twscrape; import os; print(os.path.join(os.path.dirname(twscrape.__file__), 'xclid.py'))"
code $file
```

### 6-2. `parse_anim_idx` 함수 수정

VSCode에서 `Ctrl+F` → `parse_anim_idx` 검색 후 아래 부분을 찾아서:

**수정 전:**
```python
async def parse_anim_idx(text: str) -> list[int]:
    scripts = list(get_scripts_list(text))
    scripts = [x for x in scripts if "/ondemand.s." in x]
```

**수정 후:**
```python
async def parse_anim_idx(text: str) -> list[int]:
    scripts = ["https://abs.twimg.com/responsive-web/client-web/ondemand.s.96a973da.js"]
    scripts = [x for x in scripts if "/ondemand.s." in x]
```

`Ctrl+S` 로 저장합니다.

### 6-3. get_scripts_list 함수도 패치

같은 파일에서 `Ctrl+F` → `Failed to parse scripts` 검색 후 아래 부분을 찾아서:

**수정 전:**
```python
    except json.decoder.JSONDecodeError as e:
        raise Exception("Failed to parse scripts") from e
```

**수정 후:**
```python
    except json.decoder.JSONDecodeError as e:
        try:
            import re as _re
            fixed = _re.sub(r'([,\{])(\s*)([\w$]+)(\s*):(?=\s*")', r'\1\2"\3"\4:', scripts)
            for k, v in json.loads(fixed).items():
                yield script_url(k, f"{v}a")
        except Exception:
            raise Exception("Failed to parse scripts") from e
```

`Ctrl+S` 로 저장합니다.

> 🔄 **나중에 `IndexError`가 다시 발생하면** JS 파일명이 바뀐 것입니다. Chrome → x.com → F12 → Network 탭에서 `ondemand.s` 검색 후 최신 파일명으로 6-2를 다시 진행하세요.

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

> 🔒 **보안 주의**: 코드를 GitHub에 올릴 때 위 값들을 반드시 빈 문자열로 바꾸세요.

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

| 증상 | 원인 | 해결 방법 |
|------|------|-----------|
| `IndexError: list index out of range` | ① 계정 정지 또는 ② xclid.py 미패치 | x.com 직접 로그인해서 계정 상태 확인 → 정지면 새 계정 교체. 정상이면 [6번](#6-twscrape-버그-수정-필수--최초-1회) 패치 적용 |
| 수집량이 모두 0개 | 쿠키 만료 | [5번](#5-xtwitter-쿠키-추출) 과정 다시 진행해 새 쿠키 입력 |
| `No active accounts` | 계정 DB 오류 | `Remove-Item accounts.db` 후 재실행 |
| `No account available... Next available at` | Rate limit (정상) | 그냥 두면 자동 재개됩니다 |
| `ModuleNotFoundError: twscrape` | 라이브러리 미설치 | `pip install twscrape` 실행 |
| `Account already exists` (경고) | 정상 동작 | 무시해도 됩니다 |
| `TabError: inconsistent use of tabs` | xclid.py 수정 시 탭/스페이스 혼용 | VSCode로 파일 열어서 스페이스로 통일 후 저장 |

---

## 12. 팀 협업 주의사항

- **CSV 파일 공유**: 항상 최신 CSV를 `output/` 폴더에 넣고 실행하세요. 기존 데이터를 자동으로 읽어 중복을 방지합니다.
- **역할 분담**: 같은 쿼리+구간을 동시에 여러 명이 돌리지 않도록 팀원끼리 담당 구간을 나눠주세요.
- **accounts.db 비공유**: 각자 본인 계정으로 생성합니다. GitHub에 올리지 마세요.
- **쿠키 값 비공유**: `AUTH_TOKEN`, `CT0_TOKEN`은 개인 정보입니다. GitHub push 전 반드시 삭제하세요.
- **중복 걱정 없음**: 기존 CSV의 ID를 자동으로 로드하므로 여러 번 돌려도 중복 없이 저장됩니다.

