FROM node:22-bookworm-slim
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json
RUN npm ci --workspace apps/web
COPY apps/web ./apps/web
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build --workspace apps/web
EXPOSE 3100
CMD ["npm", "run", "start", "--workspace", "apps/web", "--", "-p", "3100", "-H", "0.0.0.0"]
