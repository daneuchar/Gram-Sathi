from sqlalchemy import Column, String, Integer, DateTime, func, ForeignKey
from app.models.base import Base


class ConversationTurn(Base):
    __tablename__ = "conversation_turns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    call_sid = Column(String(100), ForeignKey("call_logs.call_sid"))
    turn_number = Column(Integer)
    speaker = Column(String(10))                    # user | assistant
    transcript = Column(String(2000))
    tool_called = Column(String(100), nullable=True)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
