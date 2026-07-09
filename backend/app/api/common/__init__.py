"""共享 API 路由包（跨版本通用端点）。

包含 ``channel``（通道通用操作）与 ``play_start``（点播启动）两个路由模块，
由 ``app/main.py`` 直接挂载到 ``/api/common/channel`` 与 ``/api/play`` 路径下，
独立于版本化的 ``app/api/v1`` 路由。
"""
