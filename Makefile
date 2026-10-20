.PHONY: up up-mock up-gpu down logs test-backend test-frontend doctor clean smoke

# Default: mock mode
up: up-mock

# Mock mode: lightweight simulated pipeline
up-mock:
	@echo ">>> Stopping any running GPU worker..."
	-COMPOSE_PROFILES=gpu docker compose stop worker-gpu 2>/dev/null || true
	@echo ">>> Starting ScanForge in MOCK mode..."
	SCANFORGE_ENGINE=mock COMPOSE_PROFILES=mock docker compose up -d --build
	@echo ">>> Mock mode active. UI at http://localhost:3000"

# GPU mode: real COLMAP/OpenMVS/nerfstudio pipeline
up-gpu:
	@echo ">>> Stopping any running mock worker..."
	-COMPOSE_PROFILES=mock docker compose stop worker-mock 2>/dev/null || true
	@echo ">>> Starting ScanForge in GPU (real) mode..."
	SCANFORGE_ENGINE=real COMPOSE_PROFILES=gpu docker compose up -d --build
	@echo ">>> GPU mode active. UI at http://localhost:3000"
	@echo ">>> Verifying /api/capabilities reports engine=real..."
	@sleep 5
	@curl -sf http://localhost:3000/api/capabilities | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  engine={d[\"engine\"]}, gpu_available={d[\"gpu_available\"]}'); assert d['engine']=='real', 'ERROR: engine is not real'" || echo "  (verification failed or API not ready yet; check manually)"

down:
	docker compose --profile gpu --profile mock --profile test down

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
