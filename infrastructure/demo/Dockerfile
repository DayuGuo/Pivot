# Build on the developer machine, never on the small demonstration VPS.
FROM --platform=$BUILDPLATFORM node:22-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json
RUN npm ci --workspace apps/web
COPY infrastructure/demo/site ./demo
COPY apps/web/components/demo ./demo/components/demo
COPY apps/web/components/editorial/icons.tsx ./demo/components/editorial/icons.tsx
ENV NEXT_TELEMETRY_DISABLED=1
RUN ./node_modules/.bin/next build demo --webpack

FROM nginx:1.28-alpine AS runtime
COPY infrastructure/demo/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/demo/out /usr/share/nginx/html
EXPOSE 80
