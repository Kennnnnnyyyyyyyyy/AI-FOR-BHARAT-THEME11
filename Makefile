.PHONY: help bootstrap dev test lint format clean docker-up docker-down demo-venkateshulu demo-positive build-demo

help:
	@echo "Kartavya Development Commands"
	@echo "=============================="
	@echo "  make bootstrap         Install deps & init environment"
	@echo "  make dev               Run FastAPI dev server"
	@echo "  make test              Run tests"
	@echo "  make lint              Lint code"
	@echo "  make format            Format code"
	@echo "  make docker-up         Start services"
	@echo "  make docker-down       Stop services"
	@echo "  make demo-venkateshulu Run CLI on Venkateshulu (negative case, dry-run)"
	@echo "  make demo-positive     Run CLI on synthetic positive case (dry-run)"
	@echo "  make clean             Clean cache"

bootstrap:
	python3 -m venv .venv
	. .venv/bin/activate && pip install -q --upgrade pip setuptools wheel
	. .venv/bin/activate && pip install -q -r requirements.txt
	. .venv/bin/activate && pip install -q -r requirements-dev.txt
	cp .env.template .env
	docker-compose up -d
	@echo "✅ Bootstrap complete! Edit .env and run: make dev"

dev:
	. .venv/bin/activate && uvicorn kartavya.main:app --reload --host 0.0.0.0 --port 8000

test:
	. .venv/bin/activate && pytest -v

lint:
	. .venv/bin/activate && ruff check . && mypy kartavya/

format:
	. .venv/bin/activate && black kartavya/ && ruff check --fix .

docker-up:
	docker-compose up -d
	docker-compose ps

docker-down:
	docker-compose down

docker-ps:
	docker-compose ps

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov/
	@echo "✅ Cleaned"

demo-venkateshulu:
	.venv/bin/python -m kartavya.cli.run \
	    tests/fixtures/venkateshulu_real_pdf_wp13296_2022/original.pdf \
	    --dry-run

demo-positive:
	.venv/bin/python -m kartavya.cli.run \
	    tests/fixtures/synthetic_disposed_with_directions/judgment.pdf \
	    --dry-run --demo-positive

build-demo:
	.venv/bin/python scripts/build_demo.py

.SILENT: help
