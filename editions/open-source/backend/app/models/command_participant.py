from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class CommandParticipant(Base):
    __tablename__ = "command_participants"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    session_id = Column(String(32), nullable=False, index=True)
    user_id = Column(String(32), nullable=True, index=True)
    username = Column(String(64), nullable=False)
    role = Column(String(24), nullable=False, default="observer")
    joined_at = Column(DateTime, default=func.now(), nullable=False)
