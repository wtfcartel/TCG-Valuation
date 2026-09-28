# syntax=docker/dockerfile:1
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY packages/engine/package.json packages/engine/
COPY apps/api/package.json apps/api/
COPY apps/web/package.json apps/web/
RUN npm ci --no-audit --no-fund
COPY tsconfig.base.json ./
COPY packages packages
COPY apps apps
RUN npm run build -w @cardcore/api && npm run build -w @cardcore/web

FROM node:22-alpine AS runtime
ENV NODE_ENV=production PORT=8080 WEB_DIST_DIR=/app/web PHOTO_STORAGE_DIR=/data/photos
WORKDIR /app/api
COPY package.json package-lock.json /app/
COPY packages/engine/package.json /app/packages/engine/
COPY apps/api/package.json /app/apps/api/
COPY apps/web/package.json /app/apps/web/
RUN cd /app && npm ci --omit=dev --workspace @cardcore/api --no-audit --no-fund && npm cache clean --force
COPY --from=build /app/apps/api/dist ./dist
COPY --from=build /app/apps/api/migrations ./migrations
COPY --from=build /app/apps/web/dist /app/web
RUN ln -s /app/node_modules ./node_modules && mkdir -p /data/photos && chown -R node:node /data
USER node
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD wget -qO- http://127.0.0.1:8080/api/health || exit 1
CMD ["node", "dist/server.js"]
