# sermon.freely.church. Build from the repository root (Coolify: base directory "/", Dockerfile "/saas/Dockerfile"),
# so the app file pulpit-binder.html comes along beside the server.
FROM node:22-bookworm-slim AS build
WORKDIR /app/saas
RUN apt-get update && apt-get install -y --no-install-recommends python3 make g++ ca-certificates && rm -rf /var/lib/apt/lists/*
COPY saas/package.json saas/package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund

FROM node:22-bookworm-slim
ENV NODE_ENV=production PORT=3000 DATA_DIR=/data
WORKDIR /app/saas
COPY --from=build /app/saas/node_modules ./node_modules
COPY saas/package.json ./
COPY saas/server ./server
COPY saas/web ./web
COPY pulpit-binder.html /app/pulpit-binder.html
RUN mkdir -p /data && chown -R node:node /data
USER node
VOLUME ["/data"]
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:'+(process.env.PORT||3000)+'/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "server/index.js"]
