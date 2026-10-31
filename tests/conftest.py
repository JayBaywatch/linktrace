"""Pytest fixtures and configuration."""

from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
import pytest_asyncio
from aiohttp import web

SiteFactory = Callable[[dict[str, str | tuple[int, str]]], Awaitable[str]]


@pytest_asyncio.fixture
async def local_site() -> AsyncIterator[SiteFactory]:
    """Factory that serves a dict of ``path -> html`` on a local port.

    A value may also be ``(status, html)`` to serve a non-200 response.
    Returns the base URL (``http://127.0.0.1:<port>``). Used to exercise the
    real HTTP and browser fetchers without touching the network.
    """
    runners: list[web.AppRunner] = []

    async def serve(pages: dict[str, str | tuple[int, str]]) -> str:
        app = web.Application()

        def make_handler(value: str | tuple[int, str]):
            status, body = value if isinstance(value, tuple) else (200, value)

            async def handler(request: web.Request) -> web.Response:
                return web.Response(text=body, status=status, content_type="text/html")

            return handler

        for path, value in pages.items():
            app.router.add_get(path, make_handler(value))

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        runners.append(runner)
        port = runner.addresses[0][1]
        return f"http://127.0.0.1:{port}"

    yield serve

    for runner in runners:
        await runner.cleanup()


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
