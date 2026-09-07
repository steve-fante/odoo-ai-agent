.PHONY: install seed demo test lint eval clean

install:
	pip install -e ".[dev,anthropic]"

seed:
	python scripts/seed_demo.py data/demo_odoo.sqlite

demo: seed
	python scripts/demo_offline.py

test:
	pytest -q

lint:
	ruff check .

eval:
	python evals/run_eval.py --json metrics.json

clean:
	rm -rf .pytest_cache .ruff_cache **/__pycache__ data/demo_odoo.sqlite metrics.json
