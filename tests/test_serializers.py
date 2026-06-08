"""Tests for Serializers module."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from linktrace import Document, HtmlLink, Serializers


@pytest.fixture
def sample_documents():
    """Create sample documents for testing."""
    doc1 = Document("https://example.com", "<html><body>Test</body></html>")
    doc1.title = "Example Home"
    doc1.status_code = 200
    doc1.response_headers = {"content-type": "text/html"}
    doc1.internal_links = [
        HtmlLink("https://example.com/about", "About"),
        HtmlLink("https://example.com/contact", "Contact"),
    ]
    doc1.external_links = [HtmlLink("https://external.com", "External")]

    doc2 = Document("https://example.com/about", "<html><body>About</body></html>")
    doc2.title = "About Us"
    doc2.status_code = 200
    doc2.response_headers = {"content-type": "text/html"}
    doc2.internal_links = []
    doc2.external_links = []

    return [doc1, doc2]


def test_serializers_init(sample_documents):
    """Test Serializers initialization."""
    serializer = Serializers(sample_documents)
    assert len(serializer.documents) == 2
    assert serializer.documents[0].url == "https://example.com"


def test_to_json(sample_documents):
    """Test JSON export."""
    with TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "output.json"
        serializer = Serializers(sample_documents)
        serializer.to_json(str(output_path))

        assert output_path.exists()
        with open(output_path) as f:
            data = json.load(f)

        assert len(data) == 2
        assert data[0]["url"] == "https://example.com"
        assert data[0]["title"] == "Example Home"
        assert data[0]["status_code"] == 200
        assert len(data[0]["internal_links"]) == 2
        assert len(data[0]["external_links"]) == 1
        assert "html" not in data[0]


def test_to_json_with_html(sample_documents):
    """Test JSON export with HTML included."""
    with TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "output.json"
        serializer = Serializers(sample_documents)
        serializer.to_json(str(output_path), include_html=True)

        with open(output_path) as f:
            data = json.load(f)

        assert "html" in data[0]
        assert data[0]["html"] == "<html><body>Test</body></html>"


def test_to_pandas(sample_documents):
    """Test pandas DataFrame export."""
    pytest.importorskip("pandas")
    serializer = Serializers(sample_documents)
    df = serializer.to_pandas()

    assert len(df) == 4  # 2 internal + 1 external links from doc1, 1 empty from doc2
    assert "url" in df.columns
    assert "title" in df.columns
    assert "link_url" in df.columns
    assert "link_text" in df.columns
    assert "link_type" in df.columns

    # First doc has 3 links
    doc1_rows = df[df["url"] == "https://example.com"]
    assert len(doc1_rows) == 3
    assert doc1_rows["link_type"].isin(["internal", "external"]).all()


def test_to_pandas_with_html(sample_documents):
    """Test pandas DataFrame export with HTML."""
    pytest.importorskip("pandas")
    serializer = Serializers(sample_documents)
    df = serializer.to_pandas(include_html=True)

    assert "html" in df.columns
    assert df.loc[0, "html"] == "<html><body>Test</body></html>"


def test_to_polars(sample_documents):
    """Test polars DataFrame export."""
    pytest.importorskip("polars")
    serializer = Serializers(sample_documents)
    df = serializer.to_polars()

    assert len(df) == 4
    assert "url" in df.columns
    assert "title" in df.columns
    assert "link_url" in df.columns
    assert "link_type" in df.columns


def test_to_arrow(sample_documents):
    """Test PyArrow Table export."""
    pytest.importorskip("pyarrow")
    serializer = Serializers(sample_documents)
    table = serializer.to_arrow()

    assert table.num_rows == 4
    assert "url" in table.column_names
    assert "link_url" in table.column_names
    assert "link_type" in table.column_names


def test_flattened_links():
    """Test that links are properly flattened."""
    doc = Document("https://example.com", "")
    doc.title = "Test"
    doc.status_code = 200
    doc.response_headers = {}
    doc.internal_links = [HtmlLink("https://example.com/a", "A")]
    doc.external_links = [HtmlLink("https://external.com/b", "B")]

    serializer = Serializers([doc])
    rows = serializer._flatten_documents()

    assert len(rows) == 2
    assert rows[0]["link_type"] == "internal"
    assert rows[0]["link_url"] == "https://example.com/a"
    assert rows[1]["link_type"] == "external"
    assert rows[1]["link_url"] == "https://external.com/b"


def test_document_with_no_links():
    """Test document with no links."""
    doc = Document("https://example.com", "")
    doc.title = "Test"
    doc.status_code = 200
    doc.response_headers = {}
    doc.internal_links = []
    doc.external_links = []

    serializer = Serializers([doc])
    rows = serializer._flatten_documents()

    assert len(rows) == 1
    assert rows[0]["link_url"] is None
    assert rows[0]["link_text"] is None
    assert rows[0]["link_type"] is None


def test_json_export_creates_parent_dir():
    """Test that JSON export creates parent directories."""
    with TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "nested" / "dir" / "output.json"
        doc = Document("https://example.com", "")
        doc.title = "Test"
        doc.status_code = 200
        doc.response_headers = {}
        doc.internal_links = []
        doc.external_links = []

        serializer = Serializers([doc])
        serializer.to_json(str(output_path))

        assert output_path.exists()
        with open(output_path) as f:
            data = json.load(f)
        assert len(data) == 1
