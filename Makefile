COMPOSE := docker compose

TUNNEL := $(COMPOSE) -f docker-compose.yml -f docker-compose.tunnel.yml

.PHONY: up down logs test lint build-web tunnel-up tunnel-url tunnel-stop

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

# Standard pytest: real failures propagate (plan revision removed exit-code softening).
# The api service is hardened (non-root, read-only rootfs, 64m /tmp, no /repo mount), so
# the one-off test container gets what the suite needs: the repo at /repo (read-only),
# a writable /scan, and a scratch volume for TMPDIR/HOME (a test writes 10x100MB).
# Root is needed because anonymous volumes are root-owned; capabilities stay dropped.
test:
	$(COMPOSE) run --rm -u 0 -v "$(CURDIR)":/repo:ro -v /scan -v /work \
		-e TMPDIR=/work -e HOME=/work api pytest -q -p no:cacheprovider

# --no-cache: /app is read-only in the hardened api container.
lint:
	$(COMPOSE) run --rm api ruff check --no-cache .

build-web:
	docker build -f caddy/Dockerfile -t repodoc-caddy:local .

# Temporary public link via Cloudflare Quick Tunnel (docs/DEPLOY.md 0-a).
tunnel-up:
	$(TUNNEL) up -d --build

tunnel-url:
	@$(TUNNEL) logs tunnel | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1

tunnel-stop:
	$(TUNNEL) stop tunnel
