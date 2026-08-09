# -------------------------------------------------------------------------
# 🚀 Project: PyGBSentry
# ✍️ Author: suoten
# 📧 Email: suoten@163.com
# 📄 License: AGPL-3.0-or-later WITH Classpath-Exception
# -------------------------------------------------------------------------
"""
PyGBSentry 后端启动脚本。

FIX: [2026-07-04] Windows 平台默认使用 ProactorEventLoop，其 UDP 实现存在已知问题
(datagram_received 延迟回调/高并发丢包)，导致 SIP UDP 传输不响应。
此脚本在 uvicorn 创建事件循环之前设置 WindowsSelectorEventLoopPolicy，
确保 SIP UDP 传输可靠工作。

使用方式：
    python run_server.py
    python run_server.py --host 0.0.0.0 --port 8000
"""
import sys
import asyncio

# FIX: [2026-07-04] 必须在 uvicorn 创建事件循环之前设置 SelectorEventLoop 策略，
# 否则 app.main 中的 set_event_loop_policy 太晚（uvicorn 已用 ProactorEventLoop 创建循环）。
# 根因：uvicorn 的 Server.run() → asyncio.run() 在导入 app 模块之前就已创建事件循环。
# 修复：通过独立启动脚本在 uvicorn 启动前设置策略。 [全栈工程师]
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn
from app.core.config import settings


def main():
    host = settings.HOST or "0.0.0.0"
    port = settings.PORT or 8000

    # 允许命令行参数覆盖配置
    if "--host" in sys.argv:
        idx = sys.argv.index("--host")
        if idx + 1 < len(sys.argv):
            host = sys.argv[idx + 1]
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        if idx + 1 < len(sys.argv):
            port = int(sys.argv[idx + 1])

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        # 显式指定 asyncio 循环（Windows 下会使用上方设置的 SelectorEventLoop）
        loop="asyncio",
    )


if __name__ == "__main__":
    main()
