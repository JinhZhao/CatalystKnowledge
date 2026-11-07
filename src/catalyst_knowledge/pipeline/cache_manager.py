"""Cache Manager for pipeline extraction artifacts.

Provides:
- Historical artifact discovery across Phase directories
- Cache validation by input SHA256, pipeline/schema/prompt versions
- Namespace isolation by document_id
- Unified cache labels: FRESH, CACHE_REUSE, STALE, MISSING
- Source tracking: cache path, hash, version metadata

Cache Invalidation Dimensions:
1. Input file SHA256 (content changed)
2. Pipeline version (processing logic changed)
3. Schema version (output structure changed)
4. Prompt version (extraction criteria changed)

Any dimension mismatch → cache is STALE, not reused.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from .run_manifest import compute_file_sha256

logger = logging.getLogger(__name__)


class CacheStatus(str, Enum):
    """Cache validation status."""
    FRESH = "FRESH"              # Valid cache, can reuse
    CACHE_REUSE = "CACHE_REUSE"  # Valid cache, reusing (same as FRESH but emphasizes reuse)
    STALE = "STALE"              # Cache exists but versions don't match
    MISSING = "MISSING"          # No cache found
    INVALID = "INVALID"          # Cache file corrupted or malformed


class CacheLabel(str, Enum):
    """Unified execution label for pipeline stages."""
    FRESH = "FRESH"
    CACHE_REUSE = "CACHE_REUSE"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


@dataclass
class CacheKey:
    """Cache lookup key combining all validation dimensions."""
    document_id: str
    stage_name: str
    namespace: str
    input_hash: str  # SHA256 of input file(s)
    pipeline_version: str
    schema_version: str
    prompt_version: str
    
    def to_dict(self) -> dict[str, str]:
        return {
            "document_id": self.document_id,
            "stage_name": self.stage_name,
            "namespace": self.namespace,
            "input_hash": self.input_hash,
            "pipeline_version": self.pipeline_version,
            "schema_version": self.schema_version,
            "prompt_version": self.prompt_version,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, str]) -> CacheKey:
        return cls(
            document_id=data["document_id"],
            stage_name=data["stage_name"],
            namespace=data["namespace"],
            input_hash=data["input_hash"],
            pipeline_version=data["pipeline_version"],
            schema_version=data["schema_version"],
            prompt_version=data["prompt_version"],
        )
    
    def matches(self, other: CacheKey) -> bool:
        """Check if two cache keys are equivalent (all dimensions match)."""
        return (
            self.document_id == other.document_id
            and self.stage_name == other.stage_name
            and self.namespace == other.namespace
            and self.input_hash == other.input_hash
            and self.pipeline_version == other.pipeline_version
            and self.schema_version == other.schema_version
            and self.prompt_version == other.prompt_version
        )


@dataclass
class CacheEntry:
    """A single cache artifact with metadata.
    
    Attributes:
        key: CacheKey with all validation dimensions
        source_path: Path to the cache file
        created_at: ISO timestamp of creation
        file_hash: SHA256 of the cache file itself
        status: Cache validation status
        artifact_type: Type of artifact (extraction, normalization, report, etc.)
        execution_type: How this was produced (fresh, cache_reuse, recovered, etc.)
        trusted: Whether this entry has verified version metadata.
                 False for historical artifacts with UNKNOWN versions.
        metadata: Additional metadata dict
    """
    key: CacheKey
    source_path: str
    created_at: str
    file_hash: str
    status: CacheStatus = CacheStatus.FRESH
    artifact_type: str = "unknown"
    execution_type: str = "unknown"
    trusted: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key.to_dict(),
            "source_path": self.source_path,
            "created_at": self.created_at,
            "file_hash": self.file_hash,
            "status": self.status.value,
            "artifact_type": self.artifact_type,
            "execution_type": self.execution_type,
            "trusted": self.trusted,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CacheEntry:
        return cls(
            key=CacheKey.from_dict(data["key"]),
            source_path=data["source_path"],
            created_at=data["created_at"],
            file_hash=data["file_hash"],
            status=CacheStatus(data.get("status", "FRESH")),
            artifact_type=data.get("artifact_type", "unknown"),
            execution_type=data.get("execution_type", "unknown"),
            trusted=data.get("trusted", True),
            metadata=data.get("metadata", {}),
        )
    
    def is_valid(self) -> bool:
        """Check if cache entry is valid for reuse.
        
        Only trusted entries with matching versions are valid.
        """
        return (
            self.trusted
            and self.status in (CacheStatus.FRESH, CacheStatus.CACHE_REUSE)
        )


@dataclass
class CacheIndex:
    """Index of all cache entries for a namespace."""
    namespace: str
    entries: dict[str, CacheEntry] = field(default_factory=dict)  # key: source_path
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def add_entry(self, entry: CacheEntry) -> None:
        """Add or update a cache entry."""
        self.entries[entry.source_path] = entry
        self.updated_at = datetime.now().isoformat()
    
    def remove_entry(self, source_path: str) -> Optional[CacheEntry]:
        """Remove a cache entry by source path."""
        entry = self.entries.pop(source_path, None)
        if entry:
            self.updated_at = datetime.now().isoformat()
        return entry
    
    def find_by_key(self, key: CacheKey) -> Optional[CacheEntry]:
        """Find a cache entry matching the given key."""
        for entry in self.entries.values():
            if entry.key.matches(key):
                return entry
        return None
    
    def find_by_partial_key(
        self,
        document_id: str,
        stage_name: str,
        namespace: str,
    ) -> Optional[CacheEntry]:
        """Find a cache entry by document_id/stage_name/namespace only.
        
        Used to detect stale cache when versions/hashes change.
        """
        for entry in self.entries.values():
            if (
                entry.key.document_id == document_id
                and entry.key.stage_name == stage_name
                and entry.key.namespace == namespace
            ):
                return entry
        return None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "entries": {path: entry.to_dict() for path, entry in self.entries.items()},
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CacheIndex:
        index = cls(
            namespace=data["namespace"],
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )
        for path, entry_data in data.get("entries", {}).items():
            index.entries[path] = CacheEntry.from_dict(entry_data)
        return index


class ArtifactResolution(str, Enum):
    """Result of authoritative artifact resolution."""
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass
class ArtifactResult:
    """Result of artifact resolution with status and optional entries."""
    resolution: ArtifactResolution
    entry: Optional[CacheEntry] = None
    candidates: list[CacheEntry] = field(default_factory=list)
    
    @property
    def found(self) -> bool:
        return self.resolution == ArtifactResolution.FOUND


class CacheManager:
    """Manages extraction cache across pipeline runs.
    
    Responsibilities:
    - Discover historical artifacts from Phase directories
    - Validate cache by input hash and version dimensions
    - Provide cache reuse or mark as stale
    - Track cache source and metadata
    - Isolate by document_id/namespace
    """
    
    HISTORICAL_PATTERNS = [
        "phase3/*/05_extraction/*/*_extracted.json",
        "phase3_4_2/*/*_v2_extracted.json",
        "phase3_4_3/*/PHASE343_SIX_DIMENSION_RESULT.json",
        "phase3_4_3/*/characterization_recovery/characterization_v2_extracted.json",
        "phase3_4_5/*/PHASE345_SIX_DIMENSION_FINAL.json",
        "phase3_5/*/*_SIX_DIMENSION_PHASE35.json",
    ]
    
    EXCLUDED_FILENAMES = {
        "identity.json", "extraction_summary.json", "store_index.json",
        "call_metadata.json", "qc_metrics.json", "validation_result.json",
        "recovery_manifest.json", "traceability_audit.json",
        "recovered_data.json", "call_recovery_manifest.json",
    }
    
    EXCLUDED_SUFFIXES = {
        "_identity.json", "_summary.json", "_index.json",
        "_metadata.json", "_metrics.json", "_audit.json",
        "_manifest.json", "_raw.json",
    }
    
    EXTRACTION_CONTENT_MARKERS = {
        "dimensions", "extraction_results", "six_dimension",
        "catalyst_design", "characterization", "mechanism",
        "performance", "reliability", "structure_activity",
    }
    
    def __init__(
        self,
        runs_dir: Path | str,
        pipeline_version: str = "1.0.0",
        schema_version: str = "1.0.0",
        prompt_version: str = "1.0.0",
    ):
        self.runs_dir = Path(runs_dir)
        self.pipeline_version = pipeline_version
        self.schema_version = schema_version
        self.prompt_version = prompt_version
        
        # Namespace-indexed cache storage
        self._indices: dict[str, CacheIndex] = {}
        
        # Load existing cache index if present
        self._cache_index_file = self.runs_dir / "cache_index.json"
        if self._cache_index_file.exists():
            self._load_index()
    
    def _load_index(self) -> None:
        """Load cache index from disk."""
        try:
            with open(self._cache_index_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for namespace, index_data in data.get("indices", {}).items():
                self._indices[namespace] = CacheIndex.from_dict(index_data)
            logger.info("Loaded cache index with %d namespaces", len(self._indices))
        except Exception as e:
            logger.warning("Failed to load cache index: %s", e)
    
    def _save_index(self) -> None:
        """Persist cache index to disk."""
        data = {
            "pipeline_version": self.pipeline_version,
            "schema_version": self.schema_version,
            "prompt_version": self.prompt_version,
            "updated_at": datetime.now().isoformat(),
            "indices": {ns: idx.to_dict() for ns, idx in self._indices.items()},
        }
        self._cache_index_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._cache_index_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.debug("Saved cache index to %s", self._cache_index_file)
    
    def get_or_create_index(self, namespace: str) -> CacheIndex:
        """Get or create a cache index for the given namespace."""
        if namespace not in self._indices:
            self._indices[namespace] = CacheIndex(namespace=namespace)
        return self._indices[namespace]
    
    def discover_historical_artifacts(
        self,
        document_id: str,
        namespace: Optional[str] = None,
        artifact_type: Optional[str] = None,
    ) -> list[CacheEntry]:
        """Discover historical extraction artifacts for a document.
        
        Scans Phase directories for existing extraction results.
        Applies strict filtering:
        - document_id must appear as a path component (directory name)
        - Excludes temp/test/intermediate files
        - Validates file content structure
        
        Args:
            document_id: Document identifier to match
            namespace: Optional namespace (defaults to document_id)
            artifact_type: Optional filter by artifact type
            
        Returns:
            List of CacheEntry objects (not yet validated for version match)
        """
        ns = namespace or document_id
        discovered: list[CacheEntry] = []
        
        for pattern in self.HISTORICAL_PATTERNS:
            for path in self.runs_dir.glob(pattern):
                if not path.is_file():
                    continue
                
                if not self._passes_document_filter(path, document_id):
                    continue
                
                if self._is_excluded_file(path):
                    continue
                
                if not self._validate_extraction_content(path):
                    continue
                
                try:
                    entry = self._create_entry_from_file(path, document_id, ns)
                    if entry is None:
                        continue
                    
                    if artifact_type and entry.artifact_type != artifact_type:
                        continue
                    
                    discovered.append(entry)
                    logger.debug("Discovered historical artifact: %s", path)
                except Exception as e:
                    logger.warning("Failed to process artifact %s: %s", path, e)
        
        logger.info(
            "Discovered %d historical artifacts for %s (type=%s)",
            len(discovered), document_id, artifact_type or "any",
        )
        return discovered
    
    def _passes_document_filter(self, path: Path, document_id: str) -> bool:
        """Check if a file belongs to the given document_id.
        
        Uses two-layer identity verification:
        1. Exact directory name match (case-insensitive): f02 matches F02
        2. File content cross-validation: JSON document_id field matches
        
        A file passes if EITHER condition is met:
        - Its parent directory name exactly equals document_id
        - Its JSON content contains a matching document_id field
        
        This prevents loose prefix matching (e.g., f02_validation_check != F02).
        """
        doc_lower = document_id.lower()
        
        dir_match = False
        for part in path.parts:
            part_lower = part.lower()
            if part_lower == doc_lower:
                dir_match = True
                break
        
        if dir_match:
            return True
        
        content_id = self._read_file_document_id(path)
        if content_id is not None and content_id.lower() == doc_lower:
            return True
        
        return False
    
    @staticmethod
    def _read_file_document_id(path: Path) -> Optional[str]:
        """Read document_id from a JSON file's content.
        
        Returns the document_id string if found, None otherwise.
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                doc_id = data.get("document_id")
                if isinstance(doc_id, str) and doc_id.strip():
                    return doc_id.strip()
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            pass
        return None
    
    def _is_excluded_file(self, path: Path) -> bool:
        """Check if file should be excluded (temp/test/intermediate)."""
        name_lower = path.name.lower()
        
        if name_lower in self.EXCLUDED_FILENAMES:
            return True
        
        for suffix in self.EXCLUDED_SUFFIXES:
            if name_lower.endswith(suffix):
                return True
        
        if name_lower.startswith("_") or name_lower.startswith("."):
            return True
        
        return False
    
    def _validate_extraction_content(self, path: Path) -> bool:
        """Validate that file contains extraction result structure."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return False
        
        if not isinstance(data, dict):
            return False
        
        for marker in self.EXTRACTION_CONTENT_MARKERS:
            if marker in data:
                return True
        
        if "document_id" in data and ("merge_summary" in data or "dimensions" in data):
            return True
        
        name_lower = path.name.lower()
        if "extracted" in name_lower or "six_dimension" in name_lower:
            return True
        
        return False
    
    def _create_entry_from_file(
        self,
        file_path: Path,
        document_id: str,
        namespace: str,
    ) -> Optional[CacheEntry]:
        """Create a CacheEntry from a historical artifact file.
        
        Historical artifacts with UNKNOWN version metadata are marked as untrusted.
        Untrusted entries can be discovered but will NOT pass cache validation.
        """
        file_hash = compute_file_sha256(file_path)
        if not file_hash:
            return None
        
        versions = self._extract_versions_from_file(file_path)
        stage_name = self._infer_stage_name(file_path)
        artifact_type = self._infer_artifact_type(file_path, stage_name)
        
        has_unknown_version = any(
            v == "UNKNOWN" for v in [
                versions.get("pipeline_version", "UNKNOWN"),
                versions.get("schema_version", "UNKNOWN"),
                versions.get("prompt_version", "UNKNOWN"),
            ]
        )
        
        key = CacheKey(
            document_id=document_id,
            stage_name=stage_name,
            namespace=namespace,
            input_hash="UNKNOWN",
            pipeline_version=versions.get("pipeline_version", "UNKNOWN"),
            schema_version=versions.get("schema_version", "UNKNOWN"),
            prompt_version=versions.get("prompt_version", "UNKNOWN"),
        )
        
        return CacheEntry(
            key=key,
            source_path=str(file_path),
            created_at=versions.get("created_at", datetime.now().isoformat()),
            file_hash=file_hash,
            status=CacheStatus.FRESH,
            artifact_type=artifact_type,
            execution_type="historical",
            trusted=not has_unknown_version,
            metadata={
                "historical": True,
                "source_directory": file_path.parent.name,
                "version_metadata_complete": not has_unknown_version,
            },
        )
    
    def _extract_versions_from_file(self, file_path: Path) -> dict[str, str]:
        """Extract version metadata from a cache file."""
        versions: dict[str, str] = {}
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Look for version fields
            if isinstance(data, dict):
                versions["pipeline_version"] = data.get("pipeline_version", "UNKNOWN")
                versions["schema_version"] = data.get("schema_version", "UNKNOWN")
                versions["prompt_version"] = data.get("prompt_version", "UNKNOWN")
                versions["created_at"] = data.get("created_at", data.get("merge_date", ""))
        except Exception:
            pass
        return versions
    
    def _infer_stage_name(self, file_path: Path) -> str:
        """Infer the stage name from the file path/name."""
        name = file_path.name.lower()
        
        if "six_dimension" in name or "extraction" in name:
            return "six_dimension_extraction"
        elif "num_unit" in name or "quantity" in name:
            return "num_unit_normalization"
        elif "quality" in name or "qa" in name:
            return "quality_gate"
        elif "canonical" in name or "store" in name:
            return "canonical_store"
        elif "report" in name:
            return "report_generation"
        elif "figure" in name:
            return "figure_text_association"
        elif "document_ir" in name:
            return "document_ir"
        elif "parse" in name or "mineru" in name:
            return "pdf_parse"
        else:
            return "unknown"
    
    @staticmethod
    def _infer_artifact_type(file_path: Path, stage_name: str) -> str:
        """Infer the artifact type from file path and stage name.
        
        Returns one of: extraction, normalization, qa_report, store_index,
                        report, figure_association, document_ir, pdf_parse, unknown
        """
        name = file_path.name.lower()
        
        if "six_dimension" in name or "extracted" in name:
            return "extraction"
        elif "normalized" in name or "quantity" in name:
            return "normalization"
        elif "qa_report" in name or "qa" in name:
            return "qa_report"
        elif "store_index" in name or "canonical" in name:
            return "store_index"
        elif "report" in name and "phase" not in name:
            return "report"
        elif "figure" in name or "association" in name:
            return "figure_association"
        elif stage_name != "unknown":
            return stage_name
        return "unknown"
    
    def validate_cache(
        self,
        key: CacheKey,
        namespace: Optional[str] = None,
    ) -> tuple[CacheStatus, Optional[CacheEntry]]:
        """Validate cache for the given key.
        
        Returns:
            Tuple of (status, entry) where:
            - status: CacheStatus indicating validity
            - entry: CacheEntry if found, None otherwise
        
        Validation dimensions:
        1. Entry must be trusted (has verified version metadata)
        2. Input hash must match
        3. Pipeline version must match
        4. Schema version must match
        5. Prompt version must match
        
        Any mismatch -> STALE or INVALID
        """
        ns = namespace or key.namespace
        index = self._indices.get(ns)
        if not index:
            return CacheStatus.MISSING, None
        
        entry = index.find_by_partial_key(
            key.document_id, key.stage_name, ns,
        )
        
        if not entry:
            return CacheStatus.MISSING, None
        
        if not entry.trusted:
            logger.info(
                "Cache INVALID for %s/%s: untrusted entry (missing version metadata)",
                key.document_id, key.stage_name,
            )
            entry.status = CacheStatus.INVALID
            return CacheStatus.INVALID, entry
        
        if not entry.key.matches(key):
            if entry.key.input_hash != key.input_hash:
                logger.info(
                    "Cache STALE for %s/%s: input hash mismatch",
                    key.document_id, key.stage_name,
                )
            elif entry.key.pipeline_version != key.pipeline_version:
                logger.info(
                    "Cache STALE for %s/%s: pipeline version mismatch (%s vs %s)",
                    key.document_id, key.stage_name,
                    entry.key.pipeline_version, key.pipeline_version,
                )
            elif entry.key.schema_version != key.schema_version:
                logger.info(
                    "Cache STALE for %s/%s: schema version mismatch (%s vs %s)",
                    key.document_id, key.stage_name,
                    entry.key.schema_version, key.schema_version,
                )
            elif entry.key.prompt_version != key.prompt_version:
                logger.info(
                    "Cache STALE for %s/%s: prompt version mismatch (%s vs %s)",
                    key.document_id, key.stage_name,
                    entry.key.prompt_version, key.prompt_version,
                )
            entry.status = CacheStatus.STALE
            return CacheStatus.STALE, entry
        
        if not Path(entry.source_path).exists():
            logger.warning(
                "Cache file missing: %s", entry.source_path,
            )
            return CacheStatus.MISSING, None
        
        entry.status = CacheStatus.FRESH
        return CacheStatus.FRESH, entry
    
    def register_cache(
        self,
        key: CacheKey,
        source_path: str | Path,
        metadata: Optional[dict[str, Any]] = None,
        artifact_type: Optional[str] = None,
        execution_type: str = "fresh",
    ) -> CacheEntry:
        """Register a new cache artifact.
        
        New registrations are always trusted (trusted=True) because they have
        verified version metadata from the current pipeline run.
        
        Args:
            key: CacheKey with all validation dimensions
            source_path: Path to the cache file
            metadata: Optional additional metadata
            artifact_type: Type of artifact (inferred from stage_name if not provided)
            execution_type: How this was produced (fresh, cache_reuse, recovered)
        
        Returns:
            CacheEntry that was registered
        """
        source_path = Path(source_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Cache file not found: {source_path}")
        
        try:
            with open(source_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError(f"Cache file is not a JSON object: {source_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Cache file contains invalid JSON: {source_path}: {e}")
        
        file_hash = compute_file_sha256(source_path)
        if not file_hash:
            raise ValueError(f"Failed to compute hash for: {source_path}")
        
        if artifact_type is None:
            artifact_type = self._infer_artifact_type(source_path, key.stage_name)
        
        entry = CacheEntry(
            key=key,
            source_path=str(source_path),
            created_at=datetime.now().isoformat(),
            file_hash=file_hash,
            status=CacheStatus.FRESH,
            artifact_type=artifact_type,
            execution_type=execution_type,
            trusted=True,
            metadata=metadata or {},
        )
        
        index = self.get_or_create_index(key.namespace)
        index.add_entry(entry)
        self._save_index()
        
        logger.info(
            "Registered cache for %s/%s: %s (trusted=%s, type=%s)",
            key.document_id, key.stage_name, source_path,
            entry.trusted, entry.artifact_type,
        )
        return entry
    
    def invalidate_cache(
        self,
        document_id: str,
        stage_name: str,
        namespace: Optional[str] = None,
    ) -> int:
        """Invalidate all cache entries for a specific stage.
        
        Returns:
            Number of entries invalidated
        """
        ns = namespace or document_id
        index = self._indices.get(ns)
        if not index:
            return 0
        
        invalidated = 0
        to_remove = []
        for path, entry in index.entries.items():
            if entry.key.document_id == document_id and entry.key.stage_name == stage_name:
                entry.status = CacheStatus.STALE
                to_remove.append(path)
                invalidated += 1
        
        for path in to_remove:
            index.remove_entry(path)
        
        if invalidated > 0:
            self._save_index()
            logger.info(
                "Invalidated %d cache entries for %s/%s",
                invalidated, document_id, stage_name,
            )
        
        return invalidated
    
    def invalidate_downstream(
        self,
        document_id: str,
        stage_name: str,
        namespace: Optional[str] = None,
    ) -> int:
        """Invalidate cache for a stage and all downstream stages.
        
        Uses the pipeline DAG to determine downstream dependencies.
        
        Returns:
            Total number of entries invalidated
        """
        # Define stage order for downstream calculation
        stage_order = [
            "pdf_parse",
            "document_ir",
            "figure_text_association",
            "six_dimension_extraction",
            "num_unit_normalization",
            "quality_gate",
            "canonical_store",
            "report_generation",
        ]
        
        if stage_name not in stage_order:
            logger.warning("Unknown stage: %s", stage_name)
            return self.invalidate_cache(document_id, stage_name, namespace)
        
        # Find index of current stage
        start_idx = stage_order.index(stage_name)
        downstream_stages = stage_order[start_idx:]
        
        total_invalidated = 0
        for stage in downstream_stages:
            total_invalidated += self.invalidate_cache(
                document_id, stage, namespace,
            )
        
        return total_invalidated
    
    def get_cache_label(
        self,
        key: CacheKey,
        namespace: Optional[str] = None,
    ) -> CacheLabel:
        """Get the unified cache label for a stage execution.
        
        Returns one of: FRESH, CACHE_REUSE, STALE, MISSING
        """
        status, entry = self.validate_cache(key, namespace)
        
        if status == CacheStatus.FRESH:
            return CacheLabel.CACHE_REUSE
        elif status == CacheStatus.STALE:
            return CacheLabel.FRESH  # Will re-extract
        elif status == CacheStatus.MISSING:
            return CacheLabel.FRESH  # No cache, will extract
        else:
            return CacheLabel.FRESH  # Invalid cache, will extract
    
    def get_authoritative_artifact(
        self,
        document_id: str,
        stage_name: str = "six_dimension_extraction",
        namespace: Optional[str] = None,
    ) -> ArtifactResult:
        """Get the authoritative (most recent verified) artifact.
        
        Only considers trusted entries with verified version metadata.
        Returns AMBIGUOUS when multiple trusted candidates exist at the same
        priority level and no single authoritative version can be determined.
        
        Priority:
        1. PHASE345_SIX_DIMENSION_FINAL.json (Phase 3.4.5 final merge)
        2. PHASE343_SIX_DIMENSION_RESULT.json (Phase 3.4.3 recovery)
        3. Latest *_v2_extracted.json (Phase 3.4.2)
        4. Any *_extracted.json (Phase 3)
        
        Returns:
            ArtifactResult with resolution status and entry/candidates
        """
        discovered = self.discover_historical_artifacts(
            document_id, namespace, artifact_type="extraction",
        )
        
        trusted = [e for e in discovered if e.trusted and e.key.stage_name == stage_name]
        
        if not trusted:
            all_trusted = [e for e in discovered if e.trusted]
            if all_trusted:
                trusted = all_trusted
            else:
                return ArtifactResult(
                    resolution=ArtifactResolution.NOT_FOUND,
                    candidates=discovered,
                )
        
        def priority_key(entry: CacheEntry) -> int:
            path = entry.source_path.lower()
            if "phase345" in path and "final" in path:
                return 0
            elif "phase343" in path:
                return 1
            elif "v2_extracted" in path:
                return 2
            elif "extracted" in path:
                return 3
            else:
                return 4
        
        trusted.sort(key=priority_key)
        best_priority = priority_key(trusted[0])
        top_candidates = [e for e in trusted if priority_key(e) == best_priority]
        
        if len(top_candidates) > 1:
            logger.warning(
                "AMBIGUOUS: %d trusted candidates at priority %d for %s/%s",
                len(top_candidates), best_priority, document_id, stage_name,
            )
            return ArtifactResult(
                resolution=ArtifactResolution.AMBIGUOUS,
                entry=None,
                candidates=top_candidates,
            )
        
        return ArtifactResult(
            resolution=ArtifactResolution.FOUND,
            entry=top_candidates[0],
            candidates=top_candidates,
        )
    
    def summary(self, namespace: Optional[str] = None) -> dict[str, Any]:
        """Get a summary of cache status."""
        if namespace:
            indices = {namespace: self._indices.get(namespace)}
        else:
            indices = self._indices
        
        summary = {
            "total_namespaces": len(self._indices),
            "total_entries": sum(len(idx.entries) for idx in self._indices.values()),
            "pipeline_version": self.pipeline_version,
            "schema_version": self.schema_version,
            "prompt_version": self.prompt_version,
            "namespaces": {},
        }
        
        for ns, index in indices.items():
            if not index:
                continue
            status_counts = {}
            for entry in index.entries.values():
                status = entry.status.value
                status_counts[status] = status_counts.get(status, 0) + 1
            
            summary["namespaces"][ns] = {
                "entry_count": len(index.entries),
                "status_counts": status_counts,
                "updated_at": index.updated_at,
            }
        
        return summary
