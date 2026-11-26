# FIXED-P2: R4-04 使用pnpm替代npm，与项目锁文件一致
# DEVOPS: node:20 LTS 已于 2026-04 EOL，升级到 node:22-alpine（当前活跃 LTS）
FROM node:22-alpine AS build-stage

WORKDIR /app

# 可选镜像源构建参数：默认官方源；国内网络构建时传
# --build-arg NPM_REGISTRY=https://registry.npmmirror.com
ARG NPM_REGISTRY=https://registry.npmjs.org
ENV NPM_CONFIG_REGISTRY=${NPM_REGISTRY}
ENV COREPACK_NPM_REGISTRY=${NPM_REGISTRY}

# FIXED [issue IKMFK8]: pnpm@latest 已进入 12.x，会对未声明的依赖构建脚本直接报
# ERR_PNPM_IGNORED_BUILDS 错误导致构建失败。锁定到与 pnpm-lock.yaml（lockfileVersion 9.0）
# 兼容的 pnpm 10.x，并在 package.json 的 pnpm.onlyBuiltDependencies 中显式放行所需构建脚本。
RUN corepack enable && corepack prepare pnpm@10.34.9 --activate

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
# TS 债务专项已清零（2026-11-26 vue-tsc 0 错误），恢复 build:full（含 vue-tsc 类型检查）
# [历史] 原 459 个 TS 严格性错误导致构建失败而临时降级为 build，现已恢复
RUN pnpm run build:full

# Production Stage
FROM nginx:stable-alpine AS production-stage

COPY --from=build-stage /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# FIX: 非 root 运行（USER nginx）时 nginx 无法自建缓存目录，须在切用户前预建并授权
# 否则启动即报 mkdir /var/cache/nginx/client_temp permission denied
RUN mkdir -p /var/cache/nginx/client_temp /var/cache/nginx/proxy_temp \
             /var/cache/nginx/fastcgi_temp /var/cache/nginx/uwsgi_temp \
             /var/cache/nginx/scgi_temp \
    && chown -R nginx:nginx /var/cache/nginx /var/run /etc/nginx/conf.d \
    && touch /run/nginx.pid && chown nginx:nginx /run/nginx.pid

# P1-52: 非 root 运行 + 健康检查
USER nginx
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q --spider http://localhost/ || exit 1

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
