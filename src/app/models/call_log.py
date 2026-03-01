from sqlalchemy import Column, String, Integer, DateTime, func, ForeignKey
from app.models.base import Base


class CallLog(Base):
    __tablename__ = "call_logs"

    call_sid = Column(String(100), primary_key=True)
    phone = Column(String(20), ForeignKey("users.phone"))
    direction = Column(String(20))                      # inbound | outbound
    status = Column(String(30))                         # completed | failed | missed
    duration_seconds = Column(Integer, nullable=True)
    language_detected = Column(String(50), nullable=True)
    tools_used = Column(String(500), nullable=True)     # comma-separated
    created_at = Column(DateTime, server_default=func.now())
    ended_at = Column(DateTime, nullable=True)
