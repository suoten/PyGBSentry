# PyGBSentry Tools 索引

本目录包含 PyGBSentry 的运维、安全、质量检查工具。

## 工具清单

### 环境与配置

| 工具 | 用途 | 用法 |
|------|------|------|
| `env_manager.py` | 环境配置切换与校验（dev/prod） | `python tools/env_manager.py switch --env prod` |
| `scan_config_security.py` | 配置安全扫描（占位符、弱密码、密钥泄露） | `python tools/scan_config_security.py --strict --root .` |

### 安全与审计

| 工具 | 用途 | 用法 |
|------|------|------|
| `verify_hash_chain.py` | 哈希链审计日志完整性校验 | `python tools/verify_hash_chain.py --log-file logs/audit.jsonl` |
| `check_plugin_display_metadata.py` | 插件展示元数据完整性检查 | `python tools/check_plugin_display_metadata.py` |
| `generate_market_keys.py` | 插件市场 Ed25519 密钥对生成 | `python tools/generate_market_keys.py` |

### 运行时检查

| 工具 | 用途 | 用法 |
|------|------|------|
| `query_runtime_events.py` | 运行时事件查询（设备上下线、流状态等） | `python tools/query_runtime_events.py --type device_online` |
| `check_runtime_coverage.py` | 运行时代码覆盖率检查 | `python tools/check_runtime_coverage.py` |

### 系统全面检查

| 工具 | 用途 | 用法 |
|------|------|------|
| `system_check/run_check.py` | 系统全面健康检查（前后端 API 一致性、UX 质量、健壮性等） | `python tools/system_check/run_check.py --edition open-source --format markdown` |
| `export_openapi.py` | 导出 FastAPI OpenAPI 规范（版本与代码绑定） | `python tools/export_openapi.py --output docs/openapi.json` |

`system_check/` 子目录结构：
- `analyzers/` — 分析器（API 一致性、健壮性、可用性、UX 质量、扩展性、stub 扫描）
- `parsers/` — 解析器（Python AST、Vue SFC、TS 类型、前端 API、后端路由）
- `reporters/` — 报告器（Markdown、JSON、聚合器）
- `shared/` — 共享组件（配置、模型、路径匹配、类型映射、版本隔离、消毒器）

### 性能测试

| 工具 | 用途 | 用法 |
|------|------|------|
| `perf/p5/p5_load_test.py` | P5 级负载压力测试 | `python tools/perf/p5/p5_load_test.py --concurrency 100` |

## CI 集成

以下工具已集成到 GitHub Actions CI（见 `.github/workflows/ci.yml`）：

- `scan_config_security.py --strict` — config-security job
- `system_check/run_check.py` — config-security job（生成报告 artifact）
