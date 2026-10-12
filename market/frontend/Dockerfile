# Build context is the repo root (see shared/infra/docker-compose.yml).
# Next's standalone output keeps the monorepo layout, so the paths below mirror it.
FROM node:22-alpine AS build
WORKDIR /srv
COPY shared/frontend ./shared/frontend
COPY market/frontend/package.json market/frontend/package-lock.json ./market/frontend/
RUN cd market/frontend && npm ci
COPY market/frontend ./market/frontend
RUN cd market/frontend && npm run build

FROM node:22-alpine
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /srv
COPY --from=build /srv/market/frontend/.next/standalone ./
COPY --from=build /srv/market/frontend/.next/static ./market/frontend/.next/static
USER node
EXPOSE 3000
CMD ["node", "market/frontend/server.js"]
