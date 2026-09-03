# 2-stage: node:20 builds the Next.js static export (web/out) -> caddy:2 serves /srv/web.
# web/ is owned by a parallel task (todo 5); until its skeleton lands this stage emits a
# placeholder page. First real web build is proven in todo 6.
FROM node:20 AS web-builder
WORKDIR /build/web
COPY web/ ./
RUN if [ -f package.json ]; then \
      npm ci && npm run build; \
    else \
      mkdir -p out && echo "placeholder: web/ not built yet (todo 6)" > out/index.html; \
    fi

FROM caddy:2
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=web-builder /build/web/out /srv/web
