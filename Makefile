.PHONY: up down reset

up: .env
	docker compose up -d --build --wait --wait-timeout 180
	@echo ""
	@echo "Gateway ready: http://localhost:8080"

down:
	docker compose down

reset: .env
	docker compose down -v
	docker compose up -d --build --wait --wait-timeout 180
	@echo ""
	@echo "Gateway ready: http://localhost:8080"

.env:
	cp .env.example .env
