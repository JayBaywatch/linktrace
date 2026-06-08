# linktrace — common tasks. Run `just` to list.

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
    uv run pytest -v --cov=linktrace --cov-report=term-missing --cov-report=html

# Run the spider against the demo URL
run:
    uv run python -m linktrace.Spider

# Build the wheel + sdist into dist/
build:
    uv build

# Remove the virtualenv and caches
clean:
    rm -rf .venv __pycache__ */__pycache__ .ruff_cache

# Release a new version (creates tag and pushes to GitHub)
release version:
    #!/usr/bin/env bash
    set -e
    echo "📦 Releasing linktrace v{{version}}"

    # Verify version format
    if ! [[ {{version}} =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "❌ Invalid version format. Use: just release 0.1.0"
        exit 1
    fi

    # Update version in pyproject.toml (only the [project] version field)
    sed -i '' "s/^version = \".*\"/version = \"{{version}}\"/" pyproject.toml
    echo "✅ Updated version in pyproject.toml"

    # Commit version bump
    git add pyproject.toml
    git commit -m "Bump version to {{version}}"
    echo "✅ Committed version bump"

    # Create and push tag
    git tag "v{{version}}"
    git push origin main
    git push origin "v{{version}}"
    echo "✅ Pushed to GitHub"

    echo ""
    echo "🎉 Next step: Create release on GitHub"
    echo "   https://github.com/JayBaywatch/webcrawler/releases/new?tag=v{{version}}"
    echo ""
    echo "   This will trigger GitHub Actions to publish to PyPI automatically!"
