"""VQ Clustering Celery 작업"""
from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Callable, Optional

# ML Service 경로 추가 — 호스트(ml-service/)와 컨테이너(/app/ml_service) 레이아웃 모두 지원
_ML_SERVICE_CANDIDATES = [
    Path(__file__).parent.parent.parent.parent / "ml-service" / "src",  # 호스트 레포 루트 기준
    Path("/app/ml_service/src"),  # docker-compose 볼륨 마운트 기준
]
ML_SERVICE_PATH = next((p for p in _ML_SERVICE_CANDIDATES if p.exists()), _ML_SERVICE_CANDIDATES[0])
sys.path.append(str(ML_SERVICE_PATH))

from celery import Task
from app.core.celery_app import celery_app
import numpy as np
import pickle
from datetime import datetime
import logging
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

# ML Service import
try:
    from processors.feature_extractor import FeatureExtractor
    from processors.vq_codebook import VQCodebookGenerator
    from processors.clustering import ClusteringProcessor
    from processors.change_detection import ChangeDetector
    from evaluation.metrics import MetricsEvaluator
except ImportError as e:
    print(f"Warning: ML Service import failed: {e}")
    print(f"ML_SERVICE_PATH: {ML_SERVICE_PATH}")


ProgressCallback = Optional[Callable[[int, str], None]]


def _report(progress_cb: ProgressCallback, progress: int, status: str) -> None:
    """진행률 콜백이 있으면 호출한다 (없으면 무시)."""
    if progress_cb is not None:
        progress_cb(progress, status)


def _to_jsonable(value):
    """numpy 스칼라/배열 등을 JSON 직렬화 가능한 순수 파이썬 타입으로 재귀 변환한다."""
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    return value


# ---------------------------------------------------------------------------
# Celery 태스크와 무관한 순수 로직 (plain 함수)
#
# full_vq_pipeline_task가 celery 태스크 객체를 직접 함수 호출하던 버그를 없애기
# 위해, 각 단계의 실제 처리 로직을 여기로 추출했다. 개별 celery 태스크와
# full_vq_pipeline_task 양쪽 모두 이 함수들을 호출하며, 태스크는 진행률
# 보고(update_state)만 자신의 컨텍스트로 감싼다.
# ---------------------------------------------------------------------------


def _run_extract_features(image_path: str, output_path: str, progress_cb: ProgressCallback = None) -> dict:
    """특징 벡터 추출 (순수 함수, celery 무관)"""
    _report(progress_cb, 10, "Initializing...")

    extractor = FeatureExtractor(device="cpu")

    _report(progress_cb, 30, "Extracting features...")

    features = extractor.extract(image_path)

    _report(progress_cb, 80, "Saving features...")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    np.save(output_path, features)

    _report(progress_cb, 100, "Completed")

    return {
        "status": "completed",
        "image_path": image_path,
        "output_path": output_path,
        "feature_shape": list(features.shape),
        "n_features": len(features),
    }


def _run_generate_codebook(
    features_path: str,
    codebook_path: str,
    codebook_size: int = 256,
    progress_cb: ProgressCallback = None,
) -> dict:
    """VQ 코드북 생성 (순수 함수, celery 무관)"""
    _report(progress_cb, 10, "Loading features...")

    features = np.load(features_path)

    # K-means는 n_clusters <= n_samples를 요구한다. 작은 이미지(패치 수가
    # codebook_size보다 적은 경우, 예: 내장 샘플)에서 K-means가 즉시
    # 실패하지 않도록 codebook_size를 feature 개수 이하로 안전하게 낮춘다.
    effective_codebook_size = min(codebook_size, max(1, len(features)))
    if effective_codebook_size < codebook_size:
        logger.warning(
            "codebook_size(%d)가 feature 개수(%d)보다 커서 %d로 조정합니다.",
            codebook_size, len(features), effective_codebook_size,
        )

    _report(progress_cb, 30, "Generating codebook...")

    vq_gen = VQCodebookGenerator(
        codebook_size=effective_codebook_size,
        use_minibatch=(len(features) > 10000),
    )
    codebook = vq_gen.generate(features)

    _report(progress_cb, 80, "Saving codebook...")

    os.makedirs(os.path.dirname(codebook_path), exist_ok=True)
    vq_gen.save_codebook(codebook_path)

    metrics = vq_gen.get_metrics()

    _report(progress_cb, 100, "Completed")

    return {
        "status": "completed",
        "codebook_path": codebook_path,
        "codebook_size": effective_codebook_size,
        "codebook_shape": list(codebook.shape),
        "metrics": _to_jsonable(metrics),
    }


