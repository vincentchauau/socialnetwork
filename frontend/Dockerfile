# Build context is the repo root (see shared/infra/docker-compose.yml).
# Next's standalone output keeps the monorepo layout, so the paths below mirror it.
FROM node:22-alpine AS build
WORKDIR /srv
# The packages first (they change rarely), then the code (every edit): a change of code does not install the packages again.
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN --mount=type=cache,target=/root/.npm cd frontend && npm ci
COPY shared/frontend ./shared/frontend
COPY frontend ./frontend
RUN cd frontend && npm run build

FROM node:22-alpine
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /srv
COPY --from=build /srv/frontend/.next/standalone ./
COPY --from=build /srv/frontend/.next/static ./frontend/.next/static
COPY --from=build /srv/frontend/public ./frontend/public
USER node
EXPOSE 3000
CMD ["node", "frontend/server.js"]
