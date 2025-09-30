.PHONY: help install dev test build run clean docker-up docker-down

help:
	@echo "Available commands:"
	@echo "  make install    - Install dependencies"
	@echo "  make dev        - Run development server"
	@echo "  make test       - Run tests"
	@echo "  make build      - Build Docker image"
	@echo "  make run        - Run with Docker Compose"
	@echo "  make clean      - Clean up files"

install:
	pip install -r requirements.txt
	python -m spacy download en_core_web_sm

dev:
	uvicorn app:app --reload --port 8080

test:
	pytest tests/ -v --cov=. --cov-report=html

build:
	docker build -t tei-nlp-converter .

run:
	docker-compose up -d

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf logs/*
	rm -rf data/*.db

migrate:
	alembic upgrade head

format:
	black . --line-length 100

lint:
	flake8 . --max-line-length 100
	mypy . --ignore-missing-imports

secure:
	bandit -r . -f json -o security-report.json

all: clean install test build
