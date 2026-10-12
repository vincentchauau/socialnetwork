# Build context is the repo root (see shared/infra/docker-compose.yml).
# Next's standalone output keeps the monorepo layout, so the paths below mirror it.
FROM node:22-alpine AS build
WORKDIR /srv
COPY shared/frontend ./shared/frontend
COPY werewolf/frontend/package.json werewolf/frontend/package-lock.json ./werewolf/frontend/
RUN cd werewolf/frontend && npm ci
COPY werewolf/frontend ./werewolf/frontend
RUN cd werewolf/frontend && npm run build

FROM node:22-alpine
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /srv
COPY --from=build /srv/werewolf/frontend/.next/standalone ./
COPY --from=build /srv/werewolf/frontend/.next/static ./werewolf/frontend/.next/static
USER node
EXPOSE 3000
CMD ["node", "werewolf/frontend/server.js"]
