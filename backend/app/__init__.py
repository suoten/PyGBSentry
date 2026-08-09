"""PyGBSentry 开源版后端应用包。

显式的 ``__init__.py`` 使 ``app`` 成为常规包（regular package），避免被
Python 解析为命名空间包（namespace package）。当系统 ``site-packages`` 中
存在其他将 ``app`` 模块加入 ``sys.path`` 的 ``.pth`` 条目
时，常规包优先于命名空间包，从而防止导入污染。
"""
