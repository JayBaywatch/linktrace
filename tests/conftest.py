"""Pytest fixtures and configuration."""

import pytest


@pytest.fixture
def sample_html():
    """Sample HTML for testing parsing."""
    return """
    <html>
        <head><title>Test Page</title></head>
        <body>
            <a href="https://internal.example.com/page1">Internal Link</a>
            <a href="https://external.org">External Link</a>
            <a href="/relative">Relative Link</a>
            <a href="javascript:void(0)">JavaScript Link</a>
        </body>
    </html>
    """


@pytest.fixture
def malformed_html():
    """Malformed HTML for testing error handling."""
    return "<html><body>Unclosed tag</body>"
