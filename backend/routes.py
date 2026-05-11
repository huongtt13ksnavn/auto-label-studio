from __future__ import annotations

import io
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse, StreamingResponse
from PIL import Image as PILImage
from sqlalchemy.orm import Session

from . import models, schemas
from .db import DATA_DIR, SessionLocal, get_db
from .ml import (
    Prediction,
    RUNS_DIR,
    export_yolo_layout,
    get_backend,
    uncertainty_score,
    _dataset_yaml,
)

router = APIRouter()

IMAGES_DIR = DATA_DIR / "images"
IMAGES_DIR.mkdir(exist_ok=True)
EXPORTS_DIR = DATA_DIR / "exports"
EXPORTS_DIR.mkdir(exist_ok=True)
TRAIN_DIRS = DATA_DIR / "train_layouts"
TRAIN_DIRS.mkdir(exist_ok=True)


# ----- datasets -----


@router.post("/datasets", response_model=schemas.DatasetOut)
def create_dataset(payload: schemas.DatasetCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Dataset).filter(models.Dataset.name == payload.name).first()
    if existing:
        raise HTTPException(400, f"Dataset '{payload.name}' already exists")
    ds = models.Dataset(name=payload.name, class_name=payload.class_name)
    db.add(ds)
    db.commit()
    db.refresh(ds)
    (IMAGES_DIR / str(ds.id)).mkdir(exist_ok=True)
    return _dataset_to_out(ds, db)


@router.get("/datasets", response_model=list[schemas.DatasetOut])
def list_datasets(db: Session = Depends(get_db)):
    rows = db.query(models.Dataset).order_by(models.Dataset.id.desc()).all()
    return [_dataset_to_out(r, db) for r in rows]


@router.get("/datasets/{dataset_id}", response_model=schemas.DatasetOut)
def get_dataset(dataset_id: int, db: Session = Depends(get_db)):
    ds = _require_dataset(db, dataset_id)
    return _dataset_to_out(ds, db)


def _dataset_to_out(ds: models.Dataset, db: Session) -> schemas.DatasetOut:
    image_count = db.query(models.Image).filter(models.Image.dataset_id == ds.id).count()
    labeled_count = (
        db.query(models.Image)
        .filter(
            models.Image.dataset_id == ds.id,
            models.Image.status.in_(["labeled", "reviewed"]),
        )
        .count()
    )
    return schemas.DatasetOut(
        id=ds.id,
        name=ds.name,
        class_name=ds.class_name,
        created_at=ds.created_at,
        image_count=image_count,
        labeled_count=labeled_count,
    )


# ----- image upload -----


