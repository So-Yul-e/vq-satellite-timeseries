from sqlalchemy import Column, String, Integer
from app.core.database import Base


class ImageType(Base):
    __tablename__ = "image_types"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(200))
