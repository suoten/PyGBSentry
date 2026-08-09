"""会商会话指令：以报警为会商会话，记录指挥指令。"""
from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.sql import func
from app.db.base import Base
import uuid

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def generate_uuid():
    return _uuid7_impl().hex


class CommandInstruction(Base):
    __tablename__ = "command_instructions"

    id = Column(String(32), primary_key=True, default=generate_uuid)
    session_id = Column(String(32), nullable=False, index=True, comment="会商会话ID，通常为 alarm_id")
    content = Column(Text, nullable=False, comment="指令内容")
    user_id = Column(String(32), nullable=True, index=True)
    created_at = Column(DateTime, default=func.now())
