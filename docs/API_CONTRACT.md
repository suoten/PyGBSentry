# API 契约与稳定性承诺

> PyGBSentry 把 `/api/v1/*` 视为对外契约。本文说明我们向后兼容的口径、CI 如何强制执行,
> 以及你(集成者/应用开发者)可以依赖什么。

## 兼容性口径(只增不减)

| 变更类型 | minor 版本内 | 处理方式 |
|:---|:---|:---|
| **新增**端点 / 字段 | ✅ 允许 | 不影响调用方 |
| **删除**已发布端点 | ❌ 禁止 | 先公告弃用周期(至少一个 minor 版本 + `deprecated` 标记),大版本才移除 |
| **变更** HTTP 方法 | ❌ 禁止 | 同上 |
| 字段改名 / 类型变更 | ❌ 禁止 | 字段演进遵循"只加不改不删";废弃字段保留返回(置空) |
| 行为语义变更 | ❌ 谨慎 | 错误码/分页语义等在 CHANGELOG 明确公告 |

## CI 如何强制

- 基线:`backend/tests/api_contract_baseline.json` 记录 `/api/v1` 下全部 533 个路径、605 个端点的
  path → method 集合(生成时间:2026-11-21);
- `backend/tests/test_api_contract.py::test_api_contract_no_removals` 在每次 CI 中把当前
  OpenAPI schema 与基线对比,**删除端点或移除方法会直接使 CI 失败**;
- 守卫本身有负向单测(`test_removal_detection_logic`),防止守卫失效。

## 给集成者的建议

1. 依赖 `/api/v1` 下已存在的端点与字段,不要解析未文档化的内部字段;
2. 登录令牌通过 `Authorization: Bearer <token>`;播放地址自带 300s HMAC `token` 参数,
   不要自行拼接或复用过期令牌;
3. 升级版本前查阅 CHANGELOG 的「破坏性变更」小节——出现该小节意味着需要行动;
4. 需要长期稳定集成的场景(如嵌入播放)使用 `/api/v1/embed/links` 签名的嵌入页,
   它的令牌口径同样受本契约约束。

## 维护者:如何做一次破坏性变更(最后手段)

1. 在目标端点加 `deprecated=true`(OpenAPI)与 `Sunset` 响应头,公告弃用周期;
2. 至少保留一个 minor 版本的双跑期;
3. 大版本发布前运行 `python scripts/update_api_contract_baseline.py` 刷新基线,
   并在 CHANGELOG「破坏性变更」小节列出完整清单(端点、替代方案、迁移步骤)。