def _run_clustering(
    features_path: str,
    output_path: str,
    n_clusters: int = 8,
    algorithm: str = "kmeans",
    progress_cb: ProgressCallback = None,
) -> dict:
    """클러스터링 (순수 함수, celery 무관)"""
    _report(progress_cb, 10, "Loading features...")

    features = np.load(features_path)

    # kmeans/hierarchical은 n_clusters <= n_samples를 요구한다. (dbscan은
    # n_clusters를 쓰지 않으므로 영향 없음)
    effective_n_clusters = n_clusters
    if algorithm in ("kmeans", "hierarchical"):
        effective_n_clusters = min(n_clusters, max(1, len(features)))
        if effective_n_clusters < n_clusters:
            logger.warning(
                "n_clusters(%d)가 feature 개수(%d)보다 커서 %d로 조정합니다.",
                n_clusters, len(features), effective_n_clusters,
            )

    _report(progress_cb, 30, f"Clustering with {algorithm}...")

    processor = ClusteringProcessor(algorithm=algorithm)
    result = processor.cluster(features, n_clusters=effective_n_clusters)

    _report(progress_cb, 80, "Saving results...")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        pickle.dump(result, f)

    _report(progress_cb, 100, "Completed")

    return {
        "status": "completed",
        "output_path": output_path,
        "n_clusters": int(result["n_clusters"]),
        "algorithm": algorithm,
        "metrics": {
            "silhouette_score": _to_jsonable(result.get("silhouette_score")),
            "davies_bouldin_score": _to_jsonable(result.get("davies_bouldin_score")),
            "calinski_harabasz_score": _to_jsonable(result.get("calinski_harabasz_score")),
        },
    }


def _run_detect_changes(
    features_t1_path: str,
    features_t2_path: str,
    codebook_t1_path: str,
    codebook_t2_path: str,
    output_path: str,
    threshold_method: str = "otsu",
    progress_cb: ProgressCallback = None,
) -> dict:
    """변화 탐지 (순수 함수, celery 무관)"""
    _report(progress_cb, 10, "Loading data...")

    features_t1 = np.load(features_t1_path)
    features_t2 = np.load(features_t2_path)

    with open(codebook_t1_path, "rb") as f:
        data_t1 = pickle.load(f)
        codebook_t1 = data_t1["codebook"]

    with open(codebook_t2_path, "rb") as f:
        data_t2 = pickle.load(f)
        codebook_t2 = data_t2["codebook"]

    _report(progress_cb, 40, "Detecting changes...")

    detector = ChangeDetector(
        threshold_method=threshold_method,
        spatial_smoothing=True,
    )

    result = detector.detect_changes(
        features_t1, features_t2,
        codebook_t1, codebook_t2,
    )

    _report(progress_cb, 80, "Saving results...")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    detector.save_results(result, output_path)

    _report(progress_cb, 100, "Completed")

    return {
        "status": "completed",
        "output_path": output_path,
        "statistics": _to_jsonable(result["statistics"]),
        "threshold": float(result["threshold"]),
        # 패치별 변화 여부(순서는 feature_extractor의 슬라이딩 윈도우 순서와 동일:
        # 위→아래, 왼쪽→오른쪽) — 오버레이 시각화에 사용
        "change_mask": [bool(v) for v in result["change_mask"]],
        # 패치별 변화 강도(연속값, CVA ||Δv||) — 비지도 스크리닝 UX의 핵심.
        # 프론트가 이 값으로 threshold를 재실행 없이 실시간 조절한다(FR-402 28-3).
        "change_magnitudes": [float(v) for v in result["change_magnitudes"]],
    }


# feature_extractor.py의 슬라이딩 윈도우와 반드시 동일해야 change_mask 인덱스가
# 실제 이미지 패치 위치와 맞는다 (patch_size=224, stride=112, 반복 순서 y→x).
_PATCH_SIZE = 224
_PATCH_STRIDE = 112


