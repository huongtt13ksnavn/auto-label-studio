"""Seed a labeled demo dataset from Ultralytics' COCO128 sample.

Run from the repo root with the backend venv python:

    backend\.venv\Scripts\python.exe scripts\seed_coco128.py

What it does:
  - Asks ultralytics to materialize the coco128 dataset (downloads the
    ~7MB zip on first run into the ultralytics datasets cache).
  - Creates (or replaces) a Dataset named "coco128-demo" with the full
    80-class COCO name list.
  - Copies every train image into data/images/{dataset_id}/.
  - Inserts Image rows (status="labeled", confidence=1.0) and Box rows
    parsed from the YOLO txt label files (source="human").

After seeding, launch the app with run.ps1 and click Train.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

# make `backend` importable when run from repo root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import models  # noqa: E402
from backend.db import SessionLocal, init_db  # noqa: E402
from backend.routes import IMAGES_DIR  # noqa: E402

DATASET_NAME = "coco128-demo"


def materialize_coco128() -> dict:
    """Use ultralytics to download + locate coco128. Returns its data dict."""
    try:
        from ultralytics.data.utils import check_det_dataset
    except Exception as exc:
        raise SystemExit(
            f"Could not import ultralytics ({exc}). "
            "Activate the backend venv first."
        )

    print("Resolving coco128 (downloads ~7MB on first run)...")
    data = check_det_dataset("coco128.yaml")
    print(f"  root: {data['path']}")
    print(f"  train: {data['train']}")
    print(f"  classes: {len(data['names'])}")
    return data


def parse_label_file(label_path: Path) -> list[tuple[int, float, float, float, float]]:
    """Read a YOLO txt label file -> [(class_idx, cx, cy, w, h), ...]."""
    if not label_path.exists():
        return []
    out: list[tuple[int, float, float, float, float]] = []
    for line in label_path.read_text().splitlines():
        parts = line.strip().split()
        if len(parts) < 5:
            continue
        try:
            cls = int(float(parts[0]))
            cx, cy, w, h = (float(parts[i]) for i in (1, 2, 3, 4))
        except ValueError:
            continue
        # clamp to [0,1] in case anything drifted past edges
        cx = min(max(cx, 0.0), 1.0)
        cy = min(max(cy, 0.0), 1.0)
        w = min(max(w, 0.0), 1.0)
        h = min(max(h, 0.0), 1.0)
        out.append((cls, cx, cy, w, h))
    return out


def main() -> int:
    init_db()
    data = materialize_coco128()

    root = Path(data["path"])
    train_spec = data["train"]
    images_dir = root / train_spec if not Path(train_spec).is_absolute() else Path(train_spec)
    if not images_dir.exists():
        # coco128's yaml lists train: images/train2017 but the unpacked dir is
        # often images/train2017 directly under root. Search if mismatch.
        candidates = list(root.glob("images/*"))
        if candidates:
            images_dir = candidates[0]
    print(f"  images dir: {images_dir}")

    # YOLO convention: labels dir mirrors images dir.
    labels_dir = Path(str(images_dir).replace("images", "labels", 1))
    print(f"  labels dir: {labels_dir}")
    if not labels_dir.exists():
        raise SystemExit(f"Labels dir missing: {labels_dir}")

    names_map: dict = data["names"]  # {idx: name}
    class_names = [names_map[i] for i in sorted(names_map)]

    db = SessionLocal()
    try:
        existing = (
            db.query(models.Dataset)
            .filter(models.Dataset.name == DATASET_NAME)
            .first()
        )
        if existing:
            print(f"Replacing existing dataset id={existing.id}")
            shutil.rmtree(IMAGES_DIR / str(existing.id), ignore_errors=True)
            db.delete(existing)
            db.commit()

        ds = models.Dataset(name=DATASET_NAME, class_names=class_names)
        db.add(ds)
        db.commit()
        db.refresh(ds)
        print(f"Created dataset id={ds.id} with {len(class_names)} classes")

        dest = IMAGES_DIR / str(ds.id)
        dest.mkdir(parents=True, exist_ok=True)

        img_paths = sorted(
            [p for p in images_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}]
        )
        print(f"Found {len(img_paths)} images")

        imported = 0
        skipped_no_labels = 0
        from PIL import Image as PILImage

        for src in img_paths:
            label_path = labels_dir / f"{src.stem}.txt"
            boxes = parse_label_file(label_path)
            if not boxes:
                skipped_no_labels += 1
                continue

            target = dest / src.name
            i = 1
            while target.exists():
                target = dest / f"{src.stem}_{i}{src.suffix}"
                i += 1
            shutil.copy2(src, target)

            try:
                with PILImage.open(target) as im:
                    width, height = im.size
            except Exception:
                target.unlink(missing_ok=True)
                continue

            img_row = models.Image(
                dataset_id=ds.id,
                filename=target.name,
                width=width,
                height=height,
                status="labeled",
                confidence=1.0,
            )
            db.add(img_row)
            db.flush()  # need img_row.id

            for cls, cx, cy, w, h in boxes:
                db.add(
                    models.Box(
                        image_id=img_row.id,
                        cx=cx,
                        cy=cy,
                        w=w,
                        h=h,
                        confidence=None,
                        class_idx=cls,
                        source="human",
                    )
                )
            imported += 1

        db.commit()
        print(f"Imported {imported} labeled images "
              f"(skipped {skipped_no_labels} with no labels)")
        print()
        print("Next steps:")
        print("  1. .\\run.ps1                 # start backend + frontend")
        print(f"  2. Open http://localhost:5173, pick '{DATASET_NAME}'")
        print("  3. Click Train (defaults: 20 epochs, 640px)")
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
