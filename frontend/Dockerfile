# FIXED-P2: R4-04 使用pnpm替代npm，与项目锁文件一致
# DEVOPS: node:20 LTS 已于 2026-04 EOL，升级到 node:22-alpine（当前活跃 LTS）
FROM node:22-alpine as build-stage

WORKDIR /app

RUN corepack enable && corepack prepare pnpm@latest --activate

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
# P1-21: 构建时显式执行类型检查（build:full = check + vue-tsc + vite build）
RUN pnpm run build:full

# Production Stage
FROM nginx:stable-alpine as production-stage

COPY --from=build-stage /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# P1-52: 非 root 运行 + 健康检查
USER nginx
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q --spider http://localhost/ || exit 1

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
