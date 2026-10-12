# Build context is the repo root (see shared/infra/docker-compose.yml).
# Next's standalone output keeps the monorepo layout, so the paths below mirror it.
FROM node:22-alpine AS build
WORKDIR /srv
COPY shared/frontend ./shared/frontend
COPY jobs/frontend/package.json jobs/frontend/package-lock.json ./jobs/frontend/
RUN cd jobs/frontend && npm ci
COPY jobs/frontend ./jobs/frontend
RUN cd jobs/frontend && npm run build

FROM node:22-alpine
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /srv
COPY --from=build /srv/jobs/frontend/.next/standalone ./
COPY --from=build /srv/jobs/frontend/.next/static ./jobs/frontend/.next/static
USER node
EXPOSE 3000
CMD ["node", "jobs/frontend/server.js"]
