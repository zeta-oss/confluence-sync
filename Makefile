.PHONY: install test lint smoke build release clean

install:
	./scripts/bootstrap-dev.sh

test:
	nox -s test cli

lint:
	nox -s lint

smoke:
	nox -s live_smoke

build:
	nox -s build

release:
	@test -n "$(VERSION)" || (echo "Usage: make release VERSION=x.y.z"; exit 1)
	./scripts/release.sh $(VERSION)

clean:
	rm -rf dist/ .coverage htmlcov/ .nox/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
