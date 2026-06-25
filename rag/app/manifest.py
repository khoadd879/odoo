"""Loads MANIFEST_ingestion_metadata.json to attach per-file metadata at ingest.

The manifest was created alongside the 17 mock documents in
`mock_data/rag_documents/`. Each entry carries `doc_id`, `visibility`,
`division`, `section`, and `tags`. We index by `filename` so the chunker can
look up metadata for a given markdown file with a single dict lookup.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class Manifest:
    """Read-only view over MANIFEST_ingestion_metadata.json."""

    def __init__(self, data: Dict[str, dict]) -> None:
        self._by_filename: Dict[str, dict] = {entry["filename"]: entry for entry in data.get("documents", [])}

    @classmethod
    def load(cls, manifest_path: str | Path) -> "Manifest":
        path = Path(manifest_path)
        if not path.exists():
            logger.warning("Manifest not found at %s — all chunks will get default visibility=STAFF", path)
            return cls({"documents": []})
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return cls(data)

    def get(self, filename: str) -> Optional[dict]:
        """Return manifest entry for `filename` or None."""
        return self._by_filename.get(filename)
