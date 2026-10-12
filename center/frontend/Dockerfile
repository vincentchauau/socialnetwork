# Build context is the repo root (see shared/infra/docker-compose.yml).
# Next's standalone output keeps the monorepo layout, so the paths below mirror it.
FROM node:22-alpine AS build
WORKDIR /srv
COPY shared/frontend ./shared/frontend
COPY center/frontend/package.json center/frontend/package-lock.json ./center/frontend/
RUN cd center/frontend && npm ci
COPY center/frontend ./center/frontend
RUN cd center/frontend && npm run build

FROM node:22-alpine
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /srv
COPY --from=build /srv/center/frontend/.next/standalone ./
COPY --from=build /srv/center/frontend/.next/static ./center/frontend/.next/static
USER node
EXPOSE 3000
CMD ["node", "center/frontend/server.js"]
