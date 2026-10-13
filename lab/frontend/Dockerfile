# Build context is the repo root (see shared/infra/docker-compose.yml).
# Next's standalone output keeps the monorepo layout, so the paths below mirror it.
FROM node:22-alpine AS build
WORKDIR /srv
COPY shared/frontend ./shared/frontend
COPY lab/frontend/package.json lab/frontend/package-lock.json ./lab/frontend/
RUN cd lab/frontend && npm ci
COPY lab/frontend ./lab/frontend
RUN cd lab/frontend && npm run build

FROM node:22-alpine
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /srv
COPY --from=build /srv/lab/frontend/.next/standalone ./
COPY --from=build /srv/lab/frontend/.next/static ./lab/frontend/.next/static
COPY --from=build /srv/lab/frontend/public ./lab/frontend/public
USER node
EXPOSE 3000
CMD ["node", "lab/frontend/server.js"]
