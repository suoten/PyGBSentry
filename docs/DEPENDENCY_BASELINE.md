# 开源版依赖基线说明

本文档用于冻结开源版当前通过验证的依赖版本组合，便于后续升级、回滚与环境排查。

## 1. 基线范围

- 后端依赖文件：`editions/open-source/backend/requirements.txt`
- 前端运行时约束：`editions/open-source/frontend/package.json`（Node.js `>=20`）
- 前端构建镜像：`editions/open-source/frontend/Dockerfile`（`node:20-alpine`）
- 开源后端 CI：`.github/workflows/open-source-backend-ci.yml`

## 2. 后端冻结版本

以下为当前已升级并通过单元测试的核心版本：

- fastapi==0.115.12
- uvicorn==0.34.0
- sqlalchemy==2.0.39
- alembic==1.14.1
- pydantic==2.10.6
- pydantic-settings==2.8.1
- requests==2.32.4
- httpx==0.27.2
- python-multipart==0.0.20
- redis[hiredis]==5.2.1
- websockets==14.2
- loguru==0.7.3
- psutil==6.1.1
- asyncpg==0.30.0
- aiomysql==0.3.2
- aiosqlite==0.21.0
- cachetools==5.5.2
- orjson==3.10.18

完整清单以 [requirements.txt](file:///e:/硕腾网络/PyGBSentry/PyGBSentry/editions/open-source/backend/requirements.txt) 为准。

## 3. 校验口径

- 本地校验命令：
  - `python -m unittest discover -s tests -p "test_*.py" -v`
- CI 校验流程：
  - 安装 `requirements.txt`
  - 执行同等价的 `unittest discover`
  - 文件： [open-source-backend-ci.yml](file:///e:/硕腾网络/PyGBSentry/PyGBSentry/.github/workflows/open-source-backend-ci.yml)

## 4. 回滚策略

当新版本出现兼容问题时，按以下顺序回滚：

1. 先回滚单个出问题的包到上一稳定版本。
2. 若问题涉及框架联动（FastAPI / Pydantic / Starlette），按同批次整体回滚。
3. 回滚后立即执行后端全量单测与关键链路冒烟（登录、设备、点播、录像、插件相关接口）。

## 5. 后续升级建议

- 优先继续“单批次小步升级 + 每批全量回归”策略。
- 涉及网络协议与数据库驱动（websockets / asyncpg / aiomysql）时，优先在独立虚拟环境验证。
- 建议将生产镜像构建也纳入同一依赖冻结口径，避免“本地过、线上不过”的漂移问题。
