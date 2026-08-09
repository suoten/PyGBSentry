import os  # S-14 添加os导入，第37行os.path.basename依赖此模块
import subprocess
import threading
import time
import shlex
from dataclasses import dataclass
from loguru import logger


@dataclass
class FfmpegProcessInfo:
    source_id: str
    cmd: str
    started_at: float
    proc: subprocess.Popen


class FfmpegProxyManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._procs: dict[str, FfmpegProcessInfo] = {}

    def start(self, source_id: str, cmd: str) -> FfmpegProcessInfo:
        sid = str(source_id or "").strip()
        if not sid:
            raise ValueError("source_id required")
        c = str(cmd or "").strip()
        if not c:
            raise ValueError("cmd required")

        with self._lock:
            self.stop(sid)
            cmd_args = shlex.split(c)
            # W-11 校验可执行文件路径，防止命令注入
            if cmd_args:
                import shutil
                ffmpeg_path = shutil.which(cmd_args[0])
                if not ffmpeg_path or "ffmpeg" not in os.path.basename(ffmpeg_path).lower():
                    raise ValueError(f"Executable must be ffmpeg, got: {cmd_args[0]}")
                cmd_args[0] = ffmpeg_path
            try:
                proc = subprocess.Popen(
                    cmd_args,
                    shell=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
            except (FileNotFoundError, OSError, PermissionError) as e:
                logger.error(f"FFmpeg start failed: {e}")
                raise ValueError(f"FFmpeg 进程启动失败: {e}") from e
            info = FfmpegProcessInfo(source_id=sid, cmd=c, started_at=time.time(), proc=proc)
            self._procs[sid] = info
            self._attach_logger(info)
            return info

    def stop(self, source_id: str) -> bool:
        sid = str(source_id or "").strip()
        if not sid:
            return False
        info = None
        with self._lock:
            info = self._procs.pop(sid, None)
        if not info:
            return False
        try:
            if info.proc.poll() is None:
                info.proc.terminate()
                try:
                    info.proc.wait(timeout=5)
                except Exception:
                    try:
                        info.proc.kill()
                    except Exception as e:
                        logger.warning(f"Error: {e}")
        except Exception as e:
            logger.warning(f"Error: {e}")
        # W-23 FFmpeg进程停止后关闭stdout管道，防止文件描述符泄漏
        finally:
            try:
                if info.proc.stdout:
                    info.proc.stdout.close()
            except Exception as _close_err:
                # FIX [2026-07-17 P3-20]: 描述性日志替代静默吞异常，便于发现 fd 泄漏
                logger.warning(f"ffmpeg_proxy_manager: failed to close stdout pipe for source '{getattr(info, 'source_id', '?')}': {_close_err}")
        return True

    def is_running(self, source_id: str) -> bool:
        sid = str(source_id or "").strip()
        if not sid:
            return False
        with self._lock:
            info = self._procs.get(sid)
        if not info:
            return False
        return info.proc.poll() is None

    def get(self, source_id: str) -> FfmpegProcessInfo | None:
        sid = str(source_id or "").strip()
        if not sid:
            return None
        with self._lock:
            return self._procs.get(sid)

    def _attach_logger(self, info: FfmpegProcessInfo) -> None:
        def _reader():
            try:
                assert info.proc.stdout is not None
                for line in info.proc.stdout:
                    if not line:
                        continue
                    logger.info("[ffmpeg:{}] {}", info.source_id, line.rstrip())
            except Exception as e:
                logger.warning(f"Error: {e}")

        t = threading.Thread(target=_reader, daemon=True)
        t.start()


ffmpeg_proxy_manager = FfmpegProxyManager()
