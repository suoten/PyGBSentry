import asyncio
from loguru import logger

try:
    import cv2  # type: ignore
except Exception:  # ImportError or binary load error
    logger.warning("cv2 导入失败，AI 视觉功能不可用")
    cv2 = None

try:
    import numpy as np  # type: ignore
except Exception:
    logger.warning("numpy 导入失败，AI 视觉功能不可用")
    np = None
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.stream_session import StreamSession
from app.models.alarm import Alarm
from app.models.alarm_escalation import AlarmEscalation
from app.api.v1.endpoints.alarms import alarm_manager
from sqlalchemy import select  # TECH_DEBT: 直接依赖具体实现，未来改为Protocol接口注入
from datetime import datetime, timezone

try:
    from ultralytics import YOLO  # type: ignore
except Exception:
    logger.warning("ultralytics YOLO 导入失败，AI 视觉功能不可用")
    YOLO = None



class VisionHub:
    def __init__(self):
        self.running = False
        self.model = None
        self.check_interval = 5 # Seconds between checks per stream
        self._executor = None # Thread pool for OpenCV/YOLO
        self._processing_streams = set() # Avoid overlapping processing
        self.enabled = True

    async def start(self):
        if not bool(getattr(settings, "VISION_HUB_ENABLED", False)):
            self.enabled = False
            logger.info("AI Vision Hub disabled by config (VISION_HUB_ENABLED=false).")
            return
        if cv2 is None or YOLO is None:
            self.enabled = False
            logger.warning(
                "AI Vision Hub disabled: missing optional dependencies (%s%s).",
                "cv2 " if cv2 is None else "",
                "ultralytics " if YOLO is None else "",
            )
            return
        try:
            from concurrent.futures import ThreadPoolExecutor
            self._executor = ThreadPoolExecutor(max_workers=4) # Concurrent streams

            # Load YOLOv8n model
            self.model = YOLO("yolov8n.pt")

            # Optional: Move to GPU if available
            import torch
            if torch.cuda.is_available():
                self.model.to("cuda")
                logger.info("AI Vision Hub using CUDA GPU acceleration")
            else:
                logger.info("AI Vision Hub using CPU (No CUDA found)")

            logger.info("AI Vision Hub started with YOLOv8n")
            self.running = True
            asyncio.create_task(self._run_loop())
        except Exception as e:
            logger.error(f"Failed to start AI Vision Hub: {e}")

    async def stop(self):
        self.running = False
        if self._executor:
            self._executor.shutdown(wait=False)

    async def _run_loop(self):
        while self.running:
            try:
                async with AsyncSessionLocal() as session:
                    stmt = select(StreamSession).where(StreamSession.stream.isnot(None))
                    result = await session.execute(stmt)
                    streams = result.scalars().all()

                    for stream in streams:
                        if stream.stream not in self._processing_streams:
                            asyncio.create_task(self._process_stream_safe(stream))

            except Exception as e:
                logger.error(f"Vision loop error: {e}")

            await asyncio.sleep(self.check_interval)

    async def _process_stream_safe(self, stream: StreamSession):
        self._processing_streams.add(stream.stream)
        try:
            async with AsyncSessionLocal() as session:
                await self._process_stream(stream, session)
        finally:
            self._processing_streams.remove(stream.stream)

    async def _process_stream(self, stream: StreamSession, session):
        # Prefer RTSP for lower latency in snapshot capture if possible
        # Here we use FLV from ZLM for consistency
        stream_url = f"http://{settings.MEDIA_SERVER_HOST}:{settings.MEDIA_SERVER_HTTP_PORT}/live/{stream.stream}.live.flv"

        try:
            loop = asyncio.get_running_loop()
            detections = await loop.run_in_executor(self._executor, self._detect, stream_url)

            if detections:
                unique_labels = set([d[0] for d in detections])
                for label in unique_labels:
                    conf = max([d[1] for d in detections if d[0] == label])
                    logger.warning(f"AI Detected {label} ({conf:.2f}) on {stream.stream}")

                    alarm = Alarm(
                        tenant_id="default",
                        device_id=stream.asset_id,
                        channel_id=stream.resource_id,
                        priority="1",
                        method="5",
                        time=datetime.now(timezone.utc),
                        description=f"AI Alert: {label.capitalize()} detected (Conf: {conf:.2f})",
                        alarm_type="AI",
                        status=0
                    )
                    session.add(alarm)
                    await session.flush()
                    escalation = AlarmEscalation(alarm_id=alarm.id, state="open", escalation_level=0, escalation_count=0)
                    session.add(escalation)

                    alarm_data = {
                        "id": alarm.id,
                        "device_id": alarm.device_id,
                        "time": alarm.time.isoformat(),
                        "description": alarm.description,
                        "priority": alarm.priority,
                        "escalation_level": 0,
                        "escalation_state": "open"
                    }
                    asyncio.create_task(alarm_manager.broadcast_alarm(alarm_data))

                await session.commit()

        except Exception as e:
            logger.error(f"AI stream process error: {e}", exc_info=True)

    def _detect(self, stream_url):
        if cv2 is None or self.model is None:
            return None

        # Explicitly use FFMPEG backend to avoid CAP_IMAGES fallback when connection fails
        cap = cv2.VideoCapture(stream_url, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            return None

        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        for _ in range(3): # Clear buffer
            ret, frame = cap.read()

        cap.release()

        if not ret:
            return None

        results = self.model(frame, verbose=False, imgsz=320)

        detections = []
        for r in results:
            for box in r.boxes:
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                label = self.model.names[cls]

                # Dynamic thresholds
                thresholds = {"person": 0.45, "car": 0.5, "dog": 0.5, "cat": 0.5}
                if label in thresholds and conf > thresholds[label]:
                    detections.append((label, conf))

        return detections

# Singleton
vision_hub = None
