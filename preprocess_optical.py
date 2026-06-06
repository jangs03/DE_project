# ========================================
# ⚠️ 여기만 수정
MY_MOVIES   = None   # None이면 frames 폴더 기준 자동 선택 (최대 MAX_MOVIES)
MAX_MOVIES  = 10     # 자동 선택 시 최대 영화 수
BASE_PATH   = r'./datasetVer3'   # 데이터셋 경로 (윈도우: r'C:\Users\...\datasetVer3')
OUTPUT_PATH = r'./output_npy'    # 결과 저장 경로
CLIP_LEN    = 8      # 클립 길이 (프레임 수)
STRIDE      = 2      # 슬라이딩 윈도우 간격
NEG_RATIO   = 1.5    # violence 대비 neg 비율
MAX_WORKERS = 6      # 병렬 처리 워커 수 (CPU 코어 수의 60~70% 권장)
# ========================================

import cv2
import numpy as np
import re
import time
from pathlib import Path
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from tqdm import tqdm


# ── 유틸 함수 ──────────────────────────────────────────────
def load_frame(base_path: str, movie_id: str, frame_no: int):
    path = Path(base_path) / 'frames' / movie_id / f'frame_{frame_no:06d}.jpg'
    if not path.exists():
        return None
    return cv2.imread(str(path))


def compute_flow_magnitude(frame1, frame2) -> float:
    gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
    flow  = cv2.calcOpticalFlowFarneback(
        gray1, gray2, None,
        pyr_scale=0.5, levels=3, winsize=15,
        iterations=3, poly_n=5, poly_sigma=1.2, flags=0
    )
    return float(np.sqrt(flow[..., 0]**2 + flow[..., 1]**2).mean())


def parse_annotation(base_path: str, movie_id: str) -> list:
    txt_path = Path(base_path) / 'annotations' / 'raw_txt' / f'{movie_id}.txt'
    scenes   = []
    with open(txt_path, encoding='utf-8') as f:
        for line in f:
            match = re.match(r'\[(.+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\w+)\]', line.strip())
            if match:
                start = int(match.group(3))
                end   = int(match.group(4))
                label = match.group(5)
                if label == 'violence':
                    scenes.append({'start': start, 'end': end, 'label': 'violence'})
                elif label in ('neg_hard', 'neg_easy'):
                    scenes.append({'start': start, 'end': end, 'label': 'neg'})
    return scenes


def build_clips(base_path: str, movie_id: str, clip_len: int,
                stride: int, neg_ratio: float, movie_idx: int = 0):
    scenes = parse_annotation(base_path, movie_id)

    vio_clips = {'clips': [], 'labels': []}
    neg_clips = {'clips': [], 'labels': []}

    with tqdm(
        total=len(scenes),
        desc=f'[{movie_id}]',
        unit='구간',
        leave=True,
        ncols=90,
        position=movie_idx
    ) as pbar:
        for scene in scenes:
            start  = scene['start']
            end    = scene['end']
            label  = scene['label']
            frames = list(range(start, end + 1))

            for i in range(0, len(frames) - clip_len, stride):
                clip_frames = frames[i:i + clip_len + 1]

                magnitudes = []
                prev_frame = None
                for fn in clip_frames:
                    curr_frame = load_frame(base_path, movie_id, fn)
                    if curr_frame is None:
                        prev_frame = None
                        continue
                    if prev_frame is not None:
                        mag = compute_flow_magnitude(prev_frame, curr_frame)
                        magnitudes.append(mag)
                    prev_frame = curr_frame

                if len(magnitudes) < clip_len:
                    continue

                clip_feat = magnitudes[:clip_len]

                if label == 'violence':
                    vio_clips['clips'].append(clip_feat)
                    vio_clips['labels'].append('violence')
                else:
                    neg_clips['clips'].append(clip_feat)
                    neg_clips['labels'].append('neg')

            pbar.update(1)
            pbar.set_postfix({
                'vio': len(vio_clips['clips']),
                'neg': len(neg_clips['clips'])
            })

    # neg 비율 조정
    max_neg = int(len(vio_clips['clips']) * neg_ratio)
    if len(neg_clips['clips']) > max_neg:
        idx = np.random.choice(len(neg_clips['clips']), max_neg, replace=False)
        neg_clips['clips']  = [neg_clips['clips'][i]  for i in idx]
        neg_clips['labels'] = [neg_clips['labels'][i] for i in idx]

    all_clips  = vio_clips['clips']  + neg_clips['clips']
    all_labels = vio_clips['labels'] + neg_clips['labels']

    return all_clips, all_labels


