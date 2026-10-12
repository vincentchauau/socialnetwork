# Build context is the repo root (see shared/infra/docker-compose.yml).
# Next's standalone output keeps the monorepo layout, so the paths below mirror it.
FROM node:22-alpine AS build
WORKDIR /srv
COPY shared/frontend ./shared/frontend
COPY watch/frontend/package.json watch/frontend/package-lock.json ./watch/frontend/
RUN cd watch/frontend && npm ci
COPY watch/frontend ./watch/frontend
RUN cd watch/frontend && npm run build

FROM node:22-alpine
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /srv
COPY --from=build /srv/watch/frontend/.next/standalone ./
COPY --from=build /srv/watch/frontend/.next/static ./watch/frontend/.next/static
USER node
EXPOSE 3000
CMD ["node", "watch/frontend/server.js"]
