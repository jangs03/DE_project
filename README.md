# preprocess_optical.py 사용 가이드

Optical Flow magnitude를 피처로 추출해 `.npy` 파일로 저장하는 전처리 스크립트입니다.

---

## 환경 설정

### 공통
```bash
pip install opencv-python numpy tqdm
```

### Windows
```bash
python -m venv venv_optical
venv_optical\Scripts\activate
pip install opencv-python numpy tqdm
```

### Mac (M1/M2)
```bash
python3 -m venv venv_optical
source venv_optical/bin/activate
pip install opencv-python-headless numpy tqdm
```

> Mac에서는 `opencv-python` 대신 `opencv-python-headless` 설치를 권장합니다.

---

## 데이터셋 구조

스크립트 실행 전 데이터셋이 아래 구조로 준비되어 있어야 합니다.

```
datasetVer3/
├── annotations/
│   └── raw_txt/
│       ├── 영화이름.txt
│       └── ...
└── frames/
    ├── 영화이름/
    │   ├── frame_000001.jpg
    │   ├── frame_000002.jpg
    │   └── ...
    └── ...
```

어노테이션 파일 형식:
```
[video_id, 번호, start_frame, end_frame, label]
```
- label: `violence`, `neg_hard`, `neg_easy`

---

## 설정

`preprocess_optical.py` 상단의 설정 부분만 수정하면 됩니다.

```python
MY_MOVIES   = None        # None이면 자동 선택, 특정 영화만 할 경우 ['영화1', '영화2']
MAX_MOVIES  = 10          # 자동 선택 시 최대 영화 수
BASE_PATH   = r'./datasetVer3'   # 데이터셋 경로
OUTPUT_PATH = r'./output_npy'    # 결과 저장 경로
CLIP_LEN    = 8           # 클립 길이 (프레임 수)
STRIDE      = 2           # 슬라이딩 윈도우 간격
NEG_RATIO   = 1.5         # violence 대비 neg 클립 비율
MAX_WORKERS = 6           # 병렬 처리 워커 수
```

### MAX_WORKERS 권장값

| CPU 코어 수 | 권장 MAX_WORKERS |
|------------|----------------|
| 8코어       | 5              |
| 12코어      | 7              |
| 16코어      | 10             |

> CPU 코어 수 확인:
> - Windows: `Get-WmiObject Win32_Processor | Select-Object NumberOfLogicalProcessors`
> - Mac: `sysctl -n hw.logicalcpu`

---

## 실행

```bash
python preprocess_optical.py
```

---

## 출력

### 터미널
```
처리할 영화 10개:
  0OwaYB-BBWI
  1YAwZ5CWXCQ
  ...

  [0OwaYB-BBWI] 100%|████████| 30/30 [구간] violence=284 neg=426
  [0OwaYB-BBWI] 완료 → violence: 284 / neg: 426

전체 완료 — 1823s (30.4분)
총 클립:   7124개
violence:  2847개
neg:       4277개
X shape:   (7124, 8)
```

### 저장 파일

영화별로 개별 저장됩니다.

```
output_npy/
├── 0OwaYB-BBWI_clip8_X.npy   # shape: (클립수, 8)
├── 0OwaYB-BBWI_clip8_y.npy   # ['violence', 'neg', ...]
├── 1YAwZ5CWXCQ_clip8_X.npy
├── 1YAwZ5CWXCQ_clip8_y.npy
└── ...
```

---

## 재실행 (이어하기)

이미 완료된 영화는 자동으로 스킵합니다. 중간에 끊겨도 재실행하면 이어서 처리합니다.

```
  [0OwaYB-BBWI] ✅ 완료 (1007개) 스킵
  [1YAwZ5CWXCQ] ✅ 완료 (680개) 스킵
  [6OvtUA4JPsk] 처리 시작...
```

---

## 참고

- 피처: Optical Flow magnitude (Farneback 알고리즘)
- 클립 단위: `CLIP_LEN`개 프레임 → magnitude 시퀀스 1개
- 레이블: `violence` / `neg` (neg_hard + neg_easy 통합)
- GPU 불필요 — CPU만으로 실행 가능