@router.post("/datasets/{dataset_id}/upload", response_model=list[schemas.ImageOut])
async def upload_images(
    dataset_id: int,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    ds = _require_dataset(db, dataset_id)
    dest_dir = IMAGES_DIR / str(ds.id)
    dest_dir.mkdir(exist_ok=True)

    out: list[models.Image] = []
    for f in files:
        if not f.filename:
            continue
        target = dest_dir / Path(f.filename).name
        # avoid clobber
        i = 1
        while target.exists():
            target = dest_dir / f"{Path(f.filename).stem}_{i}{Path(f.filename).suffix}"
            i += 1

        with target.open("wb") as fp:
            shutil.copyfileobj(f.file, fp)

        try:
            with PILImage.open(target) as img:
                width, height = img.size
        except Exception:
            target.unlink(missing_ok=True)
            continue

        row = models.Image(
            dataset_id=ds.id,
            filename=target.name,
            width=width,
            height=height,
            status="pending",
        )
        db.add(row)
        out.append(row)

    db.commit()
    for r in out:
        db.refresh(r)
    return [_image_to_out(r) for r in out]


# ----- images -----


@router.get("/datasets/{dataset_id}/images", response_model=list[schemas.ImageOut])
def list_images(
    dataset_id: int,
    status: Optional[str] = None,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    _require_dataset(db, dataset_id)
    q = db.query(models.Image).filter(models.Image.dataset_id == dataset_id)
    if status:
        q = q.filter(models.Image.status == status)
    rows = q.order_by(models.Image.id).limit(limit).all()
    return [_image_to_out(r) for r in rows]


@router.get("/images/{image_id}", response_model=schemas.ImageOut)
def get_image(image_id: int, db: Session = Depends(get_db)):
    img = db.query(models.Image).get(image_id)
    if not img:
        raise HTTPException(404, "Image not found")
    return _image_to_out(img)


@router.get("/images/{image_id}/file")
def serve_image_file(image_id: int, db: Session = Depends(get_db)):
    img = db.query(models.Image).get(image_id)
    if not img:
        raise HTTPException(404, "Image not found")
    path = IMAGES_DIR / str(img.dataset_id) / img.filename
    if not path.exists():
        raise HTTPException(404, "Image file missing on disk")
    return FileResponse(path)


def _image_to_out(img: models.Image) -> schemas.ImageOut:
    return schemas.ImageOut(
        id=img.id,
        dataset_id=img.dataset_id,
        filename=img.filename,
        width=img.width,
        height=img.height,
        status=img.status,
        confidence=img.confidence,
        boxes=[
            schemas.BoxOut(
                id=b.id,
                cx=b.cx,
                cy=b.cy,
                w=b.w,
                h=b.h,
                class_idx=b.class_idx,
                confidence=b.confidence,
                source=b.source,
            )
            for b in img.boxes
        ],
    )


# ----- labels -----


@router.put("/images/{image_id}/labels", response_model=schemas.ImageOut)
def update_labels(
    image_id: int,
    payload: schemas.LabelUpdate,
    db: Session = Depends(get_db),
):
    img = db.query(models.Image).get(image_id)
    if not img:
        raise HTTPException(404, "Image not found")

    # replace boxes with submitted ones (simplest, no diff logic for MVP)
    for old in list(img.boxes):
        db.delete(old)
    for b in payload.boxes:
        db.add(
            models.Box(
                image_id=img.id,
                cx=b.cx,
                cy=b.cy,
                w=b.w,
                h=b.h,
                class_idx=b.class_idx,
                confidence=b.confidence,
                source=b.source,
            )
        )

    img.status = payload.status
    # human review wipes auto-confidence so it sorts to end of low-conf queue
    if payload.status in ("labeled", "reviewed"):
        img.confidence = 1.0
    db.commit()
    db.refresh(img)
    return _image_to_out(img)


# ----- training -----


@router.post("/datasets/{dataset_id}/train", response_model=schemas.TrainingRunOut)
def start_training(
    dataset_id: int,
    payload: schemas.TrainRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    ds = _require_dataset(db, dataset_id)

    labeled = (
        db.query(models.Image)
        .filter(
            models.Image.dataset_id == ds.id,
            models.Image.status.in_(["labeled", "reviewed"]),
        )
        .count()
    )
    if labeled < 10:
        raise HTTPException(
            400,
            f"Need at least 10 labeled images to train. Have {labeled}. "
            "Note: 50+ is recommended; the 'Label 50 -> auto-label 500' pitch is "
            "unverified on custom domains with seeds below ~200.",
        )

    run = models.TrainingRun(
        dataset_id=ds.id,
        status="queued",
        epochs=payload.epochs,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    background.add_task(
        _run_training,
        run_id=run.id,
        dataset_id=ds.id,
        epochs=payload.epochs,
        img_size=payload.img_size,
    )
    return run


def _run_training(run_id: int, dataset_id: int, epochs: int, img_size: int) -> None:
    """Background training task. Owns its own db session."""
    db = SessionLocal()
    try:
        run = db.query(models.TrainingRun).get(run_id)
        ds = db.query(models.Dataset).get(dataset_id)
        if not run or not ds:
            return

        run.status = "running"
        db.commit()

        labeled = (
            db.query(models.Image)
            .filter(
                models.Image.dataset_id == ds.id,
                models.Image.status.in_(["labeled", "reviewed"]),
            )
            .all()
        )

        layout_dir = TRAIN_DIRS / f"ds{ds.id}_run{run.id}"
        layout_dir.mkdir(exist_ok=True)

        images_for_train = []
        for img in labeled:
            src = IMAGES_DIR / str(ds.id) / img.filename
            if not src.exists():
                continue
            boxes = [
                (b.cx, b.cy, b.w, b.h, b.class_idx)
                for b in img.boxes
                if b.source in ("human",) or b.source == "model"
            ]
            if not boxes:
                continue
            images_for_train.append((src, boxes))

        if not images_for_train:
            run.status = "failed"
            run.log = "No usable labeled images found on disk."
            run.finished_at = datetime.utcnow()
            db.commit()
            return

        export_yolo_layout(layout_dir, images_for_train, val_split=0.2)
        ds_yaml = _dataset_yaml(layout_dir, ds.class_name)

        backend = get_backend()
        try:
            best = backend.train(
                dataset_yaml=ds_yaml,
                epochs=epochs,
                img_size=img_size,
                project_dir=RUNS_DIR,
                run_name=f"ds{ds.id}_run{run.id}",
            )
        except Exception as exc:  # surface training failure to UI
            run.status = "failed"
            run.log = f"{type(exc).__name__}: {exc}"
            run.finished_at = datetime.utcnow()
            db.commit()
            return

        if not best or not best.exists():
            run.status = "failed"
            run.log = "Training finished but best.pt not produced."
        else:
            run.status = "done"
            run.weights_path = str(best)
        run.finished_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


@router.get("/datasets/{dataset_id}/runs", response_model=list[schemas.TrainingRunOut])
def list_runs(dataset_id: int, db: Session = Depends(get_db)):
    _require_dataset(db, dataset_id)
    return (
        db.query(models.TrainingRun)
        .filter(models.TrainingRun.dataset_id == dataset_id)
        .order_by(models.TrainingRun.id.desc())
        .all()
    )


@router.get("/runs/{run_id}", response_model=schemas.TrainingRunOut)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.query(models.TrainingRun).get(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run


# ----- prediction -----


@router.post("/datasets/{dataset_id}/predict")
def predict_unlabeled(
    dataset_id: int,
    payload: schemas.PredictRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    ds = _require_dataset(db, dataset_id)

    last_run = (
        db.query(models.TrainingRun)
        .filter(
            models.TrainingRun.dataset_id == ds.id,
            models.TrainingRun.status == "done",
        )
        .order_by(models.TrainingRun.id.desc())
        .first()
    )
    if not last_run or not last_run.weights_path or not Path(last_run.weights_path).exists():
        raise HTTPException(400, "No completed training run with weights available.")

    pending = (
        db.query(models.Image)
        .filter(
            models.Image.dataset_id == ds.id,
            models.Image.status == "pending",
        )
        .all()
    )
    if not pending:
        return {"queued": 0, "weights": last_run.weights_path}

    background.add_task(
        _run_predict,
        dataset_id=ds.id,
        weights_path=last_run.weights_path,
        image_ids=[i.id for i in pending],
        conf_threshold=payload.conf_threshold,
    )
    return {"queued": len(pending), "weights": last_run.weights_path}


def _run_predict(
    dataset_id: int,
    weights_path: str,
    image_ids: list[int],
    conf_threshold: float,
) -> None:
    db = SessionLocal()
    try:
        backend = get_backend()
        weights = Path(weights_path)
        for img_id in image_ids:
            img = db.query(models.Image).get(img_id)
            if not img or img.status != "pending":
                continue

            src = IMAGES_DIR / str(dataset_id) / img.filename
            if not src.exists():
                continue

            try:
                preds: list[Prediction] = backend.predict(weights, src, conf_threshold)
            except Exception:
                continue

            # wipe any prior model boxes; keep humans
            for b in list(img.boxes):
                if b.source == "model":
                    db.delete(b)

            for p in preds:
                db.add(
                    models.Box(
                        image_id=img.id,
                        cx=p.cx,
                        cy=p.cy,
                        w=p.w,
                        h=p.h,
                        confidence=p.confidence,
                        class_idx=p.class_idx,
                        source="model",
                    )
                )

            img.confidence = uncertainty_score(preds)
            img.status = "predicted"
            db.commit()
    finally:
        db.close()


# ----- review queue -----


@router.get("/datasets/{dataset_id}/queue", response_model=list[schemas.ImageOut])
def review_queue(
    dataset_id: int,
    limit: int = 50,
    sort: str = "confidence_asc",
    db: Session = Depends(get_db),
):
    _require_dataset(db, dataset_id)
    q = db.query(models.Image).filter(
        models.Image.dataset_id == dataset_id,
        models.Image.status == "predicted",
    )
    if sort == "confidence_asc":
        q = q.order_by(models.Image.confidence.asc().nulls_first(), models.Image.id)
    elif sort == "confidence_desc":
        q = q.order_by(models.Image.confidence.desc().nulls_last(), models.Image.id)
    else:
        q = q.order_by(models.Image.id)
    return [_image_to_out(r) for r in q.limit(limit).all()]


# ----- export -----


@router.get("/datasets/{dataset_id}/export/yolo")
def export_yolo(dataset_id: int, db: Session = Depends(get_db)):
    ds = _require_dataset(db, dataset_id)

    rows = (
        db.query(models.Image)
        .filter(
            models.Image.dataset_id == ds.id,
            models.Image.status.in_(["labeled", "reviewed"]),
        )
        .all()
    )
    if not rows:
        raise HTTPException(400, "No reviewed/labeled images to export.")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "dataset.yaml",
            "path: ./\n"
            "train: images/train\n"
            "val: images/val\n"
            f"names:\n  0: {ds.class_name}\n",
        )
        n = len(rows)
        val_count = max(1, int(n * 0.2)) if n > 1 else 0
        for i, img in enumerate(rows):
            split = "val" if i < val_count else "train"
            src = IMAGES_DIR / str(ds.id) / img.filename
            if not src.exists():
                continue
            z.write(src, arcname=f"images/{split}/{img.filename}")
            lines = [
                f"{b.class_idx} {b.cx:.6f} {b.cy:.6f} {b.w:.6f} {b.h:.6f}"
                for b in img.boxes
            ]
            z.writestr(f"labels/{split}/{Path(img.filename).stem}.txt", "\n".join(lines))

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{ds.name}_yolo.zip"',
        },
    )


# ----- helpers -----


def _require_dataset(db: Session, dataset_id: int) -> models.Dataset:
    ds = db.query(models.Dataset).get(dataset_id)
    if not ds:
        raise HTTPException(404, "Dataset not found")
    return ds
