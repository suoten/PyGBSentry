#!/usr/bin/env python3
"""PyGBSentry 根目录启动入口。

委托到 backend/run_server.py，使 IDE 和自动化工具能从项目根目录发现入口文件。

使用方式：
    python run.py                  # 启动后端服务
    python run.py --host 0.0.0.0 --port 8000
"""
import os
import sys

# 将 backend 目录加入 sys.path，使 import app.* 可解析
_backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# 委托到后端启动脚本
from run_server import main  # type: ignore[import-not-found]

if __name__ == "__main__":
    main()
