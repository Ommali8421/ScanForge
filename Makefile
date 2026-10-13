.PHONY: up up-gpu down logs test-backend test-frontend doctor clean smoke

up:
	docker compose up -d --build

up-gpu:
	docker compose --profile gpu up -d --build

down:
	docker compose --profile gpu --profile test down

logs:
	docker compose logs -f

test-backend:
	docker compose exec api pytest tests/ -v

test-frontend:
	docker compose --profile test up --build --abort-on-container-exit test-frontend

doctor:
	python scripts/doctor.py

smoke:
	python3 scripts/e2e_smoke.py

clean:
	docker compose down -v
