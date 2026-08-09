import json
import uuid
from datetime import datetime, timezone
from sqlalchemy import select  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入

try:
    from uuid7 import uuid7 as _uuid7_impl
except ImportError:
    _uuid7_impl = uuid.uuid4

def _uuid7_hex(n: int = 16) -> str:
    return _uuid7_impl().hex[:n]

from sqlalchemy.ext.asyncio import AsyncSession
from app.models.system_setting import SystemSetting
from app.models.config_revision import ConfigRevision
from app.models.publish_record import PublishRecord
from app.services.config_center_service import config_center_service
from app.services.audit_center_service import audit_center_service
from loguru import logger


class ReleaseCenterService:
    _revision_key = "visual.config.current_revision"

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

    async def _get_revision_content(self, db: AsyncSession, revision: int) -> dict:
        if revision <= 0:
            return {}
        stmt = select(ConfigRevision).where(ConfigRevision.revision == revision).order_by(ConfigRevision.created_at.desc())
        result = await db.execute(stmt)
        record = result.scalars().first()
        if record and record.content:
            try:
                data = json.loads(record.content)
                if isinstance(data, dict):
                    return data
            except Exception as e:
                logger.warning(f"Error: {e}")
        legacy_raw = await self._get_setting(db, f"visual.config.revision.{revision}")
        if not legacy_raw:
            return {}
        try:
            data = json.loads(legacy_raw)
            if isinstance(data, dict):
                return data
        except Exception:
            return {}
        return {}

    def _flatten(self, value: dict, prefix: str = "") -> dict:
        out: dict[str, str | int | float | bool | None] = {}
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(item, dict):
                out.update(self._flatten(item, path))
            elif isinstance(item, (str, int, float, bool)) or item is None:
                out[path] = item
            else:
                out[path] = json.dumps(item, ensure_ascii=False)
        return out

    async def get_diff(self, db: AsyncSession, draft_id: str) -> dict:
        draft = await config_center_service._get_draft_data(db, draft_id)
        if not draft:
            return {"from_revision": 0, "to_draft": draft_id, "changes": []}
        base_revision = int(draft.get("base_revision") or 0)
        base_modules = await self._get_revision_content(db, base_revision)
        after_modules = draft.get("modules") or {}
        before_map = self._flatten(base_modules)
        after_map = self._flatten(after_modules)
        keys = set(before_map.keys()) | set(after_map.keys())
        changes: list[dict] = []
        for key in sorted(keys):
            before = before_map.get(key)
            after = after_map.get(key)
            if before == after:
                continue
            parts = key.split(".")
            module = ".".join(parts[:-1]) if len(parts) > 1 else key
            changes.append(
                {
                    "module": module,
                    "path": parts[-1],
                    "before": before,
                    "after": after,
                    "risk_level": "low",
                }
            )
        return {"from_revision": base_revision, "to_draft": draft_id, "changes": changes}

    async def publish(self, db: AsyncSession, draft_id: str, operator: str, note: str | None) -> dict:
        draft = await config_center_service._get_draft_data(db, draft_id)
        if not draft:
            raise ValueError("Draft does not exist")
        validation = await config_center_service.validate_draft(db, draft_id, operator)
        if not validation["valid"]:
            raise ValueError("Draft validation failed")
        raw_revision = await self._get_setting(db, self._revision_key)
        try:
            previous_revision = int(raw_revision or "0")
        except Exception:
            previous_revision = 0
        new_revision = previous_revision + 1
        modules = draft.get("modules") or {}
        content = json.dumps(modules, ensure_ascii=False)
        db.add(
            ConfigRevision(
                revision=new_revision,
                status="published",
                content=content,
                created_by=operator or "system",
            )
        )
        publish_id = f"pb_{_uuid7_hex(12)}"
        db.add(
            PublishRecord(
                publish_id=publish_id,
                from_revision=previous_revision,
                to_revision=new_revision,
                operator=operator or "system",
                note=note,
                status="success",
            )
        )
        await self._set_setting(db, f"visual.config.revision.{new_revision}", content)
        await self._set_setting(db, self._revision_key, str(new_revision))
        draft["base_revision"] = new_revision
        draft["status"] = "published"
        draft["updated_at"] = datetime.now(timezone.utc).isoformat()
        await config_center_service._save_draft_data(db, draft_id, draft)
        await db.commit()
        await audit_center_service.log(
            db=db,
            module="release-center",
            action="publish",
            operator=operator,
            result="success",
            summary=f"发布草稿 {draft_id} 为 revision {new_revision}" if not note else f"发布草稿 {draft_id} 为 revision {new_revision}: {note}",
        )
        return {
            "publish_id": publish_id,
            "revision": new_revision,
            "status": "success",
            "published_at": datetime.now(timezone.utc).isoformat(),
        }

    async def rollback(self, db: AsyncSession, target_revision: int, operator: str, reason: str | None) -> dict:
        target_modules = await self._get_revision_content(db, target_revision)
        if not target_modules:
            raise ValueError("Target version does not exist")
        raw_revision = await self._get_setting(db, self._revision_key)
        try:
            current_revision = int(raw_revision or "0")
        except Exception:
            current_revision = 0
        publish_id = f"pb_{_uuid7_hex(12)}"
        db.add(
            PublishRecord(
                publish_id=publish_id,
                from_revision=current_revision,
                to_revision=target_revision,
                operator=operator or "system",
                note=reason,
                status="rollback",
            )
        )
        await self._set_setting(db, self._revision_key, str(target_revision))
        await db.commit()
        await audit_center_service.log(
            db=db,
            module="release-center",
            action="rollback",
            operator=operator,
            result="success",
            summary=f"回滚到 revision {target_revision}" if not reason else f"回滚到 revision {target_revision}: {reason}",
        )
        return {"status": "success", "target_revision": target_revision}


release_center_service = ReleaseCenterService()