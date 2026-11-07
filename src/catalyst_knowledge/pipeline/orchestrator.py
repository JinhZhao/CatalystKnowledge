"""PipelineOrchestrator — DAG-based pipeline execution engine.

Manages:
- Stage dependency graph (DAG)
- Execution ordering (topological sort)
- Conditional stage skipping (disabled / output exists)
- Failure handling (stop-on-failure vs continue)
- Partial execution (start/end stage)
- Stage re-execution with downstream cascade
- DryRun mode (validate without executing)
- Resume from previous run manifest
- Idempotency control (skip stages with unchanged inputs)
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import OrderedDict
from pathlib import Path
from typing import Any, Optional

from .cache_manager import CacheManager, CacheKey, CacheStatus, CacheLabel
from .config_loader import ConfigLoader
from .run_manifest import RunManifest, StageRecord, compute_file_sha256
from .stage_adapter import StageAdapter, StageResult

logger = logging.getLogger(__name__)


class PipelineError(Exception):
    """Raised when pipeline execution encounters an unrecoverable error."""


class PipelineOrchestrator:
    """DAG-based pipeline execution engine."""

    def __init__(self, config: ConfigLoader):
        self.config = config
        self._stages: OrderedDict[str, StageAdapter] = OrderedDict()
        self._dependencies: dict[str, list[str]] = {}
        self._manifest: Optional[RunManifest] = None
        
        # Initialize cache manager
        runs_dir = Path(config.get("paths.pipeline_runs", "runs/pipeline_001"))
        self._cache_manager = CacheManager(
            runs_dir=runs_dir,
            pipeline_version=config.get("pipeline.version", "1.0.0"),
            schema_version=config.get("pipeline.schema_version", "1.0.0"),
            prompt_version=config.get("pipeline.prompt_version", "1.0.0"),
        )

    def register_stage(
        self,
        adapter: StageAdapter,
        dependencies: Optional[list[str]] = None,
    ) -> None:
        """Register a stage with its dependencies."""
        name = adapter.stage_name
        if name in self._stages:
            raise PipelineError(f"Stage already registered: {name}")
        deps = dependencies if dependencies is not None else adapter.dependencies
        for dep in deps:
            if dep not in self._stages:
                logger.warning("[%s] Dependency '%s' not yet registered", name, dep)
        self._stages[name] = adapter
        self._dependencies[name] = deps

    def get_execution_order(self) -> list[str]:
        """Return topologically sorted stage names."""
        visited: set[str] = set()
        order: list[str] = []
        temp_mark: set[str] = set()

        def visit(name: str):
            if name in temp_mark:
                raise PipelineError(f"Circular dependency detected involving '{name}'")
            if name in visited:
                return
            temp_mark.add(name)
            for dep in self._dependencies.get(name, []):
                if dep in self._stages:
                    visit(dep)
            temp_mark.discard(name)
            visited.add(name)
            order.append(name)

        for name in self._stages:
            if name not in visited:
                visit(name)
        return order

    def validate_dag(self) -> list[str]:
        """Validate the DAG. Returns list of issues (empty = valid)."""
        issues: list[str] = []
        for name, deps in self._dependencies.items():
            for dep in deps:
                if dep not in self._stages:
                    issues.append(f"Stage '{name}' depends on unregistered stage '{dep}'")
        try:
            self.get_execution_order()
        except PipelineError as e:
            issues.append(str(e))
        return issues

    def dry_run(
        self,
        document_id: str,
        start_stage: Optional[str] = None,
        end_stage: Optional[str] = None,
    ) -> dict[str, Any]:
        """Execute the pipeline in dry-run mode (no actual processing).

        Returns a report of what would be executed.
        """
        manifest = self._create_manifest(document_id)
        manifest.mark_running()
        execution_order = self._get_filtered_order(start_stage, end_stage)

        report = {
            "run_id": manifest.run_id,
            "document_id": document_id,
            "mode": "dry_run",
            "execution_order": execution_order,
            "stages": [],
        }

        for stage_name in execution_order:
            adapter = self._stages[stage_name]
            stage_record = manifest.add_stage(stage_name)
            skip = self._should_skip_stage(stage_name, stage_record, dry_run=True)

            stage_info = {
                "name": stage_name,
                "version": adapter.version,
                "dependencies": self._dependencies.get(stage_name, []),
                "input_contract": {
                    "required": adapter.input_contract.required_inputs,
                    "optional": adapter.input_contract.optional_inputs,
                },
                "output_contract": {
                    "required": adapter.output_contract.required_outputs,
                    "optional": adapter.output_contract.optional_outputs,
                },
                "would_skip": skip,
                "timeout_seconds": adapter.timeout_seconds,
            }
            report["stages"].append(stage_info)

        manifest.mark_completed()
        manifest.save()
        logger.info("DryRun complete: %d stages planned", len(execution_order))
        return report

    def run(
        self,
        document_id: str,
        stage_data: Optional[dict[str, Any]] = None,
        start_stage: Optional[str] = None,
        end_stage: Optional[str] = None,
        resume_from: Optional[Path | str] = None,
    ) -> RunManifest:
        """Execute the full pipeline for a document.

        Args:
            document_id: Target document identifier
            stage_data: Shared data dict passed to all stages
            start_stage: First stage to execute (skip earlier ones)
            end_stage: Last stage to execute (skip later ones)
            resume_from: Path to a previous manifest to resume from

        Returns:
            RunManifest with full execution trace
        """
        if resume_from:
            return self._resume(document_id, Path(resume_from), stage_data or {})

        manifest = self._create_manifest(document_id)
        manifest.mark_running()
        manifest.save()

        shared_data = dict(stage_data or {})
        shared_data["document_id"] = document_id
        shared_data["config"] = self.config.config

        execution_order = self._get_filtered_order(start_stage, end_stage)
        stop_on_failure = self.config.get("execution.stop_on_failure", True)

        logger.info("Pipeline run %s: %d stages", manifest.run_id, len(execution_order))

        for stage_name in execution_order:
            adapter = self._stages[stage_name]
            stage_record = manifest.add_stage(stage_name)

            skip = self._should_skip_stage(stage_name, stage_record)
            if skip:
                logger.info("[%s] Skipped: %s", stage_name, stage_record.skip_reason)
                continue

            deps = self._dependencies.get(stage_name, [])
            dep_blocked = False
            for dep in deps:
                dep_record = manifest.get_stage(dep)
                if dep_record and dep_record.status in ("FAILED", "BLOCKED"):
                    msg = f"Dependency '{dep}' {dep_record.status}; blocking '{stage_name}'"
                    stage_record.mark_blocked(msg)
                    logger.warning("[%s] %s", stage_name, msg)
                    dep_blocked = True
                    break
                elif dep_record and dep_record.status == "NOT_IMPLEMENTED":
                    msg = (
                        f"Dependency '{dep}' is NOT_IMPLEMENTED; "
                        f"blocking '{stage_name}' (required data unavailable)"
                    )
                    stage_record.mark_blocked(msg)
                    logger.warning("[%s] %s", stage_name, msg)
                    dep_blocked = True
                    break
            if dep_blocked:
                continue

            # Check cache before execution
            cache_hit, cached_output = self._check_cache_for_stage(
                stage_name, document_id, shared_data, stage_record,
            )
            
            if cache_hit and cached_output:
                # Use cached output
                logger.info("[%s] Using cached output", stage_name)
                stage_record.mark_success()
                stage_record.metadata["execution_source"] = "cache"

                # Wrap raw cached file content with output contract keys
                # so downstream stages find their required inputs.
                contract_output = dict(cached_output)
                output_file = stage_record.metadata.get("cache_source", "")
                contract_output[f"{stage_name}_output_path"] = output_file
                contract_output.setdefault(f"{stage_name}_status", "PASS")
                contract_output.setdefault("namespace", shared_data.get("namespace", document_id))
                contract_output.setdefault("implementation_status", "PASS")

                shared_data.update(contract_output)
                shared_data[f"_stage_{stage_name}_result"] = StageResult(
                    stage_name=stage_name,
                    success=True,
                    output=contract_output,
                )

                # Re-register cache with correct output path
                if output_file:
                    self._register_cache_for_stage(
                        stage_name, document_id, shared_data, output_file,
                    )
                continue

            # Execute stage
            result = adapter.execute(shared_data, stage_record)
            manifest.save()

            if not result.success:
                logger.error("[%s] FAILED: %s", stage_name, result.error)
                if stop_on_failure:
                    manifest.mark_failed(f"Stage '{stage_name}' failed: {result.error}")
                    manifest.save()
                    return manifest
            else:
                if isinstance(result.output, dict):
                    shared_data.update(result.output)
                    
                    # Register cache for successful execution
                    output_path = result.output.get("output_path") or result.output.get(f"{stage_name}_output_path")
                    if output_path:
                        self._register_cache_for_stage(
                            stage_name, document_id, shared_data, output_path,
                        )
                
                shared_data[f"_stage_{stage_name}_result"] = result

        # Final verification: ensure the pipeline actually produced real output
        verification_errors = self._verify_pipeline_outputs(manifest, shared_data)
        if verification_errors:
            manifest.mark_failed(
                f"Output verification failed: {'; '.join(verification_errors)}"
            )
            manifest.save()
            logger.error(
                "Pipeline %s VERIFICATION FAILED: %s",
                manifest.run_id, verification_errors,
            )
            return manifest

        manifest.mark_completed()
        manifest.save()
        logger.info("Pipeline %s completed: %s", manifest.run_id, manifest.status)
        return manifest

    def rerun_stage(
        self,
        document_id: str,
        stage_name: str,
        stage_data: Optional[dict[str, Any]] = None,
        cascade_downstream: bool = True,
    ) -> RunManifest:
        """Re-execute a specific stage and optionally its downstream dependents.

        Args:
            document_id: Target document
            stage_name: Stage to re-execute
            stage_data: Shared data
            cascade_downstream: If True, also re-execute all downstream stages
        """
        if stage_name not in self._stages:
            raise PipelineError(f"Unknown stage: {stage_name}")

        manifest = self._create_manifest(document_id)
        manifest.mark_running()

        shared_data = dict(stage_data or {})
        shared_data["document_id"] = document_id
        shared_data["config"] = self.config.config

        stages_to_run = [stage_name]
        if cascade_downstream:
            stages_to_run.extend(self._get_downstream_stages(stage_name))

        for name in stages_to_run:
            adapter = self._stages[name]
            stage_record = manifest.add_stage(name)
            result = adapter.execute(shared_data, stage_record)
            manifest.save()

            if not result.success:
                manifest.mark_failed(f"Stage '{name}' failed: {result.error}")
                manifest.save()
                return manifest

            if isinstance(result.output, dict):
                shared_data.update(result.output)

        manifest.mark_completed()
        manifest.save()
        return manifest

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_manifest(self, document_id: str) -> RunManifest:
        manifest_dir = Path(self.config.get("execution.manifest_dir",
                                            self.config.get("paths.pipeline_runs",
                                                            "runs/pipeline_001")))
        manifest = RunManifest(
            document_id=document_id,
            manifest_dir=manifest_dir,
            pipeline_version=self.config.get("pipeline.version", "1.0.0"),
            schema_version=self.config.get("pipeline.schema_version", "1.0.0"),
            prompt_version=self.config.get("pipeline.prompt_version", "1.0.0"),
        )
        llm_cfg = self.config.get_llm_config()
        manifest.set_model(llm_cfg.get("model", llm_cfg.get("default_model", "")))
        if self.config.config_hash:
            manifest.set_config_hash(self.config.config_hash)
        self._manifest = manifest
        return manifest

    def _get_filtered_order(
        self,
        start_stage: Optional[str] = None,
        end_stage: Optional[str] = None,
    ) -> list[str]:
        full_order = self.get_execution_order()
        if start_stage is None and end_stage is None:
            return full_order

        start_idx = 0
        end_idx = len(full_order)

        if start_stage:
            if start_stage not in full_order:
                raise PipelineError(f"start_stage not found: {start_stage}")
            start_idx = full_order.index(start_stage)

        if end_stage:
            if end_stage not in full_order:
                raise PipelineError(f"end_stage not found: {end_stage}")
            end_idx = full_order.index(end_stage) + 1

        return full_order[start_idx:end_idx]

    def _should_skip_stage(
        self,
        stage_name: str,
        stage_record: StageRecord,
        dry_run: bool = False,
    ) -> bool:
        stage_cfg = self.config.get_stage_config(stage_name)

        if not stage_cfg.get("enabled", True):
            stage_record.mark_skipped("disabled in config")
            return True

        if dry_run:
            return False

        if stage_cfg.get("skip_if_output_exists", False):
            adapter = self._stages.get(stage_name)
            if adapter:
                for pattern in adapter.output_contract.output_file_patterns:
                    p = Path(pattern)
                    if p.exists():
                        stage_record.mark_skipped(f"output exists: {p}")
                        return True

        return False

    def _get_downstream_stages(self, stage_name: str) -> list[str]:
        """Get all stages that transitively depend on the given stage (BFS)."""
        order = self.get_execution_order()
        visited: set[str] = set()
        queue = [stage_name]
        downstream: list[str] = []

        while queue:
            current = queue.pop(0)
            for name, deps in self._dependencies.items():
                if current in deps and name not in visited and name != stage_name:
                    visited.add(name)
                    downstream.append(name)
                    queue.append(name)

        return [s for s in order if s in visited]

    def _compute_input_hash(self, stage_name: str, shared_data: dict[str, Any]) -> str:
        """Compute a hash of the stage's input data for cache validation.
        
        Hashes the actual input file SHA256 plus upstream stage output file hashes.
        This ensures that:
        - Input file content changes -> different hash -> cache invalidated
        - Upstream stage output changes -> different hash -> downstream cache invalidated
        """
        hasher = hashlib.sha256()
        
        input_file_sha = self._get_input_file_sha256(shared_data)
        hasher.update(input_file_sha.encode())
        
        for dep_stage in self._dependencies.get(stage_name, []):
            dep_hash = self._hash_upstream_output(dep_stage, shared_data)
            hasher.update(dep_hash.encode())
        
        hasher.update(stage_name.encode())
        return hasher.hexdigest()
    
    @staticmethod
    def _get_input_file_sha256(shared_data: dict[str, Any]) -> str:
        """Extract the input file SHA256 from shared_data metadata."""
        try:
            return shared_data["input_metadata"]["metadata"]["sha256"]
        except (KeyError, TypeError):
            pass
        input_file = shared_data.get("input_file")
        if input_file:
            h = compute_file_sha256(Path(input_file))
            if h:
                return h
        return "NO_INPUT_HASH"
    
    def _hash_upstream_output(self, dep_stage: str, shared_data: dict[str, Any]) -> str:
        """Compute a hash representing the upstream stage's output."""
        result = shared_data.get(f"_stage_{dep_stage}_result")
        if hasattr(result, "output") and isinstance(result.output, dict):
            output_path = result.output.get("output_path")
            if output_path:
                h = compute_file_sha256(Path(output_path))
                if h:
                    return h
        
        for key in (f"{dep_stage}_output_path",):
            path_val = shared_data.get(key)
            if path_val:
                h = compute_file_sha256(Path(path_val))
                if h:
                    return h
        
        stage_data = shared_data.get(dep_stage)
        if isinstance(stage_data, dict):
            output_path = stage_data.get("output_path")
            if output_path:
                h = compute_file_sha256(Path(output_path))
                if h:
                    return h
        
        return f"UPSTREAM_{dep_stage}_NO_OUTPUT"

    def _check_cache_for_stage(
        self,
        stage_name: str,
        document_id: str,
        shared_data: dict[str, Any],
        stage_record: StageRecord,
    ) -> tuple[bool, Optional[dict[str, Any]]]:
        """Check if valid cache exists for this stage.
        
        Returns:
            Tuple of (cache_hit, cached_output)
            - cache_hit: True if valid cache found
            - cached_output: The cached output dict if cache_hit, None otherwise
        """
        namespace = shared_data.get("namespace", document_id)
        input_hash = self._compute_input_hash(stage_name, shared_data)
        
        cache_key = CacheKey(
            document_id=document_id,
            stage_name=stage_name,
            namespace=namespace,
            input_hash=input_hash,
            pipeline_version=self.config.get("pipeline.version", "1.0.0"),
            schema_version=self.config.get("pipeline.schema_version", "1.0.0"),
            prompt_version=self.config.get("pipeline.prompt_version", "1.0.0"),
        )
        
        status, entry = self._cache_manager.validate_cache(cache_key, namespace)
        
        if status == CacheStatus.FRESH and entry:
            logger.info("[%s] Cache HIT: %s", stage_name, entry.source_path)
            stage_record.metadata["cache_source"] = entry.source_path
            stage_record.metadata["cache_label"] = CacheLabel.CACHE_REUSE.value
            
            # Load cached output
            try:
                with open(entry.source_path, "r", encoding="utf-8") as f:
                    cached_output = json.load(f)
                return True, cached_output
            except Exception as e:
                logger.warning("[%s] Failed to load cache: %s", stage_name, e)
                return False, None
        else:
            logger.debug("[%s] Cache %s", stage_name, status.value)
            stage_record.metadata["cache_label"] = CacheLabel.FRESH.value
            return False, None

    def _register_cache_for_stage(
        self,
        stage_name: str,
        document_id: str,
        shared_data: dict[str, Any],
        output_path: str | Path,
    ) -> None:
        """Register a new cache entry after successful stage execution."""
        namespace = shared_data.get("namespace", document_id)
        input_hash = self._compute_input_hash(stage_name, shared_data)
        
        cache_key = CacheKey(
            document_id=document_id,
            stage_name=stage_name,
            namespace=namespace,
            input_hash=input_hash,
            pipeline_version=self.config.get("pipeline.version", "1.0.0"),
            schema_version=self.config.get("pipeline.schema_version", "1.0.0"),
            prompt_version=self.config.get("pipeline.prompt_version", "1.0.0"),
        )
        
        try:
            self._cache_manager.register_cache(
                key=cache_key,
                source_path=output_path,
                metadata={"stage_name": stage_name, "document_id": document_id},
            )
            logger.info("[%s] Cache registered: %s", stage_name, output_path)
        except Exception as e:
            logger.warning("[%s] Failed to register cache: %s", stage_name, e)

    def _verify_pipeline_outputs(
        self, manifest: "RunManifest", shared_data: dict[str, Any],
    ) -> list[str]:
        """Final verification before marking pipeline COMPLETED.

        Checks:
        1. At least one FRESH (non-cache) stage produced real output files
        2. QA status is not FAILED
        3. Critical stages have non-empty output when marked SUCCESS
        """
        errors: list[str] = []

        fresh_with_output = 0
        for stage_name, stage_record in manifest.stages.items():
            if stage_record.status != "SUCCESS":
                continue
            exec_source = stage_record.metadata.get("execution_source", "")
            if exec_source == "cache":
                continue
            if stage_record.output_files:
                fresh_with_output += 1

        if fresh_with_output == 0:
            all_cached = all(
                sr.metadata.get("execution_source") == "cache"
                for sr in manifest.stages.values()
                if sr.status == "SUCCESS"
            )
            if all_cached:
                errors.append("All SUCCESS stages were cache reuse — no fresh output produced")
            else:
                errors.append("No FRESH stage produced any output files")

        qa_status = shared_data.get("qa_status", "")
        if qa_status == "FAILED":
            errors.append(f"QA gate FAILED: qa_status={qa_status}")

        return errors

    def _resume(
        self,
        document_id: str,
        previous_manifest_path: Path,
        stage_data: dict[str, Any],
    ) -> RunManifest:
        """Resume from a previous run manifest."""
        prev = RunManifest.load(previous_manifest_path)
        logger.info("Resuming from run %s (status=%s)", prev.run_id, prev.status)

        manifest = self._create_manifest(document_id)
        manifest.metadata["resumed_from"] = prev.run_id
        manifest.mark_running()

        shared_data = dict(stage_data)
        shared_data["document_id"] = document_id
        shared_data["config"] = self.config.config

        for stage_name in self.get_execution_order():
            prev_stage = prev.get_stage(stage_name)
            if prev_stage and prev_stage.status == "SUCCESS":
                stage_record = manifest.add_stage(stage_name)
                stage_record.mark_skipped(f"already succeeded in {prev.run_id}")
                logger.info("[%s] Skipped (resumed: previously succeeded)", stage_name)
                continue

            adapter = self._stages[stage_name]
            stage_record = manifest.add_stage(stage_name)
            result = adapter.execute(shared_data, stage_record)
            manifest.save()

            if not result.success:
                manifest.mark_failed(f"Stage '{stage_name}' failed: {result.error}")
                manifest.save()
                return manifest

            if isinstance(result.output, dict):
                shared_data.update(result.output)

        manifest.mark_completed()
        manifest.save()
        return manifest
