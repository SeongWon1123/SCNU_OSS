COMPOSE := docker compose

.PHONY: up down logs test lint build-web

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
