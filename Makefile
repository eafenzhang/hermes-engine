.PHONY: dev test clean

# ── Development ─────────────────────────────────────────────────────
dev:
	python run.py --debug

run:
	python run.py

# ── Tests ────────────────────────────────────────────────────────────
test:
	python -m pytest tests/ -v

test-coverage:
	python -m pytest tests/ --cov=. --cov-report=term-missing

# ── Cleanup ──────────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf *.egg-info
