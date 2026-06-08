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


@pytest.fixture
def protocol_edge_cases_html():
    """HTML with various dangerous protocols and edge cases."""
    return """
    <html>
        <head><title>Protocol Tests</title></head>
        <body>
            <a href="https://safe.example.com">Safe HTTPS</a>
            <a href="http://safe.example.com">Safe HTTP</a>
            <a href="ftp://safe.example.com">Safe FTP</a>
            <a href="javascript:void(0)">JavaScript lowercase</a>
            <a href="JavaScript:alert('xss')">JavaScript uppercase</a>
            <a href="jAvAsCrIpT:void(0)">JavaScript mixed case</a>
            <a href="data:text/html,<script>alert('xss')</script>">Data URL</a>
            <a href="vbscript:msgbox('xss')">VBScript</a>
            <a href="file:///etc/passwd">File protocol</a>
            <a href="mailto:user@example.com">Mailto</a>
            <a href="tel:+1234567890">Tel</a>
            <a href="#anchor">Anchor only</a>
            <a href="">Empty href</a>
            <a href=" ">Space only</a>
        </body>
    </html>
    """
