import json
import uuid
from datetime import datetime, timezone
try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def _uuid7_hex(n: int = 16) -> str:
    return _uuid7_impl().hex[:n]

from sqlalchemy import select, desc  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.system_setting import SystemSetting
from app.models.config_draft import ConfigDraft
from app.models.config_revision import ConfigRevision
from app.services.config_validator_service import config_validator_service
from app.services.audit_center_service import audit_center_service
from loguru import logger


class ConfigCenterService:
    _draft_key = "visual.config.current_draft"
    _revision_key = "visual.config.current_revision"

    def _to_iso(self, dt: datetime | None) -> str:
        if not dt:
            return datetime.now(timezone.utc).isoformat()
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc).isoformat()
        return dt.astimezone(timezone.utc).isoformat()

    def _parse_datetime(self, value: str | None) -> datetime:
        if not value:
            return datetime.now(timezone.utc)
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)

    async def _get_setting(self, db: AsyncSession, key: str) -> str | None:
        stmt = select(SystemSetting).where(SystemSetting.setting_key == key)
        result = await db.execute(stmt)
        row = result.scalars().first()
        return row.setting_value if row else None

    async def _set_setting(self, db: AsyncSession, key: str, value: str):
        stmt = select(SystemSetting).where(SystemSetting.setting_key == key)
        result = await db.execute(stmt)
        row = result.scalars().first()
        if row:
            row.setting_value = value
        else:
            db.add(SystemSetting(setting_key=key, setting_value=value))

    def _row_to_draft(self, row: ConfigDraft) -> dict:
        modules = {}
        try:
            loaded = json.loads(row.modules or "{}")
            if isinstance(loaded, dict):
                modules = loaded
        except Exception:
            modules = {}
        return {
            "draft_id": row.draft_id,
            "base_revision": row.base_revision,
            "status": row.status or "editing",
            "modules": modules,
            "updated_at": self._to_iso(row.updated_at),
        }

    async def _get_draft_row(self, db: AsyncSession, draft_id: str) -> ConfigDraft | None:
        stmt = select(ConfigDraft).where(ConfigDraft.draft_id == draft_id)
        result = await db.execute(stmt)
        return result.scalars().first()

    async def _upsert_draft_row(self, db: AsyncSession, draft_id: str, data: dict):
        row = await self._get_draft_row(db, draft_id)
        modules_json = json.dumps(data.get("modules") or {}, ensure_ascii=False)
        base_revision = int(data.get("base_revision") or 0)
        status = str(data.get("status") or "editing")
        updated_at = self._parse_datetime(data.get("updated_at"))
        if row:
            row.base_revision = base_revision
            row.status = status
            row.modules = modules_json
            row.updated_at = updated_at
            return
        db.add(
            ConfigDraft(
                draft_id=draft_id,
                base_revision=base_revision,
                status=status,
                modules=modules_json,
                updated_at=updated_at,
            )
        )

    async def _get_legacy_draft_data(self, db: AsyncSession, draft_id: str) -> dict | None:
        raw = await self._get_setting(db, f"visual.config.draft.{draft_id}")
        if not raw:
            return None
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except Exception:
            return None
        return None

    async def _get_draft_data(self, db: AsyncSession, draft_id: str) -> dict | None:
        row = await self._get_draft_row(db, draft_id)
        if row:
            return self._row_to_draft(row)
        legacy = await self._get_legacy_draft_data(db, draft_id)
        if not legacy:
            return None
        if not legacy.get("draft_id"):
            legacy["draft_id"] = draft_id
        if not legacy.get("updated_at"):
            legacy["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self._upsert_draft_row(db, draft_id, legacy)
        return legacy

    async def _save_draft_data(self, db: AsyncSession, draft_id: str, data: dict):
        await self._upsert_draft_row(db, draft_id, data)
        await self._set_setting(db, f"visual.config.draft.{draft_id}", json.dumps(data, ensure_ascii=False))
        await self._set_setting(db, self._draft_key, draft_id)

    async def _load_published_modules(self, db: AsyncSession) -> tuple[int, dict]:
        raw_revision = await self._get_setting(db, self._revision_key)
        try:
            revision = int(raw_revision or "0")
        except Exception:
            revision = 0
        if revision <= 0:
            return 0, {}
        stmt = select(ConfigRevision).where(ConfigRevision.revision == revision).order_by(desc(ConfigRevision.created_at))
        result = await db.execute(stmt)
        row = result.scalars().first()
        if row and row.content:
            try:
                data = json.loads(row.content)
                if isinstance(data, dict):
                    return revision, data
            except Exception as e:
                logger.warning(f"Failed to parse config revision {revision}: {e}")
        raw = await self._get_setting(db, f"visual.config.revision.{revision}")
        if raw:
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    return revision, data
            except Exception as e:
                logger.warning(f"Failed to parse config revision {revision}: {e}")
        return revision, {}

    async def get_or_create_current_draft(self, db: AsyncSession) -> dict:
        draft_id = await self._get_setting(db, self._draft_key)
        if draft_id:
            draft_data = await self._get_draft_data(db, draft_id)
            if draft_data:
                return draft_data
        latest_stmt = select(ConfigDraft).order_by(desc(ConfigDraft.updated_at))
        latest_result = await db.execute(latest_stmt)
        latest_row = latest_result.scalars().first()
        if latest_row:
            draft = self._row_to_draft(latest_row)
            await self._set_setting(db, self._draft_key, draft["draft_id"])
            await db.commit()
            return draft
        base_revision, published_modules = await self._load_published_modules(db)
        draft_id = f"dr_{_uuid7_hex(12)}"
        now = datetime.now(timezone.utc).isoformat()
        draft = {
            "draft_id": draft_id,
            "base_revision": base_revision,
            "status": "editing",
            "modules": published_modules,
            "updated_at": now,
        }
        await self._save_draft_data(db, draft_id, draft)
        await db.commit()
        return draft

    async def update_draft_module(
        self,
        db: AsyncSession,
        draft_id: str,
        module_name: str,
        payload: dict,
        operator: str,
    ) -> dict:
        draft = await self._get_draft_data(db, draft_id)
        if not draft:
            draft = await self.get_or_create_current_draft(db)
            draft_id = draft["draft_id"]
        modules = draft.get("modules") or {}
        modules[module_name] = payload
        draft["modules"] = modules
        draft["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self._save_draft_data(db, draft_id, draft)
        await db.commit()
        await audit_center_service.log(
            db=db,
            module="config-center",
            action="update-module",
            operator=operator,
            result="success",
            summary=f"更新草稿 {draft_id} 模块 {module_name}",
        )
        return draft

    async def validate_draft(self, db: AsyncSession, draft_id: str, operator: str) -> dict:
        draft = await self._get_draft_data(db, draft_id)
        if not draft:
            return {
                "valid": False,
                "errors": [{"field": "draft_id", "message": "Draft does not exist"}],
                "warnings": [],
                "hints": [],
            }
        result = config_validator_service.validate_modules(draft.get("modules") or {})
        await audit_center_service.log(
            db=db,
            module="config-center",
            action="validate",
            operator=operator,
            result="success" if result["valid"] else "failed",
            summary=f"校验草稿 {draft_id}",
        )
        return result


config_center_service = ConfigCenterService()