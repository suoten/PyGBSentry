"""
plugins_ai_runtime — AI 插件运行时数据 API（付费 AI 插件，随插件市场一起启用）。

自服务器版宿主 plugins_runtime.py 的「AI Plugin Runtime Data APIs」块逐端点移植，
供 3 个 AI 插件（ai_face_recognition / ai_plate_recognition / ai_behavior_analysis）
的 iframe 管理页在开源版调用。与服务器版的差异仅限：
  - 鉴权：deps.get_current_tenant_user → deps.get_current_active_user（开源版无租户体系）；
  - plugin_manager 直接从 app.core.plugin_manager 导入（服务器版经 plugins_core 中转）。

说明：
  - /runtime/ai_health/{plugin_id} 不在本文件内：开源版 plugins_runtime.py 已有同契约
    实现（经 HOOK_ON_PLUGIN_TEST 健康自测），避免重复注册；
  - 插件未安装/未加载时与服务器版行为一致（返回空 rows / success:false 等，不抛 500）。
"""
from fastapi import APIRouter, Depends, Query, UploadFile, File
from pydantic import BaseModel
from loguru import logger

from app.api import deps
from app.models.user import User
from app.core.plugin_manager import plugin_manager

router = APIRouter()


# ---------------------------------------------------------------------------
# AI Plugin Runtime Data APIs
# ---------------------------------------------------------------------------

@router.get("/runtime/ai_face_recognition/detections")
async def ai_face_detections(
    device_id: str = Query(default=""),
    keyword: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(deps.get_current_active_user),
):
    try:
        mod = plugin_manager.plugins.get("ai_face_recognition")
        if mod and hasattr(mod, "get_detection_log"):
            rows = mod.get_detection_log(
                device_id=device_id or None,
                keyword=keyword or None,
                limit=limit,
            )
            return {"rows": rows, "total": len(rows)}
        return {"rows": [], "total": 0}
    except Exception as e:
        logger.warning(f"AI face detection log error: {e}")
        return {"rows": [], "total": 0}


@router.get("/runtime/ai_plate_recognition/plates")
async def ai_plate_recognitions(
    device_id: str = Query(default=""),
    keyword: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(deps.get_current_active_user),
):
    try:
        mod = plugin_manager.plugins.get("ai_plate_recognition")
        if mod and hasattr(mod, "get_recognition_log"):
            rows = mod.get_recognition_log(
                device_id=device_id or None,
                keyword=keyword or None,
                limit=limit,
            )
            return {"rows": rows, "total": len(rows)}
        return {"rows": [], "total": 0}
    except Exception as e:
        logger.warning(f"AI plate recognition log error: {e}")
        return {"rows": [], "total": 0}


@router.get("/runtime/ai_behavior_analysis/alerts")
async def ai_behavior_alerts(
    device_id: str = Query(default=""),
    keyword: str = Query(default=""),
    rule: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(deps.get_current_active_user),
):
    try:
        mod = plugin_manager.plugins.get("ai_behavior_analysis")
        if mod and hasattr(mod, "get_alert_log"):
            rows = mod.get_alert_log(
                device_id=device_id or None,
                keyword=keyword or None,
                rule=rule or None,
                limit=limit,
            )
            return {"rows": rows, "total": len(rows)}
        return {"rows": [], "total": 0}
    except Exception as e:
        logger.warning(f"AI behavior alert log error: {e}")
        return {"rows": [], "total": 0}


# ---------------------------------------------------------------------------
# AI Plugin Management APIs (Face DB, Plate Whitelist, Health Check)
# ---------------------------------------------------------------------------

class FaceRegisterRequest(BaseModel):
    face_id: str
    name: str
    image_url: str = ""


class FaceUnregisterRequest(BaseModel):
    face_id: str


class FaceCompareRequest(BaseModel):
    pass


class FaceSearchRequest(BaseModel):
    image_url: str = ""
    top_k: int = 5


class PlateWhitelistUpdateRequest(BaseModel):
    plates: list[str]


class PlateWhitelistAddRequest(BaseModel):
    plate_number: str


