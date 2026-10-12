# Build context is the repo root (see shared/infra/docker-compose.yml).
# Next's standalone output keeps the monorepo layout, so the paths below mirror it.
FROM node:22-alpine AS build
WORKDIR /srv
COPY shared/frontend ./shared/frontend
COPY chat/frontend/package.json chat/frontend/package-lock.json ./chat/frontend/
RUN cd chat/frontend && npm ci
COPY chat/frontend ./chat/frontend
RUN cd chat/frontend && npm run build

FROM node:22-alpine
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /srv
COPY --from=build /srv/chat/frontend/.next/standalone ./
COPY --from=build /srv/chat/frontend/.next/static ./chat/frontend/.next/static
USER node
EXPOSE 3000
CMD ["node", "chat/frontend/server.js"]
