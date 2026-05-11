"""Pluggable model backend.

Default backend: ultralytics YOLOv5n. License = AGPL-3.0. Self-hosted internal
use does not trigger AGPL distribution clauses; if you ship as SaaS or
redistribute binaries, audit license obligations first.

Swap path: implement `ModelBackend` against torchvision FasterRCNN or detectron2
for BSD/Apache-licensed alternatives.
"""
from __future__ import annotations

import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from .db import DATA_DIR

MODELS_DIR = DATA_DIR.parent / "models"
MODELS_DIR.mkdir(exist_ok=True)
RUNS_DIR = DATA_DIR.parent / "runs"
RUNS_DIR.mkdir(exist_ok=True)


@dataclass
class Prediction:
    cx: float
    cy: float
    w: float
    h: float
    confidence: float
    class_idx: int


def _have_ultralytics() -> bool:
    try:
        import ultralytics  # noqa: F401

        return True
    except Exception:
        return False


def _dataset_yaml(dataset_dir: Path, class_name: str) -> Path:
    yaml_path = dataset_dir / "dataset.yaml"
    config = {
        "path": str(dataset_dir.resolve()),
        "train": "images/train",
        "val": "images/val",
        "names": {0: class_name},
    }
    yaml_path.write_text(yaml.safe_dump(config))
    return yaml_path


def export_yolo_layout(
    dataset_dir: Path,
    images: list[tuple[Path, list[tuple[float, float, float, float, int]]]],
    val_split: float = 0.2,
) -> Path:
    """Write images + labels into ultralytics layout under dataset_dir.

    images: list of (source_image_path, list of (cx, cy, w, h, class_idx))
    """
    for split in ("train", "val"):
        (dataset_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (dataset_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    n = len(images)
    val_count = max(1, int(n * val_split)) if n > 1 else 0

    for i, (src, boxes) in enumerate(images):
        split = "val" if i < val_count else "train"
        img_dst = dataset_dir / "images" / split / src.name
        label_dst = dataset_dir / "labels" / split / f"{src.stem}.txt"

        if not img_dst.exists():
            shutil.copy2(src, img_dst)

        lines = [
            f"{cls} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"
            for (cx, cy, w, h, cls) in boxes
        ]
        label_dst.write_text("\n".join(lines))

    return dataset_dir


class ModelBackend:
    def train(
        self,
        dataset_yaml: Path,
        epochs: int,
        img_size: int,
        project_dir: Path,
        run_name: str,
    ) -> Optional[Path]:
        raise NotImplementedError

    def predict(
        self,
        weights: Path,
        image_path: Path,
        conf_threshold: float,
    ) -> list[Prediction]:
        raise NotImplementedError


class UltralyticsBackend(ModelBackend):
    """YOLOv5n via ultralytics. AGPL-3.0."""

    BASE_WEIGHTS = "yolov5nu.pt"  # ultralytics-format YOLOv5n

    def train(
        self,
        dataset_yaml: Path,
        epochs: int,
        img_size: int,
        project_dir: Path,
        run_name: str,
    ) -> Optional[Path]:
        from ultralytics import YOLO

        model = YOLO(self.BASE_WEIGHTS)
        result = model.train(
            data=str(dataset_yaml),
            epochs=epochs,
            imgsz=img_size,
            project=str(project_dir),
            name=run_name,
            exist_ok=True,
            verbose=False,
            patience=10,
        )
        # result.save_dir holds the run directory; best weights at weights/best.pt
        save_dir = Path(result.save_dir) if hasattr(result, "save_dir") else project_dir / run_name
        best = save_dir / "weights" / "best.pt"
        return best if best.exists() else None

    def predict(
        self,
        weights: Path,
        image_path: Path,
        conf_threshold: float,
    ) -> list[Prediction]:
        from ultralytics import YOLO

        model = YOLO(str(weights))
        results = model.predict(
            source=str(image_path),
            conf=conf_threshold,
            verbose=False,
        )
        preds: list[Prediction] = []
        for r in results:
            if r.boxes is None or len(r.boxes) == 0:
                continue
            xywhn = r.boxes.xywhn.cpu().numpy()  # normalized cx cy w h
            confs = r.boxes.conf.cpu().numpy()
            cls = r.boxes.cls.cpu().numpy().astype(int)
            for (cx, cy, w, h), conf, c in zip(xywhn, confs, cls):
                preds.append(
                    Prediction(
                        cx=float(cx),
                        cy=float(cy),
                        w=float(w),
                        h=float(h),
                        confidence=float(conf),
                        class_idx=int(c),
                    )
                )
        return preds


class StubBackend(ModelBackend):
    """Fallback when ultralytics is not installed. Lets the API stay alive."""

    def train(self, *args, **kwargs) -> Optional[Path]:
        raise RuntimeError(
            "Model backend not installed. Run: pip install ultralytics"
        )

    def predict(self, *args, **kwargs) -> list[Prediction]:
        return []


def get_backend() -> ModelBackend:
    return UltralyticsBackend() if _have_ultralytics() else StubBackend()


def uncertainty_score(predictions: list[Prediction]) -> float:
    """Lower = more uncertain = higher priority for review queue.

    For an image with no detections we return 0.0 (most uncertain).
    Otherwise we use min-confidence across detections so a single weak box
    surfaces the whole image.
    """
    if not predictions:
        return 0.0
    return min(p.confidence for p in predictions)


def margin_uncertainty(predictions: list[Prediction]) -> float:
    """Alternative: 1 - mean(confidence). Higher = more uncertain.

    Kept for callers that want a different ranking.
    """
    if not predictions:
        return 1.0
    mean_conf = sum(p.confidence for p in predictions) / len(predictions)
    return 1.0 - mean_conf


def entropy_from_confidences(predictions: list[Prediction]) -> float:
    """Binary entropy across each detection's confidence, averaged."""
    if not predictions:
        return 1.0
    entropies = []
    for p in predictions:
        c = min(max(p.confidence, 1e-6), 1 - 1e-6)
        h = -(c * math.log2(c) + (1 - c) * math.log2(1 - c))
        entropies.append(h)
    return sum(entropies) / len(entropies)
