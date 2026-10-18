# PyGBSentrySetup — Windows 一键安装向导

单个 exe（约 10MB），双击即完成全部安装。目标用户：完全不懂程序的人。

## 用户视角的使用方式

1. 下载 `PyGBSentrySetup.exe`（发布在 Gitee Releases / 网盘）
2. 双击 → 点「开始安装」→ 等进度条（自动完成：Python 检测或静默安装 →
   下载源码 → 依赖 → 配置/数据库 → 桌面快捷方式 → 自动启动并打开浏览器）
3. 按提示输入 admin / ADMIN_PASSWORD.txt 里的密码，开始使用

## 重新打包 exe

```bash
pip install pyinstaller
cd packaging/windows
python -m PyInstaller --onefile --noconsole --name PyGBSentrySetup PyGBSentrySetup.py
# 产物：dist/PyGBSentrySetup.exe
```

## 分发建议

- 把 exe 上传到 Gitee Releases（随版本发布），README 快速开始指向它
- exe 依赖网络（下载源码与依赖）；离线场景用便携版（`make_portable.py` 产物）

## 无头模式（CI/测试）

```
PyGBSentrySetup.exe --headless --target D:\PyGBSentry
PyGBSentrySetup.exe --headless --source <本地仓库路径> --target <目录>   # 跳过下载
PyGBSentrySetup.exe --headless --skip-python-check                       # 跳过 Python 检测
```

## 已知边界

- Python 静默安装需要联网；企业内网如拦截 python.org，请先手动装 Python 3.12
- 目标安装路径默认 `C:\PyGBSentry`，已存在非空目录会提示更换
- 卸载 = 停止服务后删除安装目录 + 桌面快捷方式
