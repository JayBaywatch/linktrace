"""Export crawled documents to various formats: JSON, Pandas, Polars, PyArrow."""

import json
from pathlib import Path

from WebCrawler.Crawler import Document


class Serializers:
    """Export documents with flattened links and rich metadata."""

    def __init__(self, documents: list[Document]):
        """Initialize with a list of crawled documents.

        Args:
            documents: List of Document objects from Spider.run_async()
        """
        self.documents = documents

    def to_json(self, output_path: str, include_html: bool = False) -> None:
        """Export documents to JSON file with nested link structure.

        Args:
            output_path: Path to write JSON file
            include_html: Include raw HTML source in output (default False)
        """
        data = []
        for doc in self.documents:
            doc_data = {
                "url": doc.url,
                "title": doc.title,
                "status_code": doc.status_code,
                "domain": doc.domain,
                "response_headers": doc.response_headers,
                "internal_links": [
                    {"url": link.url, "text": link.text} for link in doc.internal_links
                ],
                "external_links": [
                    {"url": link.url, "text": link.text} for link in doc.external_links
                ],
            }
            if include_html and doc.source:
                doc_data["html"] = doc.source
            data.append(doc_data)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

    def to_pandas(self, include_html: bool = False):
        """Export documents to pandas DataFrame with flattened links.

        One row per link; document metadata is repeated for each link.

        Args:
            include_html: Include raw HTML source in output (default False)

        Returns:
            pandas DataFrame with columns: url, title, status_code, domain,
            link_url, link_text, link_type (internal/external), and optional html
        """
        try:
            import pandas as pd
        except ImportError as e:
            raise ImportError(
                "pandas is required for to_pandas(). Install with: pip install pandas"
            ) from e

        rows = self._flatten_documents(include_html)
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    def to_polars(self, include_html: bool = False):
        """Export documents to polars DataFrame with flattened links.

        One row per link; document metadata is repeated for each link.

        Args:
            include_html: Include raw HTML source in output (default False)

        Returns:
            polars DataFrame with columns: url, title, status_code, domain,
            link_url, link_text, link_type (internal/external), and optional html
        """
        try:
            import polars as pl
        except ImportError as e:
            raise ImportError(
                "polars is required for to_polars(). Install with: pip install polars"
            ) from e

        rows = self._flatten_documents(include_html)
        return pl.DataFrame(rows) if rows else pl.DataFrame()

    def to_arrow(self, include_html: bool = False):
        """Export documents to PyArrow Table with flattened links.

        One row per link; document metadata is repeated for each link.

        Args:
            include_html: Include raw HTML source in output (default False)

        Returns:
            pyarrow Table with columns: url, title, status_code, domain,
            link_url, link_text, link_type (internal/external), and optional html
        """
        try:
            import pyarrow as pa
        except ImportError as e:
            raise ImportError(
                "pyarrow is required for to_arrow(). Install with: pip install pyarrow"
            ) from e

        rows = self._flatten_documents(include_html)
        if not rows:
            return pa.table({})

        columns = {}
        for row in rows:
            for key, value in row.items():
                if key not in columns:
                    columns[key] = []
                columns[key].append(value)

        return pa.table(columns)

    def _flatten_documents(self, include_html: bool = False) -> list[dict]:
        """Flatten documents with one row per link.

        Args:
            include_html: Include raw HTML source in output

        Returns:
            List of flattened document rows
        """
        rows = []
        for doc in self.documents:
            base_row = {
                "url": doc.url,
                "title": doc.title,
                "status_code": doc.status_code,
                "domain": doc.domain,
            }

            if include_html:
                base_row["html"] = doc.source

            all_links = doc.internal_links + doc.external_links

            if not all_links:
                row = base_row.copy()
                row["link_url"] = None
                row["link_text"] = None
                row["link_type"] = None
                rows.append(row)
            else:
                for link in all_links:
                    row = base_row.copy()
                    row["link_url"] = link.url
                    row["link_text"] = link.text
                    row["link_type"] = (
                        "internal" if link in doc.internal_links else "external"
                    )
                    rows.append(row)

        return rows
