# 开源版后端与插件目录说明

- **plugins/**：运行时插件安装目录。用户从插件市场安装的插件会解压到此目录；启动时从此处加载。开源版不包含插件源码与打包产出。
- **plugin_packages/**、**plugins_dist/**：已迁移至服务器版 `editions/server/backend/`。插件源码（plugin_packages）与打包产出（plugins_dist）归属服务器版，用于发布与市场分发；开源版通过 `PLUGIN_MARKETPLACE_BASE_URL` 拉取目录并从市场安装。若本地仍存在 `plugin_packages` 或 `plugins_dist` 目录，可手动删除。联调时运行 `python tools/build_plugins.py --install` 可将服务器版打包结果安装到本目录 `plugins/`。
