from sqlalchemy import Column, String, Float, DateTime, func
from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    phone = Column(String(20), primary_key=True)
    name = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    language = Column(String(50), nullable=True)
    crops = Column(String(500), nullable=True)      # comma-separated
    land_acres = Column(Float, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
