"""Unified literature input interface.

Provides a single entry point for loading documents from various formats:
- PDF (primary literature)
- XLSX/CSV (supplementary data tables)
- ZIP (supplementary information packages)

Handles:
- File type detection and validation
- Document ID resolution (from DOI, filename, or user input)
- Metadata extraction (title, authors, journal, date)
- Supplementary material association
- Unified content access for downstream stages
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class DocumentMetadata:
    """Extracted metadata for a document."""
    document_id: str
    file_path: Path
    file_size_bytes: int
    sha256: str
    signature_type: str  # PDF, XLSX, CSV, ZIP
    doi: Optional[str] = None
    title: Optional[str] = None
    authors: Optional[list[str]] = None
    journal: Optional[str] = None
    publication_date: Optional[str] = None
    registration_timestamp: Optional[str] = None
    supplementary_files: list[Path] = field(default_factory=list)


@dataclass
class LiteratureInput:
    """Unified document input for pipeline processing.
    
    Attributes:
        metadata: DocumentMetadata with identity and file info
        content_path: Path to primary content (PDF or extracted text)
        supplementary_paths: List of paths to supplementary materials
        is_extracted: True if content was extracted from ZIP/XLSX
    """
    metadata: DocumentMetadata
    content_path: Path
    supplementary_paths: list[Path] = field(default_factory=list)
    is_extracted: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dict."""
        return {
            "metadata": {
                "document_id": self.metadata.document_id,
                "file_path": str(self.metadata.file_path),
                "file_size_bytes": self.metadata.file_size_bytes,
                "sha256": self.metadata.sha256,
                "signature_type": self.metadata.signature_type,
                "doi": self.metadata.doi,
                "title": self.metadata.title,
                "authors": self.metadata.authors,
                "journal": self.metadata.journal,
                "publication_date": self.metadata.publication_date,
                "registration_timestamp": self.metadata.registration_timestamp,
                "supplementary_files": [str(p) for p in self.metadata.supplementary_files],
            },
            "content_path": str(self.content_path),
            "supplementary_paths": [str(p) for p in self.supplementary_paths],
            "is_extracted": self.is_extracted,
        }


class LiteratureInputResolver:
    """Resolves and validates literature inputs from various file formats."""

    def __init__(self, output_base: Optional[Path] = None):
        """Initialize resolver.
        
        Args:
            output_base: Base directory for extracted content. Defaults to temp dir.
        """
        self.output_base = output_base or Path("data/test_corpus/extracted")
        self.output_base.mkdir(parents=True, exist_ok=True)

    def resolve(
        self,
        file_path: str | Path,
        document_id: Optional[str] = None,
        supplementary_paths: Optional[list[str | Path]] = None,
    ) -> LiteratureInput:
        """Resolve a file path into a LiteratureInput.
        
        Args:
            file_path: Path to primary document (PDF/XLSX/CSV/ZIP)
            document_id: Optional document ID (auto-generated if not provided)
            supplementary_paths: Optional list of supplementary file paths
            
        Returns:
            LiteratureInput with metadata and content paths
            
        Raises:
            FileNotFoundError: If file_path does not exist
            ValueError: If file type is not supported
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        signature_type = self._detect_file_type(file_path)
        if signature_type is None:
            raise ValueError(f"Unsupported file type: {file_path.suffix}")

        sha256 = self._compute_sha256(file_path)
        
        if document_id is None:
            document_id = self._generate_document_id(file_path, sha256)

        metadata = DocumentMetadata(
            document_id=document_id,
            file_path=file_path.resolve(),
            file_size_bytes=file_path.stat().st_size,
            sha256=sha256,
            signature_type=signature_type,
        )

        supplementary = [Path(p) for p in (supplementary_paths or [])]
        metadata.supplementary_files = supplementary

        if signature_type == "PDF":
            return LiteratureInput(
                metadata=metadata,
                content_path=file_path,
                supplementary_paths=supplementary,
            )
        elif signature_type == "ZIP":
            return self._extract_zip(file_path, metadata, supplementary)
        elif signature_type in ("XLSX", "CSV"):
            return self._extract_spreadsheet(file_path, metadata, supplementary)
        else:
            raise ValueError(f"Unhandled file type: {signature_type}")

    def _detect_file_type(self, file_path: Path) -> Optional[str]:
        """Detect file type from extension and magic bytes."""
        suffix = file_path.suffix.lower()
        type_map = {
            ".pdf": "PDF",
            ".xlsx": "XLSX",
            ".xls": "XLSX",
            ".csv": "CSV",
            ".zip": "ZIP",
        }
        return type_map.get(suffix)

    def _compute_sha256(self, file_path: Path) -> str:
        """Compute SHA-256 hash of file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _generate_document_id(self, file_path: Path, sha256: str) -> str:
        """Generate a document ID from filename and hash."""
        stem = file_path.stem
        stem = re.sub(r"[^a-zA-Z0-9]", "", stem)
        if len(stem) > 20:
            stem = stem[:20]
        short_hash = sha256[:8]
        return f"{stem}_{short_hash}"

    def _extract_zip(
        self,
        zip_path: Path,
        metadata: DocumentMetadata,
        supplementary: list[Path],
    ) -> LiteratureInput:
        """Extract content from ZIP file."""
        extract_dir = self.output_base / metadata.document_id
        extract_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        pdf_files = list(extract_dir.rglob("*.pdf"))
        if not pdf_files:
            raise ValueError(f"No PDF found in ZIP: {zip_path}")

        primary_pdf = pdf_files[0]
        metadata.signature_type = "PDF"

        other_files = [f for f in extract_dir.rglob("*") if f.is_file() and f != primary_pdf]
        supplementary.extend(other_files)
        metadata.supplementary_files = supplementary

        return LiteratureInput(
            metadata=metadata,
            content_path=primary_pdf,
            supplementary_paths=supplementary,
            is_extracted=True,
        )

    def _extract_spreadsheet(
        self,
        sheet_path: Path,
        metadata: DocumentMetadata,
        supplementary: list[Path],
    ) -> LiteratureInput:
        """Extract content from XLSX/CSV (treat as supplementary data)."""
        logger.warning(
            "Spreadsheet input detected: %s. "
            "This should typically be provided as supplementary_paths, not primary input.",
            sheet_path,
        )
        return LiteratureInput(
            metadata=metadata,
            content_path=sheet_path,
            supplementary_paths=supplementary,
            is_extracted=False,
        )


def load_literature_input(
    file_path: str | Path,
    document_id: Optional[str] = None,
    supplementary_paths: Optional[list[str | Path]] = None,
    output_base: Optional[Path] = None,
) -> LiteratureInput:
    """Convenience function to load a literature input.
    
    Args:
        file_path: Path to primary document
        document_id: Optional document ID
        supplementary_paths: Optional supplementary files
        output_base: Optional extraction directory
        
    Returns:
        LiteratureInput ready for pipeline processing
    """
    resolver = LiteratureInputResolver(output_base)
    return resolver.resolve(file_path, document_id, supplementary_paths)


def save_literature_input_metadata(
    literature_input: LiteratureInput,
    output_dir: str | Path,
) -> Path:
    """Save LiteratureInput metadata to JSON file.
    
    Args:
        literature_input: The input to save
        output_dir: Directory to write metadata file
        
    Returns:
        Path to saved metadata file
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    metadata_path = output_dir / f"{literature_input.metadata.document_id}_identity.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(literature_input.to_dict(), f, indent=2, ensure_ascii=False)
    
    return metadata_path
