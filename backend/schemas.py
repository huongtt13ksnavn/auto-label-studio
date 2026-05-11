from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class BoxIn(BaseModel):
    cx: float = Field(..., ge=0.0, le=1.0)
    cy: float = Field(..., ge=0.0, le=1.0)
    w: float = Field(..., gt=0.0, le=1.0)
    h: float = Field(..., gt=0.0, le=1.0)
    class_idx: int = 0
    confidence: Optional[float] = None
    source: Literal["human", "model"] = "human"


class BoxOut(BoxIn):
    id: int

    class Config:
        from_attributes = True


class ImageOut(BaseModel):
    id: int
    dataset_id: int
    filename: str
    width: int
    height: int
    status: str
    confidence: Optional[float]
    boxes: list[BoxOut] = []

    class Config:
        from_attributes = True


class DatasetCreate(BaseModel):
    name: str
    class_name: str = "object"


class DatasetOut(BaseModel):
    id: int
    name: str
    class_name: str
    created_at: datetime
    image_count: int = 0
    labeled_count: int = 0

    class Config:
        from_attributes = True


class LabelUpdate(BaseModel):
    boxes: list[BoxIn]
    status: Literal["labeled", "reviewed", "rejected"] = "labeled"


class TrainRequest(BaseModel):
    epochs: int = 20
    img_size: int = 640


class TrainingRunOut(BaseModel):
    id: int
    dataset_id: int
    status: str
    epochs: int
    started_at: datetime
    finished_at: Optional[datetime]
    weights_path: Optional[str]
    log: Optional[str]

    class Config:
        from_attributes = True


class PredictRequest(BaseModel):
    conf_threshold: float = 0.25


class QueueParams(BaseModel):
    limit: int = 50
    status: Optional[str] = None  # filter
    sort: Literal["confidence_asc", "confidence_desc", "id"] = "confidence_asc"