def _patch_grid(width: int, height: int) -> dict:
    """이미지 크기 → 패치 격자 메타. feature_extractor의 순회와 동일 공식(단일 소스).

    프론트가 이 메타 + change_magnitudes로 오버레이를 클라이언트에서 직접 그린다
    (민감도 슬라이더·그룹 토글을 재실행 없이 지원, FR-402 28-3).
    """
    n_x = max(1, (width - _PATCH_SIZE) // _PATCH_STRIDE + 1) if width >= _PATCH_SIZE else 1
    n_y = max(1, (height - _PATCH_SIZE) // _PATCH_STRIDE + 1) if height >= _PATCH_SIZE else 1
    return {
        "image_width": width,
        "image_height": height,
        "n_x": n_x,
        "n_y": n_y,
        "patch_size": _PATCH_SIZE,
        "stride": _PATCH_STRIDE,
    }


def _group_changed_patches(
    features_t1_path: str,
    features_t2_path: str,
    change_mask: list,
    max_groups: int = 4,
) -> list:
    """변화 패치들의 change vector(Δv)를 비지도 군집해 패치별 그룹 id를 반환한다.

    비지도 스크리닝 UX의 재료: "비슷한 변화끼리 묶어서" 보여주면 사용자가 그룹
    단위로 훑고 무관한 변화(예: 계절 식생)를 통째로 제외하며 볼 수 있다.
    그룹은 익명(0,1,2…) — 의미 라벨을 붙이지 않는다(03 정책). 미변화 패치는 -1.
    실패해도 파이프라인을 죽이지 않는다(그룹핑은 부가 신호).
    """
    try:
        from sklearn.cluster import KMeans

        f1 = np.load(features_t1_path)
        f2 = np.load(features_t2_path)
        n = min(len(f1), len(f2), len(change_mask))
        changed_idx = [i for i in range(n) if change_mask[i]]

        groups = [-1] * len(change_mask)
        if len(changed_idx) == 0:
            return groups
        # 변화 패치 3개당 그룹 1개꼴, 최대 max_groups — 소수 변화에 그룹이 난립하지 않게
        k = min(max_groups, max(1, len(changed_idx) // 3))
        if k == 1:
            for i in changed_idx:
                groups[i] = 0
            return groups

        delta = f2[changed_idx] - f1[changed_idx]
        labels = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(delta)
        # 그룹 번호를 크기순(큰 그룹=0)으로 재부여 — 화면 범례가 매번 안정적이게
        order = {g: r for r, g in enumerate(
            sorted(set(labels), key=lambda g: -int((labels == g).sum()))
        )}
        for i, lab in zip(changed_idx, labels):
            groups[i] = order[int(lab)]
        return groups
    except Exception as e:
        logger.error("변화 그룹핑 실패(비치명적): %s", e, exc_info=True)
        return [0 if v else -1 for v in change_mask]


def _render_change_visualization(
    image_t1_path: str,
    image_t2_path: str,
    change_mask: list,
    output_dir: str,
) -> dict:
    """T1/T2 원본과 변화 패치를 강조한 오버레이 이미지를 생성해 저장한다.

    통계 숫자만으로는 "무엇이 비교됐는지" 검증할 수 없다는 문제를 해소하기 위해,
    사용자가 실제로 두 시점 이미지와 변화 위치를 눈으로 확인할 수 있게 한다.
    실패해도 파이프라인 전체를 죽이지 않는다(시각화는 부가 기능).

    Returns:
        {"t1_image_url", "t2_image_url", "overlay_image_url"} — UPLOAD_PATH 기준
        상대 URL(/uploads/results/{job_id}/...). output_dir가 RESULTS_DIR/{job_id}
        규약을 따른다는 전제(vq_api.py) 하에 job_id를 basename으로 역산한다.
    """
    try:
        img_t1 = Image.open(image_t1_path).convert("RGB")
        img_t2 = Image.open(image_t2_path).convert("RGB")

        t1_out = os.path.join(output_dir, "t1.png")
        t2_out = os.path.join(output_dir, "t2.png")
        overlay_out = os.path.join(output_dir, "overlay.png")
        img_t1.save(t1_out)
        img_t2.save(t2_out)

        # 패치 격자 재구성 (feature_extractor와 동일한 y→x 순회 순서 — _patch_grid 단일 소스)
        w, h = img_t2.size
        grid = _patch_grid(w, h)
        n_x, n_y = grid["n_x"], grid["n_y"]

        overlay = img_t2.convert("RGBA")
        draw_layer = Image.new("RGBA", overlay.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(draw_layer)

        idx = 0
        for row in range(n_y):
            for col in range(n_x):
                if idx < len(change_mask) and change_mask[idx]:
                    x0, y0 = col * _PATCH_STRIDE, row * _PATCH_STRIDE
                    x1, y1 = min(x0 + _PATCH_SIZE, w), min(y0 + _PATCH_SIZE, h)
                    draw.rectangle([x0, y0, x1, y1], fill=(239, 68, 68, 90), outline=(239, 68, 68, 220), width=3)
                idx += 1

        overlay = Image.alpha_composite(overlay, draw_layer).convert("RGB")
        overlay.save(overlay_out)

        job_id = os.path.basename(os.path.normpath(output_dir))
        base_url = f"/uploads/results/{job_id}"
        return {
            "t1_image_url": f"{base_url}/t1.png",
            "t2_image_url": f"{base_url}/t2.png",
            "overlay_image_url": f"{base_url}/overlay.png",
        }
    except Exception as e:
        logger.error("변화 시각화 이미지 생성 실패: %s", e, exc_info=True)
        return {"t1_image_url": None, "t2_image_url": None, "overlay_image_url": None}


def _run_vq_change_detection(
    features_t1_path: str,
    features_t2_path: str,
    output_dir: str,
    progress_cb: ProgressCallback = None,
) -> dict:
    """VQ 코드북을 **변화 판정의 주역**으로 쓰는 변화탐지 (프로젝트 이름값 실현).

    구 방식은 change_mask를 CVA(‖v2−v1‖ 임계)로만 정하고 코드북은 만들어두고
    안 썼다(장식). 여기서는:
      1) 두 시점 특징을 합쳐 **shared 코드북**(작은 K = land-cover 어휘) 학습
      2) 각 패치를 두 시점에서 최근접 코드워드로 **양자화**(VQ)
      3) **코드워드 할당이 바뀐 패치 = 변화** ← 판정의 주역이 코드북
    CVA 크기(change_magnitudes)는 판정이 아니라 인스펙터의 강도축(순위·슬라이더)으로만.

    K는 패치 수보다 작아야 할당변화가 의미있다(K≈패치수면 모든 패치가 고유 코드워드라
    항상 "변화"로 잡힘). 그래서 land-cover 어휘 크기로 min(16, n-1)로 고정한다.
    """
    _report(progress_cb, 10, "특징 로드...")
    f1 = np.load(features_t1_path)
    f2 = np.load(features_t2_path)
    n = min(len(f1), len(f2))
    f1, f2 = f1[:n], f2[:n]

    # shared 코드북(작은 land-cover 어휘). n<3이면 코드북이 무의미 → 폴백은 아래.
    vq_k = max(2, min(16, n - 1)) if n >= 3 else 1

    _report(progress_cb, 40, "shared VQ 코드북 학습 + 양자화...")
    if vq_k >= 2:
        vq = VQCodebookGenerator(codebook_size=vq_k, use_minibatch=False)
        vq.generate(np.vstack([f1, f2]))
        assign_t1 = vq.quantize(f1)
        assign_t2 = vq.quantize(f2)
        change_mask = (assign_t1 != assign_t2)
    else:
        # 패치가 너무 적어 코드북이 성립 안 됨 — 전부 미변화로(오탐 방지)
        assign_t1 = np.zeros(n, dtype=int)
        assign_t2 = np.zeros(n, dtype=int)
        change_mask = np.zeros(n, dtype=bool)

    # CVA 크기(보조 강도축) — 판정엔 안 쓰고 순위/슬라이더에만
    change_magnitudes = np.linalg.norm(f2 - f1, axis=1)

    # 코드워드 전이(from→to)별 익명 그룹 — VQ-네이티브 그룹핑(구 Δv-KMeans 대체).
    # 같은 전이(예: 코드워드 3→5)를 한 그룹으로, 빈도순 상위 3개 + "기타"(3)로 캡.
    from collections import Counter
    groups = [-1] * n
    changed_idx = [i for i in range(n) if bool(change_mask[i])]
    if changed_idx:
        pair = {i: (int(assign_t1[i]), int(assign_t2[i])) for i in changed_idx}
        ranked = [p for p, _ in Counter(pair.values()).most_common()]
        order = {p: (r if r < 3 else 3) for r, p in enumerate(ranked)}
        for i in changed_idx:
            groups[i] = order[pair[i]]

    n_changed = int(change_mask.sum())
    mags_changed = change_magnitudes[change_mask] if n_changed else np.array([])
    # 슬라이더 기본값 = 변화 패치 중 최소 강도(=전체 VQ-변화 패치를 다 보여줌)
    threshold = float(mags_changed.min()) if n_changed else 0.0
    statistics = {
        "n_total": n,
        "n_changed": n_changed,
        "n_unchanged": n - n_changed,
        "change_percentage": (100.0 * n_changed / n) if n else 0.0,
        "threshold": threshold,  # 프론트 계약(statistics.threshold) 유지
        "codebook_size": int(vq_k),
        "n_codewords_t1": int(len(np.unique(assign_t1))),
        "n_codewords_t2": int(len(np.unique(assign_t2))),
    }

    result = {
        "status": "completed",
        "statistics": statistics,
        "threshold": threshold,
        "change_mask": [bool(v) for v in change_mask],
        "change_magnitudes": [float(v) for v in change_magnitudes],
        "patch_groups": groups,
        # 패치별 코드워드 할당(익명) — "3→5 전이" 같은 검증에 활용 가능
        "codeword_t1": [int(v) for v in assign_t1],
        "codeword_t2": [int(v) for v in assign_t2],
    }
    # 결과 저장(디버그/재현)
    try:
        with open(os.path.join(output_dir, "change_result.pkl"), "wb") as fh:
            pickle.dump(result, fh)
    except Exception as e:
        logger.warning("change_result 저장 실패(비치명적): %s", e)

    _report(progress_cb, 100, "완료")
    return result


def _run_timeseries_pipeline(frames: list, output_dir: str, progress_cb: ProgressCallback = None) -> dict:
    """**연속(다시점) VQ 시계열 변화탐지.** frames=[{"year","path"}...] (연도순).

    2점 파이프라인의 shared 코드북을 N점으로 확장: 모든 연도 특징을 합쳐 코드북 1개를
    학습하고 각 연도를 양자화해, 패치별 **코드워드 시퀀스**를 얻는다. 각 프레임의 변화는
    "기준(첫 연도) 대비 코드워드가 바뀐 패치"로, 타임라인을 훑으면 변화가 누적돼 보인다.
    change_year[i] = 그 패치가 기준과 처음 달라진 연도(없으면 null).
    """
    import numpy as np
    n_frames = len(frames)
    feats = []
    for idx, fr in enumerate(frames):
        _report(progress_cb, int(5 + 55 * idx / n_frames), f"{fr['year']}년 특징 추출...")
        fp = os.path.join(output_dir, f"features_{fr['year']}.npy")
        _run_extract_features(fr["path"], fp)
        feats.append(np.load(fp))

    n = min(len(f) for f in feats)
    feats = [f[:n] for f in feats]

    _report(progress_cb, 70, "shared VQ 코드북 학습 + 양자화...")
    vq_k = max(2, min(16, n - 1)) if n >= 3 else 1
    if vq_k >= 2:
        vq = VQCodebookGenerator(codebook_size=vq_k, use_minibatch=False)
        vq.generate(np.vstack(feats))
        assigns = [vq.quantize(f) for f in feats]   # [n_frames][n]
    else:
        assigns = [np.zeros(n, dtype=int) for _ in feats]

    base = assigns[0]
    job_id = os.path.basename(os.path.normpath(output_dir))
    frame_out = []
    for k, fr in enumerate(frames):
        changed = (assigns[k] != base)
        frame_out.append({
            "year": fr["year"],
            "image_url": f"/uploads/results/{job_id}/frame_{fr['year']}.png",
            "change_mask": [bool(v) for v in changed],
            "n_changed": int(changed.sum()),
            "mean_cloud": (fr.get("meta") or {}).get("mean_cloud"),
        })

    # 패치별 "기준과 처음 달라진 연도" (없으면 None)
    change_year = []
    for i in range(n):
        yr = None
        for k in range(1, n_frames):
            if assigns[k][i] != base[i]:
                yr = frames[k]["year"]; break
        change_year.append(yr)

    try:
        with Image.open(frames[0]["path"]) as _img:
            grid = _patch_grid(*_img.size)
    except Exception as e:
        logger.error("패치 격자 메타 실패(비치명): %s", e); grid = None

    _report(progress_cb, 100, "완료")
    return {
        "status": "completed",
        "years": [fr["year"] for fr in frames],
        "frames": frame_out,
        "change_year": change_year,
        "patch_grid": grid,
        "codebook_size": int(vq_k),
    }


def _run_full_pipeline(
    image_t1_path: str,
    image_t2_path: str,
    output_dir: str,
    codebook_size: int = 256,
    n_clusters: int = 8,
    progress_cb: ProgressCallback = None,
) -> dict:
    """전체 VQ Clustering 파이프라인 (순수 함수, celery 무관)

    각 단계는 progress_cb를 통해 파이프라인 전체 기준(0~100)의 진행률을 보고한다.
    """
    os.makedirs(output_dir, exist_ok=True)

    def stage(base: int, span: int, label: str) -> ProgressCallback:
        """하위 단계의 0~100 진행률을 파이프라인 전체의 [base, base+span] 구간으로 매핑.

        상태 문구는 하위 단계의 영어 마이크로 상태("Loading features...")가 아니라
        파이프라인 단계명(label, 한국어)을 유지한다 — 화면에 그대로 노출되는 값(28-3).
        """
        def _cb(p: int, status: str) -> None:
            _report(progress_cb, base + int(span * p / 100), label)
        return _cb

    # 1. 특징 추출 (t1)
    _report(progress_cb, 5, "시점1(과거) 특징 추출 중 (ResNet50)...")
    features_t1_path = os.path.join(output_dir, "features_t1.npy")
    _run_extract_features(image_t1_path, features_t1_path, progress_cb=stage(5, 15, "시점1(과거) 특징 추출 중 (ResNet50)..."))

    # 2. 특징 추출 (t2)
    _report(progress_cb, 20, "시점2(현재) 특징 추출 중 (ResNet50)...")
    features_t2_path = os.path.join(output_dir, "features_t2.npy")
    _run_extract_features(image_t2_path, features_t2_path, progress_cb=stage(20, 15, "시점2(현재) 특징 추출 중 (ResNet50)..."))

    # 3. VQ 코드북 변화탐지 — shared 코드북 학습 → 양자화 → 코드워드 할당 변화 = 변화.
    #    (구 방식: 시점별 코드북 따로 만들고 CVA로만 판정 → 코드북이 판정에 미사용.
    #     이제 코드북이 판정 주역. FR-402 재설계 2026-07-18)
    _report(progress_cb, 40, "VQ 코드북 변화탐지 (양자화 기반)...")
    change_result = _run_vq_change_detection(
        features_t1_path, features_t2_path, output_dir,
        progress_cb=stage(40, 35, "VQ 코드북 변화탐지 (양자화 기반)..."),
    )

    # 6. 클러스터링 (optional, t1 기준)
    _report(progress_cb, 80, "클러스터링 중...")
    cluster_result_path = os.path.join(output_dir, "cluster_result.pkl")
    cluster_result = _run_clustering(
        features_t1_path, cluster_result_path, n_clusters,
        progress_cb=stage(80, 15, "클러스터링 중..."),
    )

    # 7. 비교 이미지 시각화(T1/T2/변화 오버레이) — 통계만으론 무엇이 비교됐는지
    # 검증할 수 없다는 문제 해소. 실패해도 파이프라인 결과 자체는 살린다.
    visualization = _render_change_visualization(
        image_t1_path, image_t2_path, change_result.get("change_mask", []), output_dir,
    )

    # 패치 격자 메타 — 클라이언트 오버레이 렌더용(민감도 슬라이더·그룹 토글).
    try:
        with Image.open(image_t2_path) as _img:
            patch_grid = _patch_grid(*_img.size)
    except Exception as e:
        logger.error("패치 격자 메타 생성 실패(비치명적): %s", e)
        patch_grid = None

    _report(progress_cb, 100, "완료")

    return {
        "status": "completed",
        "output_dir": output_dir,
        "change_result": change_result,
        "cluster_result": cluster_result,
        "visualization": visualization,
        "patch_grid": patch_grid,
    }


# ---------------------------------------------------------------------------
# Celery 태스크 (얇은 wrapper) — 위 plain 함수를 호출하고, 자기 자신의
# update_state로만 진행률을 보고한다. 태스크가 다른 태스크를 직접 함수
# 호출하는 패턴은 여기서 전면 제거했다.
# ---------------------------------------------------------------------------


def _fail(self: Task, exc: Exception) -> None:
    """실패 시 상태 meta를 JSON 직렬화 가능한 형태로 남긴다."""
    logger.exception("Task %s failed", self.request.id)
    self.update_state(state="FAILURE", meta={"error": str(exc), "exc_type": type(exc).__name__})


@celery_app.task(bind=True, name="vq.extract_features")
def extract_features_task(self: Task, image_path: str, output_path: str):
    """특징 벡터 추출 작업"""
    try:
        return _run_extract_features(
            image_path,
            output_path,
            progress_cb=lambda p, s: self.update_state(state="PROGRESS", meta={"progress": p, "status": s}),
        )
    except Exception as e:
        _fail(self, e)
        raise RuntimeError(str(e)) from e


@celery_app.task(bind=True, name="vq.generate_codebook")
def generate_codebook_task(
    self: Task,
    features_path: str,
    codebook_path: str,
    codebook_size: int = 256,
):
    """VQ 코드북 생성 작업"""
    try:
        return _run_generate_codebook(
            features_path,
            codebook_path,
            codebook_size,
            progress_cb=lambda p, s: self.update_state(state="PROGRESS", meta={"progress": p, "status": s}),
        )
    except Exception as e:
        _fail(self, e)
        raise RuntimeError(str(e)) from e


@celery_app.task(bind=True, name="vq.cluster")
def clustering_task(
    self: Task,
    features_path: str,
    output_path: str,
    n_clusters: int = 8,
    algorithm: str = "kmeans",
):
    """클러스터링 작업"""
    try:
        return _run_clustering(
            features_path,
            output_path,
            n_clusters,
            algorithm,
            progress_cb=lambda p, s: self.update_state(state="PROGRESS", meta={"progress": p, "status": s}),
        )
    except Exception as e:
        _fail(self, e)
        raise RuntimeError(str(e)) from e


@celery_app.task(bind=True, name="vq.detect_changes")
def detect_changes_task(
    self: Task,
    features_t1_path: str,
    features_t2_path: str,
    codebook_t1_path: str,
    codebook_t2_path: str,
    output_path: str,
    threshold_method: str = "otsu",
):
    """변화 탐지 작업"""
    try:
        return _run_detect_changes(
            features_t1_path,
            features_t2_path,
            codebook_t1_path,
            codebook_t2_path,
            output_path,
            threshold_method,
            progress_cb=lambda p, s: self.update_state(state="PROGRESS", meta={"progress": p, "status": s}),
        )
    except Exception as e:
        _fail(self, e)
        raise RuntimeError(str(e)) from e


@celery_app.task(bind=True, name="vq.full_pipeline")
def full_vq_pipeline_task(
    self: Task,
    image_t1_path: str,
    image_t2_path: str,
    output_dir: str,
    codebook_size: int = 256,
    n_clusters: int = 8,
):
    """전체 VQ Clustering 파이프라인 (t1, t2 비교)"""
    try:
        return _run_full_pipeline(
            image_t1_path,
            image_t2_path,
            output_dir,
            codebook_size,
            n_clusters,
            progress_cb=lambda p, s: self.update_state(state="PROGRESS", meta={"progress": p, "status": s}),
        )
    except Exception as e:
        _fail(self, e)
        raise RuntimeError(str(e)) from e


@celery_app.task(bind=True, name="vq.location_pipeline")
def location_vq_pipeline_task(
    self: Task,
    latitude: float,
    longitude: float,
    buffer_km: float,
    past_date: str,
    current_date: str,
    output_dir: str,
    codebook_size: int = 256,
    n_clusters: int = 8,
):
    """좌표+과거날짜 → GEE 두 시점 다운로드 → VQ 파이프라인 → 위치/날짜 메타 병합.

    프로젝트 본래 목적(같은 지점의 시계열 변화탐지)을 복원하는 진입점.
    GEE 다운로드(0~25%) 후 기존 _run_full_pipeline(25~100%)을 그대로 재사용한다.
    """
    def report(p, s):
        self.update_state(state="PROGRESS", meta={"progress": p, "status": s})

    try:
        os.makedirs(output_dir, exist_ok=True)
        report(3, "위성영상 취득 준비...")

        # celery 워커에서 GEE 초기화 (backend와 동일 코드/키)
        from app.services.gee_service import GEEService
        gee = GEEService()
        if not gee.initialized:
            raise RuntimeError("GEE 초기화 실패 — 서비스 계정 키를 확인하세요")

        report(8, "두 시점 위성영상 다운로드 중 (GEE)...")
        pair = gee.download_timeseries_pair(
            latitude=latitude,
            longitude=longitude,
            buffer_km=buffer_km,
            past_date=past_date,
            current_date=current_date,
            out_dir=output_dir,
            dimensions=1024,
        )
        if not pair.get("success"):
            raise RuntimeError(pair.get("message", "위성영상 다운로드 실패"))

        report(25, "VQ 변화탐지 파이프라인 실행...")

        # 25~100% 구간에 파이프라인 진행률 매핑
        def pipe_cb(p, s):
            report(25 + int(75 * p / 100), s)

        result = _run_full_pipeline(
            pair["t1_path"],
            pair["t2_path"],
            output_dir,
            codebook_size,
            n_clusters,
            progress_cb=pipe_cb,
        )

        # 실제 취득 컨텍스트(위치·시점·타일)를 결과에 병합 — "어디서 무엇을 비교했나"
        result["location"] = {
            "latitude": latitude,
            "longitude": longitude,
            "buffer_km": buffer_km,
            "past_date": past_date,
            # T2 실제 시점 — 계절 정합 시 요청의 빈 값이 아니라 pair가 계산한 같은-계절 날짜
            "current_date": pair.get("current_date") or current_date,
            "season_aligned": pair.get("season_aligned", False),
            "radiometric_normalized": pair.get("radiometric_normalized", False),
            "t1_meta": pair.get("t1_meta"),
            "t2_meta": pair.get("t2_meta"),
            "t1_tile_url": pair.get("t1_tile_url"),
            "t2_tile_url": pair.get("t2_tile_url"),
            "diff_tile_url": pair.get("diff_tile_url"),
            "bounds": pair.get("bounds"),
        }

        # 의미 라벨(YOLO 교차참조): VQ 변화 패치 중 실제 태양광이 있는 곳을 표시.
        # VWorld 고해상에 YOLO를 돌려 패널 좌표를 얻고(각 모델 native 해상도), 그 좌표를
        # VQ 패치 격자에 매핑한다. best-effort — 실패해도 VQ 결과는 그대로 반환.
        try:
            report(96, "태양광 교차참조 (YOLO)...")
            from app.services.solar_detection_service import detect_solar_geo

            grid = result.get("patch_grid") or {}
            cr = result.get("change_result") or {}
            mask = cr.get("change_mask") or []
            bounds = pair.get("bounds")
            W, H = grid.get("image_width"), grid.get("image_height")
            n_x, ps, st = grid.get("n_x"), grid.get("patch_size"), grid.get("stride")

            solar_patches: list = []
            solar_count = 0
            if bounds and W and n_x and mask:
                ring = bounds[0] if bounds and isinstance(bounds[0][0], (list, tuple)) else bounds
                lngs = [p[0] for p in ring]; lats = [p[1] for p in ring]
                west, east, south, north = min(lngs), max(lngs), min(lats), max(lats)

                panels = detect_solar_geo(latitude, longitude, buffer_km)
                solar_count = len(panels)
                changed = {i for i, v in enumerate(mask) if v}
                hit = set()
                for pnl in panels:
                    if east == west or north == south:
                        break
                    px = (pnl["longitude"] - west) / (east - west) * W
                    py = (north - pnl["latitude"]) / (north - south) * H
                    for i in changed:
                        col, row = i % n_x, i // n_x
                        x0, y0 = col * st, row * st
                        if x0 <= px <= x0 + ps and y0 <= py <= y0 + ps:
                            hit.add(i)
                solar_patches = sorted(hit)

            result["location"]["solar_panel_count"] = solar_count
            result["location"]["solar_changed_patches"] = solar_patches
            logger.info("YOLO 교차참조: 패널 %d개, 변화∩태양광 패치 %d개", solar_count, len(solar_patches))
        except Exception as e:
            logger.warning("YOLO 교차참조 실패(비치명적): %s", e)

        # 결과 영속화 — 새로고침 후에도 남고, "최근 분석" 목록으로 즉시 재표시.
        # 이미지는 uploads/results/{job_id}에 이미 영속되므로 결과 JSON만 저장. best-effort.
        try:
            from app.core.database import SessionLocal
            from app.models.vq_analysis_run import VqAnalysisRun
            loc = result["location"]
            stats = (result.get("change_result") or {}).get("statistics") or {}
            db = SessionLocal()
            try:
                db.add(VqAnalysisRun(
                    latitude=latitude, longitude=longitude, buffer_km=buffer_km,
                    past_date=past_date, t2_date=loc.get("current_date"),
                    season_aligned=bool(loc.get("season_aligned")),
                    n_total=stats.get("n_total"), n_changed=stats.get("n_changed"),
                    change_percentage=stats.get("change_percentage"),
                    solar_panel_count=loc.get("solar_panel_count"),
                    n_solar_patches=len(loc.get("solar_changed_patches") or []),
                    job_id=os.path.basename(os.path.normpath(output_dir)),
                    result_json=result,
                ))
                db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.warning("VQ 분석 결과 영속화 실패(비치명적): %s", e)

        return result
    except Exception as e:
        _fail(self, e)
        raise RuntimeError(str(e)) from e


@celery_app.task(bind=True, name="vq.timeseries_pipeline")
def timeseries_vq_pipeline_task(
    self: Task,
    latitude: float,
    longitude: float,
    buffer_km: float,
    start_year: int,
    end_year: int,
    month: int,
    output_dir: str,
):
    """연속(다시점) VQ 시계열 — 여러 연도 같은 계절을 받아 shared 코드북 시퀀스 분석."""
    def report(p, s):
        self.update_state(state="PROGRESS", meta={"progress": p, "status": s})
    try:
        os.makedirs(output_dir, exist_ok=True)
        years = list(range(int(start_year), int(end_year) + 1))
        report(5, f"{len(years)}개 연도 위성영상 다운로드 (GEE)...")
        from app.services.gee_service import GEEService
        gee = GEEService()
        if not gee.initialized:
            raise RuntimeError("GEE 초기화 실패")
        seq = gee.download_timeseries_sequence(latitude, longitude, buffer_km, years, month, output_dir, 1024)
        if not seq.get("success"):
            raise RuntimeError(seq.get("message", "연속 시계열 다운로드 실패"))

        report(30, "연속 VQ 시계열 분석...")
        ts = _run_timeseries_pipeline(
            seq["frames"], output_dir,
            progress_cb=lambda p, s: report(30 + int(65 * p / 100), s),
        )
        result = {
            "status": "completed",
            "output_dir": output_dir,
            "timeseries": ts,
            "location": {
                "latitude": latitude, "longitude": longitude, "buffer_km": buffer_km,
                "month": month, "bounds": seq.get("bounds"),
            },
        }

        # 영속화(reuse runs 테이블) — 연속 시계열도 최근 분석에 남긴다
        try:
            from app.core.database import SessionLocal
            from app.models.vq_analysis_run import VqAnalysisRun
            yrs = ts.get("years") or []
            last = (ts.get("frames") or [{}])[-1]
            db = SessionLocal()
            try:
                db.add(VqAnalysisRun(
                    latitude=latitude, longitude=longitude, buffer_km=buffer_km,
                    past_date=str(yrs[0]) if yrs else None, t2_date=str(yrs[-1]) if yrs else None,
                    season_aligned=True,
                    n_total=len((last.get("change_mask") or [])), n_changed=last.get("n_changed"),
                    change_percentage=None, solar_panel_count=None, n_solar_patches=None,
                    job_id=os.path.basename(os.path.normpath(output_dir)),
                    result_json=result,
                ))
                db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.warning("연속 시계열 영속화 실패(비치명): %s", e)

        return result
    except Exception as e:
        _fail(self, e)
        raise RuntimeError(str(e)) from e
