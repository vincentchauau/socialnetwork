# Build context is the repo root (see shared/infra/docker-compose.yml).
# Next's standalone output keeps the monorepo layout, so the paths below mirror it.
FROM node:22-alpine AS build
WORKDIR /srv
COPY shared/frontend ./shared/frontend
COPY photos/frontend/package.json photos/frontend/package-lock.json ./photos/frontend/
RUN cd photos/frontend && npm ci
COPY photos/frontend ./photos/frontend
RUN cd photos/frontend && npm run build

FROM node:22-alpine
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /srv
COPY --from=build /srv/photos/frontend/.next/standalone ./
COPY --from=build /srv/photos/frontend/.next/static ./photos/frontend/.next/static
USER node
EXPOSE 3000
CMD ["node", "photos/frontend/server.js"]
