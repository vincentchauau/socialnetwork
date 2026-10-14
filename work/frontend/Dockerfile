# Build context is the repo root (see shared/infra/docker-compose.yml).
# Next's standalone output keeps the monorepo layout, so the paths below mirror it.
FROM node:22-alpine AS build
WORKDIR /srv
COPY shared/frontend ./shared/frontend
COPY work/frontend/package.json work/frontend/package-lock.json ./work/frontend/
RUN cd work/frontend && npm ci
COPY work/frontend ./work/frontend
RUN cd work/frontend && npm run build

FROM node:22-alpine
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /srv
COPY --from=build /srv/work/frontend/.next/standalone ./
COPY --from=build /srv/work/frontend/.next/static ./work/frontend/.next/static
COPY --from=build /srv/work/frontend/public ./work/frontend/public
USER node
EXPOSE 3000
CMD ["node", "work/frontend/server.js"]
