from datetime import datetime
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from .db import Base


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    # Ordered list of class names; index in list == YOLO class_idx on Box rows.
    class_names = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)

    images = relationship("Image", back_populates="dataset", cascade="all, delete-orphan")


class Image(Base):
    __tablename__ = "images"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    filename = Column(String, nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    # workflow status: pending | labeled | predicted | reviewed | rejected
    status = Column(String, nullable=False, default="pending")
    confidence = Column(Float, nullable=True)  # mean conf of predictions (for queue sort)
    created_at = Column(DateTime, default=datetime.utcnow)

    dataset = relationship("Dataset", back_populates="images")
    boxes = relationship("Box", back_populates="image", cascade="all, delete-orphan")


class Box(Base):
    __tablename__ = "boxes"

    id = Column(Integer, primary_key=True, index=True)
    image_id = Column(Integer, ForeignKey("images.id"), nullable=False)
    # bbox stored as YOLO-normalized cx, cy, w, h (0..1)
    cx = Column(Float, nullable=False)
    cy = Column(Float, nullable=False)
    w = Column(Float, nullable=False)
    h = Column(Float, nullable=False)
    confidence = Column(Float, nullable=True)
    source = Column(String, nullable=False, default="human")  # human | model
    class_idx = Column(Integer, nullable=False, default=0)

    image = relationship("Image", back_populates="boxes")


class TrainingRun(Base):
    __tablename__ = "training_runs"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    status = Column(String, nullable=False, default="queued")  # queued|running|done|failed
    epochs = Column(Integer, nullable=False, default=20)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    weights_path = Column(String, nullable=True)
    log = Column(Text, nullable=True)
