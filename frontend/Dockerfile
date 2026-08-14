FROM node:24-bookworm-slim AS build
WORKDIR /app
ARG OOPSNOTE_BACKEND_URL=http://backend:8000
ENV OOPSNOTE_BACKEND_URL=$OOPSNOTE_BACKEND_URL
ARG NEXT_PUBLIC_AUTH_MODE=better-auth
ENV NEXT_PUBLIC_AUTH_MODE=$NEXT_PUBLIC_AUTH_MODE
RUN test "$NEXT_PUBLIC_AUTH_MODE" = "better-auth" || test "$NEXT_PUBLIC_AUTH_MODE" = "local"
COPY package.json package-lock.json* ./
RUN npm ci --ignore-scripts
RUN node -e "const Database = require('better-sqlite3'); const db = new Database(':memory:'); db.prepare('select 1').get(); db.close()"
COPY . .
RUN npm run renderers:sync \
    && BETTER_AUTH_SECRET=build-only-better-auth-secret-32-bytes \
       OOPSNOTE_AUTH_DB_PATH=/tmp/oopsnote-build-auth.sqlite \
       npm run build

FROM node:24-bookworm-slim
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /app
COPY --from=build /app/public ./public
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
