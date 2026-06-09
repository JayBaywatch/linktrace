# Contributing to linktrace

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/JayBaywatch/linktrace.git
cd linktrace

# Create a virtual environment and install in editable mode
uv sync
uv pip install -e ".[serializers]"
```

## Running Tests

```bash
just test          # Run all tests
just test-cov      # Run tests with coverage report
just lint          # Lint and auto-fix
just fmt           # Format code
```

## Code Style

We use **Ruff** for linting and formatting. Pre-commit hooks automatically run on `git commit`.

- **Line length:** 88 characters
- **Python version:** 3.12+
- **Type checking:** mypy

## Making Changes

1. **Create a branch** for your feature or fix
2. **Write tests** for new functionality
3. **Run `just test`** to verify all tests pass
4. **Commit with clear messages** describing what changed and why
5. **Push and open a pull request**

## Commit Message Guidelines

- Start with a verb: "Add", "Fix", "Improve", "Refactor"
- Keep it short (under 72 characters)
- Reference issues if applicable: "Fix #123"

Example:
```
Fix robots.txt parsing for custom user agents

- Respect Disallow rules from robots.txt
- Add is_allowed() check before crawling
- Return 403 status for disallowed URLs
```

## Reporting Issues

Use GitHub Issues to report bugs or suggest features. Include:
- **Description** of the problem
- **Steps to reproduce** (for bugs)
- **Expected vs actual behavior**
- **Python version** and OS
- **Minimal example code** if applicable

## Questions?

Open an issue or start a discussion on GitHub. We're happy to help!
