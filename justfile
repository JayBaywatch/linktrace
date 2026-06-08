# webcrawler — common tasks. Run `just` to list.

# Show available recipes
default:
    @just --list

# Create/sync the virtualenv from pyproject.toml + uv.lock
sync:
    uv sync

# Lint (and auto-fix what's safe)
lint:
    uv run ruff check --fix .

# Format the code
fmt:
    uv run ruff format .

# Lint + format check without writing (CI-friendly)
check:
    uv run ruff check .
    uv run ruff format --check .

# Run tests
test:
    uv run pytest -v

# Run tests with coverage
test-cov:
    uv run pytest -v --cov=WebCrawler --cov-report=term-missing --cov-report=html

# Run the spider against the demo URL
run:
    uv run python -m WebCrawler.Spider

# Build the wheel + sdist into dist/
build:
    uv build

# Remove the virtualenv and caches
clean:
    rm -rf .venv __pycache__ */__pycache__ .ruff_cache
