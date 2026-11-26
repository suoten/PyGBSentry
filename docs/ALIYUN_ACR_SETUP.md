# 阿里云 ACR 国内镜像配置指南（5 分钟，一次配置永久自动）

> 目标：每次 `git tag v1.x.x` 发布时，CI 自动把 backend / frontend 镜像同步推送到
> 阿里云 ACR，国内用户直接 `docker pull`，不再依赖 ghcr.io 或 daocloud 代理。
>
> release.yml 中的推送步骤已就绪（`Push images to Aliyun ACR (CN mirror)`），
> **只要配好下述 3 个 GitHub Secrets，自动生效**；未配置时该步骤自动跳过，不影响发布。

## 1. 开通阿里云容器镜像服务（免费个人版）

1. 登录[阿里云控制台](https://home.console.aliyun.com/)，搜索「**容器镜像服务**」
2. 选择「**个人版实例**」（免费）并开通，首次会要求设置 **Registry 登录固定密码**（记下来，第 3 步要用；这不是阿里云账号密码）

## 2. 创建命名空间

1. 控制台左侧「**命名空间管理**」→ 创建命名空间（如 `suoten`）
2. 记下你的 **Registry 地址**（在实例概览/访问凭证页可见），两种格式都正常：
   - 新版个人版实例：`crpi-xxxxxx.<地域>.personal.cr.aliyuncs.com`（如 `crpi-xk6rexdt9rmbqr8l.cn-zhangjiakou.personal.cr.aliyuncs.com`）
   - 旧版经典实例：`registry.cn-<地域>.aliyuncs.com`（如 `registry.cn-hangzhou.aliyuncs.com`）
   - **Secret 只填主机名部分**（不含命名空间/仓库名，工作流自动拼接）
3. **建议**：在命名空间设置里开启「自动创建仓库」（push 时自动建 repo）；
   若不开启，请手动创建两个仓库：`pygbsentry`、`pygbsentry-frontend`
4. 每个仓库建议设为「**公开**」——国内用户拉取免登录（私有则拉取需 `docker login`）

## 3. 配置 GitHub Secrets（3 个）

仓库页面 → **Settings → Secrets and variables → Actions → New repository secret**，逐个添加：

| Secret 名称 | 值 | 说明 |
|---|---|---|
| `ALIYUN_ACR_REGISTRY` | `crpi-xxxxxx.cn-zhangjiakou.personal.cr.aliyuncs.com` | Registry 主机名（不含命名空间/仓库名） |
| `ALIYUN_ACR_USERNAME` | （见下方说明） | ACR 登录用户名 |
| `ALIYUN_ACR_PASSWORD` | （你设置的固定密码） | ACR 固定密码 |

> **用户名在哪看**：个人版控制台「访问凭证」页面直接展示登录用户名
> （通常是阿里云账号全名，如 `yourname@aliyun.com` 或主账号 ID）。
> 用「固定密码」登录，**不要**用阿里云账号登录密码。

## 4. 触发与验证

```bash
# 任意打一个 tag 即触发（或等下次正式发版）
git tag v1.0.1
git push origin v1.0.1
```

在 GitHub → Actions → Release 工作流里，看到
**Push images to Aliyun ACR (CN mirror)** 步骤变绿即成功。

本地验证国内源：

```bash
docker pull registry.cn-hangzhou.aliyuncs.com/suoten/pygbsentry:latest
docker pull registry.cn-hangzhou.aliyuncs.com/suoten/pygbsentry-frontend:latest
```

## 5. 自动化范围

配置一次后，此后**每次发版全自动**：tag → CI 构建 backend/frontend → 推
ghcr.io（`vX.Y.Z` + `latest`）→ 同步推阿里云 ACR（`vX.Y.Z` + `latest`）。
`demo.sh` 与 `docker compose up -d` 无需任何改动。

## 6. 可选：让 demo.sh 默认走国内源

国内用户克隆后，在 `.env` 中加一行即可切换镜像来源（在
`docker-compose.simulator.yml` 中以 `IMAGE_PREFIX` 方式支持时——当前版本
预构建镜像名写死在 `docker-compose.yml`，国内用户可直接用
`ghcr.m.daocloud.io` 代理，无需 ACR 也够用）。

## 常见问题

| 现象 | 原因 |
|------|------|
| ACR 推送 401 unauthorized | PASSWORD 用的是阿里云登录密码而非 ACR 固定密码，回「访问凭证」页重设 |
| push 报 denied: repository does not exist | 命名空间没开「自动创建仓库」且未手动建仓库，回第 2 步 |
| 国内拉取要登录 | 仓库设为私有了，回第 2 步第 4 点改公开 |