def process_movie(args):
    movie, clip_len, base_path, output_path, stride, neg_ratio, movie_idx = args

    x_path = Path(output_path) / f'{movie}_clip{clip_len}_X.npy'
    y_path = Path(output_path) / f'{movie}_clip{clip_len}_y.npy'

    if x_path.exists() and y_path.exists():
        saved = len(np.load(x_path))
        tqdm.write(f'  [{movie}] ✅ 완료 ({saved}개) 스킵')
        return

    clips, labels = build_clips(base_path, movie, clip_len, stride, neg_ratio, movie_idx)
    np.save(x_path, np.array(clips, dtype=np.float32))
    np.save(y_path, np.array(labels))
    tqdm.write(f'  [{movie}] 저장 완료 → {len(clips)}개')


# ── 전체 실행 ──────────────────────────────────────────────
if __name__ == '__main__':
    FRAMES_DIR = Path(BASE_PATH) / 'frames'
    ANNOT_DIR  = Path(BASE_PATH) / 'annotations' / 'raw_txt'
    OUTPUT_DIR = Path(OUTPUT_PATH)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if MY_MOVIES is None:
        MY_MOVIES = [
            f.stem for f in sorted(ANNOT_DIR.glob('*.txt'))
            if (FRAMES_DIR / f.stem).exists()
        ][:MAX_MOVIES]

    print(f'{"="*50}')
    print(f'clip_len={CLIP_LEN} | stride={STRIDE} | workers={MAX_WORKERS}')
    print(f'피처: Optical Flow magnitude → shape: (N, {CLIP_LEN})')
    print(f'{"="*50}')
    print(f'처리할 영화 {len(MY_MOVIES)}개:')
    for m in MY_MOVIES:
        print(f'  {m}')
    print()

    start_time = time.time()
    args = [
        (movie, CLIP_LEN, BASE_PATH, OUTPUT_PATH, STRIDE, NEG_RATIO, idx)
        for idx, movie in enumerate(MY_MOVIES)
    ]

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        executor.map(process_movie, args)

    elapsed = time.time() - start_time

    # 전체 집계
    print(f'\n{"="*50}')
    print(f'전체 완료 — {elapsed:.0f}s ({elapsed/60:.1f}분)')
    print(f'{"="*50}')

    X_all, y_all = [], []
    for movie in MY_MOVIES:
        x_path = OUTPUT_DIR / f'{movie}_clip{CLIP_LEN}_X.npy'
        y_path = OUTPUT_DIR / f'{movie}_clip{CLIP_LEN}_y.npy'
        if x_path.exists():
            X_all.extend(np.load(x_path).tolist())
            y_all.extend(np.load(y_path).tolist())

    print(f'총 클립:   {len(X_all)}개')
    print(f'violence:  {y_all.count("violence")}개')
    print(f'neg:       {y_all.count("neg")}개')
    print(f'X shape:   ({len(X_all)}, {CLIP_LEN})')
    print(f'\n저장 위치: {OUTPUT_DIR.resolve()}')
    print('파일 목록:')
    for f in sorted(OUTPUT_DIR.glob('*.npy')):
        size = f.stat().st_size / 1024 / 1024
        print(f'  {f.name} ({size:.1f} MB)')
