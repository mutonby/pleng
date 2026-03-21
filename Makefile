.PHONY: up down logs shell agent-shell ps

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f

logs-api:
	docker compose logs -f platform-api

logs-agent:
	docker compose logs -f agent

shell:
	docker compose exec platform-api sh

agent-shell:
	docker compose exec agent bash

chat:
	docker compose exec -it agent pleng chat

ps:
	docker compose ps
