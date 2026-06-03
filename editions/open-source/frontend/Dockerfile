# Frontend Dockerfile
FROM node:20-alpine as build-stage

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .
RUN npm run build

# Production Stage
FROM nginx:stable-alpine as production-stage

COPY --from=build-stage /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
