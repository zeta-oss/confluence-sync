.PHONY: install test lint smoke build release clean

install:
	./scripts/bootstrap-dev.sh

test:
	@if [ -x .venv/bin/pytest ]; then \
		.venv/bin/pytest tests/unit tests/integration -m "not live and not slow" \
			--cov=confluence_sync --cov-fail-under=72 -q && \
		.venv/bin/pytest tests/cli/ -q; \
	elif [ -x .venv/bin/nox ]; then .venv/bin/nox -s test cli; \
	elif command -v nox >/dev/null 2>&1; then nox -s test cli; \
	else echo "Run: make install"; exit 1; fi

lint:
	@bash -c 'source scripts/lib.sh && REPO_ROOT="$$(pwd)" && run_nox -s lint'

smoke:
	@bash -c 'source scripts/lib.sh && REPO_ROOT="$$(pwd)" && run_live_smoke'

build:
	@bash -c 'source scripts/lib.sh && REPO_ROOT="$$(pwd)" && run_build'

release:
	@test -n "$(VERSION)" || (echo "Usage: make release VERSION=x.y.z"; exit 1)
	./scripts/release.sh $(VERSION)

clean:
	rm -rf dist/ .coverage htmlcov/ .nox/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