class PlateWhitelistRemoveRequest(BaseModel):
    plate_number: str


class PlateRecognizeRequest(BaseModel):
    image_url: str = ""


class BehaviorIntrusionZoneRequest(BaseModel):
    polygon: list[list[int]]


class BehaviorAnalyzeRequest(BaseModel):
    image_url: str = ""


@router.get("/runtime/ai_face_recognition/faces")
async def ai_face_list_faces(
    current_user: User = Depends(deps.get_current_active_user),
):
    try:
        mod = plugin_manager.plugins.get("ai_face_recognition")
        if mod and hasattr(mod, "list_faces"):
            faces = mod.list_faces()
            return {"faces": faces, "total": len(faces)}
        return {"faces": [], "total": 0}
    except Exception as e:
        logger.warning(f"AI face list error: {e}")
        return {"faces": [], "total": 0}


@router.post("/runtime/ai_face_recognition/faces/register")
async def ai_face_register(
    payload: FaceRegisterRequest,
    current_user: User = Depends(deps.get_current_active_user),
):
    try:
        mod = plugin_manager.plugins.get("ai_face_recognition")
        if mod and hasattr(mod, "register_face"):
            result = mod.register_face(
                face_id=payload.face_id,
                name=payload.name,
                image_url=payload.image_url,
            )
            return result
        return {"success": False, "error": "插件未加载"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/runtime/ai_face_recognition/faces/register-upload")
async def ai_face_register_upload(
    face_id: str = Query(...),
    name: str = Query(...),
    file: UploadFile = File(...),
    current_user: User = Depends(deps.get_current_active_user),
):
    try:
        mod = plugin_manager.plugins.get("ai_face_recognition")
        if not mod or not hasattr(mod, "register_face"):
            return {"success": False, "error": "插件未加载"}
        image_data = await file.read()
        result = mod.register_face(face_id=face_id, name=name, image_data=image_data)
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/runtime/ai_face_recognition/faces/unregister")
async def ai_face_unregister(
    payload: FaceUnregisterRequest,
    current_user: User = Depends(deps.get_current_active_user),
):
    try:
        mod = plugin_manager.plugins.get("ai_face_recognition")
        if mod and hasattr(mod, "unregister_face"):
            return mod.unregister_face(payload.face_id)
        return {"success": False, "error": "插件未加载"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/runtime/ai_face_recognition/compare")
async def ai_face_compare(
    file1: UploadFile = File(...),
    file2: UploadFile = File(...),
    current_user: User = Depends(deps.get_current_active_user),
):
    try:
        mod = plugin_manager.plugins.get("ai_face_recognition")
        if not mod or not hasattr(mod, "compare_faces"):
            return {"success": False, "error": "插件未加载"}
        data1 = await file1.read()
        data2 = await file2.read()
        return mod.compare_faces(data1, data2)
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/runtime/ai_face_recognition/search")
async def ai_face_search(
    payload: FaceSearchRequest,
    current_user: User = Depends(deps.get_current_active_user),
):
    try:
        mod = plugin_manager.plugins.get("ai_face_recognition")
        if mod and hasattr(mod, "search_face"):
            return mod.search_face(image_url=payload.image_url, top_k=payload.top_k)
        return {"success": False, "error": "插件未加载"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/runtime/ai_face_recognition/search-upload")
async def ai_face_search_upload(
    file: UploadFile = File(...),
    top_k: int = Query(default=5),
    current_user: User = Depends(deps.get_current_active_user),
):
    try:
        mod = plugin_manager.plugins.get("ai_face_recognition")
        if not mod or not hasattr(mod, "search_face"):
            return {"success": False, "error": "插件未加载"}
        image_data = await file.read()
        return mod.search_face(image_data=image_data, top_k=top_k)
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/runtime/ai_plate_recognition/whitelist")
async def ai_plate_get_whitelist(
    current_user: User = Depends(deps.get_current_active_user),
):
    try:
        mod = plugin_manager.plugins.get("ai_plate_recognition")
        if mod and hasattr(mod, "get_whitelist"):
            plates = mod.get_whitelist()
            return {"plates": plates, "total": len(plates)}
        return {"plates": [], "total": 0}
    except Exception as e:
        logger.warning(f"AI plate whitelist error: {e}")
        return {"plates": [], "total": 0}


@router.put("/runtime/ai_plate_recognition/whitelist")
async def ai_plate_set_whitelist(
    payload: PlateWhitelistUpdateRequest,
    current_user: User = Depends(deps.get_current_active_user),
):
    try:
        mod = plugin_manager.plugins.get("ai_plate_recognition")
        if mod and hasattr(mod, "set_whitelist"):
            return mod.set_whitelist(payload.plates)
        return {"success": False, "error": "插件未加载"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/runtime/ai_plate_recognition/whitelist/add")
async def ai_plate_add_whitelist(
    payload: PlateWhitelistAddRequest,
    current_user: User = Depends(deps.get_current_active_user),
):
    try:
        mod = plugin_manager.plugins.get("ai_plate_recognition")
        if mod and hasattr(mod, "add_to_whitelist"):
            return mod.add_to_whitelist(payload.plate_number)
        return {"success": False, "error": "插件未加载"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/runtime/ai_plate_recognition/whitelist/remove")
async def ai_plate_remove_whitelist(
    payload: PlateWhitelistRemoveRequest,
    current_user: User = Depends(deps.get_current_active_user),
):
    try:
        mod = plugin_manager.plugins.get("ai_plate_recognition")
        if mod and hasattr(mod, "remove_from_whitelist"):
            return mod.remove_from_whitelist(payload.plate_number)
        return {"success": False, "error": "插件未加载"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/runtime/ai_plate_recognition/recognize")
async def ai_plate_recognize(
    payload: PlateRecognizeRequest,
    current_user: User = Depends(deps.get_current_active_user),
):
    try:
        mod = plugin_manager.plugins.get("ai_plate_recognition")
        if mod and hasattr(mod, "recognize_plate_image"):
            return mod.recognize_plate_image(image_url=payload.image_url)
        return {"success": False, "error": "插件未加载"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/runtime/ai_plate_recognition/recognize-upload")
async def ai_plate_recognize_upload(
    file: UploadFile = File(...),
    current_user: User = Depends(deps.get_current_active_user),
):
    try:
        mod = plugin_manager.plugins.get("ai_plate_recognition")
        if not mod or not hasattr(mod, "recognize_plate_image"):
            return {"success": False, "error": "插件未加载"}
        image_data = await file.read()
        return mod.recognize_plate_image(image_data=image_data)
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/runtime/ai_behavior_analysis/intrusion-zone")
async def ai_behavior_set_intrusion_zone(
    payload: BehaviorIntrusionZoneRequest,
    current_user: User = Depends(deps.get_current_active_user),
):
    try:
        mod = plugin_manager.plugins.get("ai_behavior_analysis")
        if mod and hasattr(mod, "set_intrusion_zone"):
            return mod.set_intrusion_zone(payload.polygon)
        return {"success": False, "error": "插件未加载"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/runtime/ai_behavior_analysis/analyze")
async def ai_behavior_analyze(
    payload: BehaviorAnalyzeRequest,
    current_user: User = Depends(deps.get_current_active_user),
):
    try:
        mod = plugin_manager.plugins.get("ai_behavior_analysis")
        if mod and hasattr(mod, "analyze_image"):
            return mod.analyze_image(image_url=payload.image_url)
        return {"success": False, "error": "插件未加载"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/runtime/ai_behavior_analysis/analyze-upload")
async def ai_behavior_analyze_upload(
    file: UploadFile = File(...),
    current_user: User = Depends(deps.get_current_active_user),
):
    try:
        mod = plugin_manager.plugins.get("ai_behavior_analysis")
        if not mod or not hasattr(mod, "analyze_image"):
            return {"success": False, "error": "插件未加载"}
        image_data = await file.read()
        return mod.analyze_image(image_data=image_data)
    except Exception as e:
        return {"success": False, "error": str(e)}
