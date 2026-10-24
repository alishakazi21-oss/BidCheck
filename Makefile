.PHONY: help install seed test evaluate run run-api docker-up docker-down

help:
	@echo "Available commands:"
	@echo "  make install    - Install Python dependencies"
	@echo "  make seed       - Generate synthetic dummy data and load Kaggle benchmarks"
	@echo "  make test       - Run pytest test suite"
	@echo "  make evaluate   - Run automated evaluation script and generate report"
	@echo "  make run        - Start Streamlit officer dashboard (offline demo mode)"
	@echo "  make run-api    - Start FastAPI backend service"
	@echo "  make docker-up  - Build and launch via Docker Compose"

install:
	pip install -r requirements.txt

seed:
	python scripts/make_dummy_data.py
	python scripts/load_kaggle_data.py

test:
	python -m pytest tests/ -v

evaluate:
	python scripts/evaluate.py

run:
	streamlit run ui/app.py

run-api:
	uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload

docker-up:
	docker compose up --build

docker-down:
	docker compose down
