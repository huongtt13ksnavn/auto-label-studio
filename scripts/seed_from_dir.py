"""Seed a dataset from a local image directory.

Two modes:
  - raw images only: status="pending", user labels in UI
  - YOLO-labeled: status="labeled", labels read from sibling labels/ dir

Usage:

    backend\.venv\Scripts\python.exe scripts\seed_from_dir.py \
        --name my-dataset \
        --classes cat,dog,bird \
        --images "C:\path\to\images" \
        [--labels "C:\path\to\labels"]

If --labels is omitted, images are inserted as pending (unlabeled).
If provided, expects YOLO txt files matching image stems
(`foo.jpg` -> `foo.txt`, lines: `class_idx cx cy w h`, normalized).
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import models  # noqa: E402
from backend.db import SessionLocal, init_db  # noqa: E402
from backend.routes import IMAGES_DIR  # noqa: E402

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def parse_label(path: Path) -> list[tuple[int, float, float, float, float]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        parts = line.strip().split()
        if len(parts) < 5:
            continue
        try:
            cls = int(float(parts[0]))
            cx, cy, w, h = (float(parts[i]) for i in (1, 2, 3, 4))
        except ValueError:
            continue
        out.append((cls, cx, cy, w, h))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="Dataset name (unique)")
    ap.add_argument("--classes", required=True,
                    help="Comma-separated class names, e.g. cat,dog,bird")
    ap.add_argument("--images", required=True, help="Path to image directory")
    ap.add_argument("--labels", default=None,
                    help="Optional path to YOLO labels directory")
    ap.add_argument("--replace", action="store_true",
                    help="Drop existing dataset with same name first")
    args = ap.parse_args()

    init_db()

    classes = [c.strip() for c in args.classes.split(",") if c.strip()]
    if not classes:
        raise SystemExit("--classes must contain at least one name")

    img_dir = Path(args.images)
    if not img_dir.is_dir():
        raise SystemExit(f"Images dir not found: {img_dir}")

    label_dir = Path(args.labels) if args.labels else None
    if label_dir and not label_dir.is_dir():
        raise SystemExit(f"Labels dir not found: {label_dir}")

    from PIL import Image as PILImage

    db = SessionLocal()
    try:
        existing = (
            db.query(models.Dataset)
            .filter(models.Dataset.name == args.name)
            .first()
        )
        if existing:
            if not args.replace:
                raise SystemExit(
                    f"Dataset '{args.name}' already exists (id={existing.id}). "
                    "Use --replace to drop and re-seed."
                )
            print(f"Replacing existing dataset id={existing.id}")
            shutil.rmtree(IMAGES_DIR / str(existing.id), ignore_errors=True)
            db.delete(existing)
            db.commit()

        ds = models.Dataset(name=args.name, class_names=classes)
        db.add(ds)
        db.commit()
        db.refresh(ds)
        print(f"Created dataset id={ds.id} '{ds.name}' "
              f"with {len(classes)} class(es)")

        dest = IMAGES_DIR / str(ds.id)
        dest.mkdir(parents=True, exist_ok=True)

        srcs = sorted(p for p in img_dir.iterdir() if p.suffix.lower() in IMG_EXTS)
        print(f"Found {len(srcs)} images")

        imported = 0
        labeled = 0
        for src in srcs:
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

            boxes: list[tuple[int, float, float, float, float]] = []
            if label_dir:
                boxes = parse_label(label_dir / f"{src.stem}.txt")
                for cls, *_ in boxes:
                    if cls >= len(classes):
                        raise SystemExit(
                            f"Label in {src.stem}.txt references class_idx "
                            f"{cls} but only {len(classes)} classes defined."
                        )

            status = "labeled" if boxes else "pending"
            img_row = models.Image(
                dataset_id=ds.id,
                filename=target.name,
                width=width,
                height=height,
                status=status,
                confidence=1.0 if boxes else None,
            )
            db.add(img_row)
            db.flush()

            for cls, cx, cy, w, h in boxes:
                db.add(models.Box(
                    image_id=img_row.id,
                    cx=cx, cy=cy, w=w, h=h,
                    confidence=None,
                    class_idx=cls,
                    source="human",
                ))
            imported += 1
            if boxes:
                labeled += 1

        db.commit()
        print(f"Imported {imported} images ({labeled} labeled, "
              f"{imported - labeled} pending)")
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
