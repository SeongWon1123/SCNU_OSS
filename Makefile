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
test:
	$(COMPOSE) run --rm api pytest -q

lint:
	$(COMPOSE) run --rm api ruff check .

build-web:
	docker build -f caddy/Dockerfile -t repodoc-caddy:local .

# Temporary public link via Cloudflare Quick Tunnel (docs/DEPLOY.md 0-a).
tunnel-up:
	$(TUNNEL) up -d --build

tunnel-url:
	@$(TUNNEL) logs tunnel | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1

tunnel-stop:
	$(TUNNEL) stop tunnel
