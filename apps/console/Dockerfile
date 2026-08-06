# Built from the repo root so npm workspaces resolve (apps/console + packages/contracts).
FROM node:22.23.2-bookworm-slim AS deps
WORKDIR /repo
COPY package.json package-lock.json ./
COPY apps/console/package.json apps/console/package.json
COPY packages/contracts/package.json packages/contracts/package.json
RUN npm ci

FROM node:22.23.2-bookworm-slim AS build
WORKDIR /repo
COPY --from=deps /repo/node_modules ./node_modules
COPY package.json package-lock.json tsconfig.base.json ./
COPY apps/console apps/console
COPY packages/contracts packages/contracts
RUN npm run build -w @aegis/console

FROM node:22.23.2-bookworm-slim AS run
WORKDIR /app
ENV NODE_ENV=production
# Docker sets $HOSTNAME to the container id; the standalone server binds to
# it if set, which is not reachable at localhost. Force it to 0.0.0.0.
ENV HOSTNAME=0.0.0.0
ENV PORT=3000
COPY --from=build /repo/apps/console/.next/standalone ./
COPY --from=build /repo/apps/console/.next/static ./apps/console/.next/static
COPY --from=build /repo/apps/console/public ./apps/console/public

EXPOSE 3000
CMD ["node", "apps/console/server.js"]
