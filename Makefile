.PHONY: install test test-scripts test-pipeline test-all lint smoke smoke-fallback build release-preflight release-rehearsal release verify-consumers clean

install:
	./scripts/bootstrap-dev.sh

test:
	@if [ -x .venv/bin/pytest ]; then \
		.venv/bin/pytest tests/unit tests/integration -m "not live and not slow and not scripts" \
			--cov=confluence_sync --cov-fail-under=72 -q && \
		.venv/bin/pytest tests/cli/ -q; \
	elif [ -x .venv/bin/nox ]; then .venv/bin/nox -s test cli; \
	elif command -v nox >/dev/null 2>&1; then nox -s test cli; \
	else echo "Run: make install"; exit 1; fi

test-scripts:
	.venv/bin/pytest tests/scripts/ -v -m scripts

test-pipeline:
	.venv/bin/pytest tests/integration/test_sync_pipeline.py tests/integration/test_smoke_run_mocked.py -v

test-all: test test-scripts test-pipeline

lint:
	@bash -c 'source scripts/lib.sh && REPO_ROOT="$$(pwd)" && run_nox -s lint'

smoke:
	@bash -c 'source scripts/lib.sh && REPO_ROOT="$$(pwd)" && run_live_smoke'

smoke-fallback:
	@bash -c 'source scripts/lib.sh && REPO_ROOT="$$(pwd)" && SMOKE_FORCE_FALLBACK=1 run_live_smoke'

build:
	@bash -c 'source scripts/lib.sh && REPO_ROOT="$$(pwd)" && run_build'

release-preflight:
	@bash -c 'source scripts/lib.sh && REPO_ROOT="$$(pwd)" && run_release_preflight'

release-rehearsal:
	./scripts/release-rehearsal.sh

verify-consumers:
	./scripts/verify-consumers.sh

release:
	@test -n "$(VERSION)" || (echo "Usage: make release VERSION=x.y.z"; exit 1)
	./scripts/release.sh $(VERSION)

clean:
	rm -rf dist/ .coverage htmlcov/ .nox/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
