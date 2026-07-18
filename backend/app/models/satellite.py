from __future__ import annotations
from sqlalchemy import Column, String, Integer, BigInteger, Date, Numeric, ForeignKey, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
from app.core.database import Base

class Satellite(Base):
    __tablename__ = "satellites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    image_type_id = Column(Integer, ForeignKey("image_types.id"))
    file_path = Column(String(500), nullable=False)
    file_size = Column(BigInteger)
    width = Column(Integer)
    height = Column(Integer)
    channels = Column(Integer)
    capture_date = Column(Date)
    latitude_min = Column(Numeric(10, 7))
    latitude_max = Column(Numeric(10, 7))
    longitude_min = Column(Numeric(10, 7))
    longitude_max = Column(Numeric(10, 7))
    thumbnail_path = Column(String(500))
    metadata_json = Column(JSONB)
    status = Column(String(20), default="uploaded")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="satellites")
    # codebook = relationship("VQCodebook", uselist=False, back_populates="satellite")
    # feature_vectors = relationship("FeatureVector", back_populates="satellite")
    # clusters = relationship("Cluster", back_populates="satellite")
