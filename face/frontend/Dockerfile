# Build context is the repo root (see shared/infra/docker-compose.yml).
# Next's standalone output keeps the monorepo layout, so the paths below mirror it.
FROM node:22-alpine AS build
WORKDIR /srv
COPY shared/frontend ./shared/frontend
COPY face/frontend/package.json face/frontend/package-lock.json ./face/frontend/
RUN cd face/frontend && npm ci
COPY face/frontend ./face/frontend
RUN cd face/frontend && npm run build

FROM node:22-alpine
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /srv
COPY --from=build /srv/face/frontend/.next/standalone ./
COPY --from=build /srv/face/frontend/.next/static ./face/frontend/.next/static
COPY --from=build /srv/face/frontend/public ./face/frontend/public
USER node
EXPOSE 3000
CMD ["node", "face/frontend/server.js"]
