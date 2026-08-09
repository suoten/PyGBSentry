import asyncio
import os
from loguru import logger
from app.services.ssl_certbot.certbot_config import CertbotSettings



_lock = asyncio.Lock()


async def certbot_certonly(cfg: CertbotSettings) -> tuple[int, str]:
    async with _lock:
        args = _build_certonly_args(cfg)
        logger.info("Running certbot certonly: %s", " ".join(args))
        try:
            if cfg.mode == "standalone":
                await _stop_nginx()
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                output = "certbot certonly timed out (120s)"
                logger.error(output)
                return 1, output
            output = stdout.decode(errors="replace").strip()
            if proc.returncode == 0:
                logger.info("certbot certonly succeeded for %s", cfg.domain)
            else:
                logger.error("certbot certonly failed (rc=%d): %s", proc.returncode, output[:500])
            return proc.returncode or 1, output
        except Exception as e:
            logger.error("certbot certonly exception: %s", e)
            return 1, str(e)
        finally:
            if cfg.mode == "standalone":
                await _start_nginx()


async def certbot_renew(cfg: CertbotSettings) -> tuple[int, str]:
    async with _lock:
        args = [
            "certbot", "renew", "--quiet",
            "--config-dir", cfg.config_dir,
            "--work-dir", cfg.work_dir,
            "--logs-dir", cfg.logs_dir,
        ]
        logger.info("Running certbot renew")
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                output = "certbot renew timed out (120s)"
                logger.error(output)
                return 1, output
            output = stdout.decode(errors="replace").strip()
            if proc.returncode == 0:
                logger.info("certbot renew succeeded")
            else:
                logger.error("certbot renew failed (rc=%d): %s", proc.returncode, output[:500])
            return proc.returncode or 1, output
        except Exception as e:
            logger.error("certbot renew exception: %s", e)
            return 1, str(e)


def _build_certonly_args(cfg: CertbotSettings) -> list[str]:
    args = [
        "certbot", "certonly",
        "--non-interactive",
        "--agree-tos",
        "--email", cfg.email,
        "-d", cfg.domain,
        "--config-dir", cfg.config_dir,
        "--work-dir", cfg.work_dir,
        "--logs-dir", cfg.logs_dir,
    ]
    if cfg.mode == "webroot":
        os.makedirs(cfg.webroot_path, exist_ok=True)
        args.extend(["--webroot", "--webroot-path", cfg.webroot_path])
    elif cfg.mode == "standalone":
        args.append("--standalone")
    return args


async def _stop_nginx() -> None:
    try:
        proc = await asyncio.create_subprocess_exec(
            "nginx", "-s", "stop",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=10.0)
    except Exception as e:
        logger.warning("Failed to stop nginx for standalone mode: %s", e)


async def _start_nginx() -> None:
    try:
        proc = await asyncio.create_subprocess_exec(
            "nginx",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=10.0)
    except Exception as e:
        logger.warning("Failed to start nginx after standalone mode: %s", e)
