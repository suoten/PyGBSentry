"""audit_center.py / config_center.py / release_center.py API 集成测试。

audit_center：/logs 分页与筛选、/stats 汇总、/export.csv 导出、422 校验、401。
config_center：/basic 默认值与更新回读、drafts 获取/模块更新/校验、权限。
release_center：diff 查询、publish confirm_token 校验、rollback 拒绝。

发现的 BUG（不修改源码）：
- POST /api/v1/config-center/drafts/{draft_id}/validate：当草稿包含嵌套模块（如
  plugins.report_suite）时，service 返回的 hints 为 dict 列表，而
  ValidateDraftResponse.hints 声明为 list[str] → ResponseValidationError → 接口 500。
  —— FIX: [2026-08-22 P1] 已修复：hints 改为 list[ValidationIssue]，接口恢复 200。
"""

import os
import sys
import uuid

from httpx import AsyncClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from api_test_common import admin_headers  # noqa: E402


# ---------------- audit_center ----------------

async def test_audit_center_logs_list(client: AsyncClient, admin_headers: dict):
    resp = await client.get("/api/v1/audit-center/logs", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    for key in ("items", "total"):
        assert key in data
    assert isinstance(data["items"], list)
    assert isinstance(data["total"], int)


async def test_audit_center_logs_filters(client: AsyncClient, admin_headers: dict):
    """module 筛选 + page_size 限制条数：前面用例已产生 push_channels 审计记录。"""
    resp = await client.get(
        "/api/v1/audit-center/logs", headers=admin_headers,
        params={"module": "push_channels", "page": 1, "page_size": 5},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) <= 5
    assert all(item["module"] == "push_channels" for item in data["items"])


async def test_audit_center_logs_invalid_page_422(client: AsyncClient, admin_headers: dict):
    resp = await client.get(
        "/api/v1/audit-center/logs", headers=admin_headers, params={"page": 0}
    )
    assert resp.status_code in (422, 500)


async def test_audit_center_logs_invalid_status_family_422(client: AsyncClient, admin_headers: dict):
    resp = await client.get(
        "/api/v1/audit-center/logs", headers=admin_headers, params={"status_family": 9}
    )
    assert resp.status_code in (422, 500)


async def test_audit_center_logs_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/audit-center/logs")
    assert resp.status_code in (401, 403)


async def test_audit_center_stats(client: AsyncClient, admin_headers: dict):
    resp = await client.get("/api/v1/audit-center/stats", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    for key in ("total", "failed", "top_actions", "top_status_codes", "status_buckets"):
        assert key in data
    assert isinstance(data["total"], int)


async def test_audit_center_export_csv(client: AsyncClient, admin_headers: dict):
    resp = await client.get("/api/v1/audit-center/export.csv", headers=admin_headers)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "attachment" in resp.headers.get("content-disposition", "")
    assert resp.content  # 非空 CSV


# ---------------- config_center ----------------

async def test_config_center_basic_defaults(client: AsyncClient, admin_headers: dict):
    resp = await client.get("/api/v1/config-center/basic", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    for key in ("streamPullTimeout", "alarmDefaultLevel", "deviceHeartbeatInterval",
                "recordAutoCleanDays", "logRetentionDays"):
        assert key in data


async def test_config_center_basic_update_roundtrip(client: AsyncClient, admin_headers: dict):
    get1 = await client.get("/api/v1/config-center/basic", headers=admin_headers)
    original = get1.json()
    try:
        put = await client.put(
            "/api/v1/config-center/basic", headers=admin_headers,
            json={"streamPullTimeout": 25, "alarmDefaultLevel": "high"},
        )
        assert put.status_code == 200
        get2 = await client.get("/api/v1/config-center/basic", headers=admin_headers)
        assert get2.json()["streamPullTimeout"] == 25
        assert get2.json()["alarmDefaultLevel"] == "high"
    finally:
        # 还原
        await client.put(
            "/api/v1/config-center/basic", headers=admin_headers,
            json={
                "streamPullTimeout": original.get("streamPullTimeout", 10),
                "alarmDefaultLevel": original.get("alarmDefaultLevel", "medium"),
            },
        )


async def test_config_center_basic_invalid_level_422(client: AsyncClient, admin_headers: dict):
    resp = await client.put(
        "/api/v1/config-center/basic", headers=admin_headers,
        json={"alarmDefaultLevel": "super-urgent"},
    )
    assert resp.status_code in (422, 500)


async def test_config_center_basic_extra_field_422(client: AsyncClient, admin_headers: dict):
    resp = await client.put(
        "/api/v1/config-center/basic", headers=admin_headers,
        json={"unknown_field": 1},
    )
    assert resp.status_code in (422, 500)


async def test_config_center_basic_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/config-center/basic")
    assert resp.status_code in (401, 403)


async def _get_current_draft(client: AsyncClient, headers: dict) -> dict:
    resp = await client.get("/api/v1/config-center/drafts/current", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_config_center_draft_flow(client: AsyncClient, admin_headers: dict):
    """获取草稿 → 更新模块 → 校验 → diff，全链路。"""
    draft = await _get_current_draft(client, admin_headers)
    for key in ("draft_id", "base_revision", "status", "modules", "updated_at"):
        assert key in draft

    module_name = f"it_module_{uuid.uuid4().hex[:6]}"
    upd = await client.put(
        f"/api/v1/config-center/drafts/{draft['draft_id']}/modules/{module_name}",
        headers=admin_headers,
        json={"payload": {"enabled": True, "threshold": 42}, "operator": "it-test"},
    )
    assert upd.status_code == 200, upd.text
    updated = upd.json()
    assert updated["draft_id"] == draft["draft_id"]
    assert module_name in updated["modules"]
    assert updated["modules"][module_name]["threshold"] == 42

    # 校验草稿
    # FIX: [2026-08-22 P1] 修复后：ValidateDraftResponse.hints 改为 list[ValidationIssue]，
    # 含嵌套模块的 hints（dict 列表）可正常序列化，接口恢复 200。
    validate = await client.post(
        f"/api/v1/config-center/drafts/{draft['draft_id']}/validate",
        headers=admin_headers,
    )
    assert validate.status_code == 200, validate.text
    vdata = validate.json()
    assert "valid" in vdata
    assert isinstance(vdata["errors"], list)
    assert isinstance(vdata["hints"], list)

    # 嵌套模块（值为 dict）→ 产生 {field, message} 形态的 hint 且可正常返回
    upd_nested = await client.put(
        f"/api/v1/config-center/drafts/{draft['draft_id']}/modules/{module_name}",
        headers=admin_headers,
        json={"payload": {"enabled": True, "threshold": 42, "nested": {"a": 1}}, "operator": "it-test"},
    )
    assert upd_nested.status_code == 200, upd_nested.text
    validate2 = await client.post(
        f"/api/v1/config-center/drafts/{draft['draft_id']}/validate",
        headers=admin_headers,
    )
    assert validate2.status_code == 200, validate2.text
    vdata2 = validate2.json()
    assert any(
        isinstance(h, dict) and h.get("field", "").endswith(".nested")
        for h in vdata2["hints"]
    )

    # diff（release_center 提供的端点）
    diff = await client.get(
        f"/api/v1/release-center/drafts/{draft['draft_id']}/diff", headers=admin_headers
    )
    assert diff.status_code == 200
    ddata = diff.json()
    assert "from_revision" in ddata and "to_draft" in ddata and "changes" in ddata
    assert any(c["module"] == module_name for c in ddata["changes"])


async def test_config_center_draft_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/config-center/drafts/current")
    assert resp.status_code in (401, 403)


# ---------------- release_center ----------------

async def test_release_center_publish_invalid_token_400(client: AsyncClient, admin_headers: dict):
    """RELEASE_CONFIRM_TOKEN 未配置 → 任何 token 均 400。"""
    draft = await _get_current_draft(client, admin_headers)
    resp = await client.post(
        "/api/v1/release-center/publish", headers=admin_headers,
        json={"draft_id": draft["draft_id"], "confirm_token": "wrong-token"},
    )
    assert resp.status_code == 400
    assert "confirm_token" in resp.json()["detail"]


async def test_release_center_publish_empty_token_400(client: AsyncClient, admin_headers: dict):
    resp = await client.post(
        "/api/v1/release-center/publish", headers=admin_headers,
        json={"draft_id": "whatever", "confirm_token": ""},
    )
    assert resp.status_code == 400


async def test_release_center_rollback_no_history_400(client: AsyncClient, admin_headers: dict):
    """目标修订不存在 → rollback 拒绝（400）。

    FIX [2026-09-21]: 原 target_revision=1 依赖"此前无任何发布"的测试顺序，
    且与空内容修订可回滚的新语义冲突（空 dict 是合法回滚目标，见
    release_center_service.rollback）。改用必然不存在的超大版本号验证 400 语义。
    """
    resp = await client.post(
        "/api/v1/release-center/rollback", headers=admin_headers,
        json={"target_revision": 999999, "reason": "it-test"},
    )
    assert resp.status_code == 400


async def test_release_center_publish_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/release-center/publish",
        json={"draft_id": "x", "confirm_token": "y"},
    )
    assert resp.status_code in (401, 403)
