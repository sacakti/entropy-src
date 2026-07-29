.PHONY: format lint typecheck test check fix clean

format:
	black .

lint:
	ruff check .

typecheck:
	mypy .

test:
	pytest

check: lint
	black --check .
	$(MAKE) typecheck
	$(MAKE) test

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
