DOCKER_COMPOSE ?= docker compose

.PHONY: build up down restart logs

build:
	$(DOCKER_COMPOSE) build --pull

up:
	$(DOCKER_COMPOSE) up -d

down:
	$(DOCKER_COMPOSE) down

restart: down up

logs:
	$(DOCKER_COMPOSE) logs -f api
