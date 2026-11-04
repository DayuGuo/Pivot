FROM node:22-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json
RUN npm ci --workspace apps/web
COPY apps/web ./apps/web
ENV NEXT_TELEMETRY_DISABLED=1 PIVOT_STANDALONE=true NEXT_PUBLIC_PIVOT_PRIVATE_PREVIEW=true
RUN npm run build --workspace apps/web
FROM node:22-bookworm-slim
WORKDIR /app
COPY --from=build /app/apps/web/.next/standalone ./
COPY --from=build /app/apps/web/.next/static ./apps/web/.next/static
USER node
CMD ["node", "apps/web/server.js"]
