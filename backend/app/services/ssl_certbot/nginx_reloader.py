import sys
import asyncio
from loguru import logger
from app.services.ssl_certbot.certbot_config import CertbotSettings




async def reload_nginx(cfg: CertbotSettings) -> bool:
    if sys.platform != "linux":
        logger.debug("nginx reload skipped: not Linux platform")
        return False
    try:
        cmd = cfg.nginx_reload_cmd
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        if proc.returncode == 0:
            logger.info("nginx reload succeeded")
            return True
        else:
            logger.error(f"nginx reload failed (rc={proc.returncode}): {stderr.decode(errors='replace').strip()[:200]}")
            return False
    except asyncio.TimeoutError:
        logger.error("nginx reload timed out")
        return False
    except Exception as e:
        logger.error(f"nginx reload exception: {e}")
        return False
