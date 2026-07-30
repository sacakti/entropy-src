.PHONY: format lint typecheck test check coverage clean fix

format:
	black .

lint:
	ruff check .

typecheck:
	mypy .

test:
	pytest

coverage:
	pytest --cov=core --cov=lib --cov-report=term-missing

check:
	ruff check .
	black --check .
	mypy .
	pytest

fix:
	ruff check . --fix
	black .

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .mypy_cache
	rm -rf .pytest_cache
	rm -rf .ruff_cache
	rm -rf .coverage
	rm -rf htmlcov
