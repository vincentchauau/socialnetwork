# Build context is the repo root (see shared/infra/docker-compose.yml).
# Next's standalone output keeps the monorepo layout, so the paths below mirror it.
FROM node:22-alpine AS build
WORKDIR /srv
COPY shared/frontend ./shared/frontend
COPY learning/frontend/package.json learning/frontend/package-lock.json ./learning/frontend/
RUN cd learning/frontend && npm ci
COPY learning/frontend ./learning/frontend
RUN cd learning/frontend && npm run build

FROM node:22-alpine
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /srv
COPY --from=build /srv/learning/frontend/.next/standalone ./
COPY --from=build /srv/learning/frontend/.next/static ./learning/frontend/.next/static
USER node
EXPOSE 3000
CMD ["node", "learning/frontend/server.js"]
