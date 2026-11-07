"""StageAdapter — unified interface for pipeline stage execution.

Wraps existing Python functions and standalone scripts into a uniform
stage abstraction with:
- Input/output data contracts
- Error handling and diagnostics
- Timeout support
- Execution logging
- Stage status recording
- Input/output validation
"""

from __future__ import annotations

import concurrent.futures
import importlib
import importlib.util
import json
import logging
import shutil
import sys
import tempfile
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from .run_manifest import StageRecord, compute_file_sha256

logger = logging.getLogger(__name__)


@dataclass
class StageResult:
    """Result of a stage execution."""
    stage_name: str
    success: bool
    output: Any = None
    output_files: list[str] = field(default_factory=list)
    error: Optional[str] = None
    traceback_str: Optional[str] = None
    duration_seconds: Optional[float] = None
    skipped: bool = False
    skip_reason: Optional[str] = None


@dataclass
class DataContract:
    """Declares what a stage expects as input and produces as output."""
    required_inputs: list[str] = field(default_factory=list)
    optional_inputs: list[str] = field(default_factory=list)
    required_outputs: list[str] = field(default_factory=list)
    optional_outputs: list[str] = field(default_factory=list)
    input_file_patterns: list[str] = field(default_factory=list)
    output_file_patterns: list[str] = field(default_factory=list)


class StageAdapter:
    """Unified adapter for calling pipeline stages.

    Supports three modes:
    1. function — wraps a callable
    2. script_module — loads and runs a standalone .py script's main()
    3. script_class — loads a class from a .py script and calls a method
    """

    def __init__(
        self,
        stage_name: str,
        version: str = "1.0.0",
        input_contract: Optional[DataContract] = None,
        output_contract: Optional[DataContract] = None,
        dependencies: Optional[list[str]] = None,
        timeout_seconds: int = 300,
    ):
        self.stage_name = stage_name
        self.version = version
        self.input_contract = input_contract or DataContract()
        self.output_contract = output_contract or DataContract()
        self.dependencies = dependencies or []
        self.timeout_seconds = timeout_seconds
        self._executor: Optional[Callable] = None
        self._executor_type: str = "none"

    def set_function(self, func: Callable, **fixed_kwargs: Any) -> StageAdapter:
        """Set a Python callable as the stage executor."""
        self._executor = func
        self._executor_type = "function"
        self._fixed_kwargs = fixed_kwargs
        return self

    def set_script_function(
        self,
        script_path: Path | str,
        func_name: str = "main",
        **fixed_kwargs: Any,
    ) -> StageAdapter:
        """Load a function from a standalone .py script."""
        self._script_path = Path(script_path)
        self._func_name = func_name
        self._fixed_kwargs = fixed_kwargs
        self._executor_type = "script_function"
        self._executor = self._make_script_function_executor()
        return self

    def set_script_class_method(
        self,
        script_path: Path | str,
        class_name: str,
        method_name: str,
        init_args: Optional[tuple] = None,
        init_kwargs: Optional[dict] = None,
        **fixed_kwargs: Any,
    ) -> StageAdapter:
        """Load a class from a script and call a method on it."""
        self._script_path = Path(script_path)
        self._class_name = class_name
        self._method_name = method_name
        self._init_args = init_args or ()
        self._init_kwargs = init_kwargs or {}
        self._fixed_kwargs = fixed_kwargs
        self._executor_type = "script_class_method"
        self._executor = self._make_script_class_executor()
        return self

    def execute(
        self,
        stage_data: dict[str, Any],
        stage_record: StageRecord,
        dry_run: bool = False,
    ) -> StageResult:
        """Execute the stage with full diagnostics and temp output isolation.

        Output isolation: when output_dir is configured, the stage writes to a
        temp directory first. Only on success are files published to the real
        output_dir. On failure/timeout the temp directory is cleaned up, so
        partial output never enters the Store or cache.

        Args:
            stage_data: Input data dict (keys match input_contract)
            stage_record: RunManifest StageRecord for this execution
            dry_run: If True, validate only — don't execute

        Returns:
            StageResult with output or error info
        """
        logger.info("[%s] Starting stage (type=%s, dry_run=%s)",
                     self.stage_name, self._executor_type, dry_run)

        stage_record.mark_start()
        self._record_inputs(stage_record, stage_data)

        if dry_run:
            stage_record.mark_skipped("dry_run")
            return StageResult(
                stage_name=self.stage_name,
                success=True,
                skipped=True,
                skip_reason="dry_run",
            )

        try:
            self._validate_inputs(stage_data)
        except ContractValidationError as e:
            stage_record.mark_failed(f"Input validation: {e}")
            return StageResult(
                stage_name=self.stage_name,
                success=False,
                error=f"Input validation failed: {e}",
            )

        if self._executor is None:
            stage_record.mark_failed("No executor configured")
            return StageResult(
                stage_name=self.stage_name,
                success=False,
                error="No executor configured for this stage",
            )

        real_output_dir = self._fixed_kwargs.get("output_dir")
        temp_dir = None
        if real_output_dir:
            temp_dir = tempfile.mkdtemp(prefix=f"{self.stage_name}_")
            self._fixed_kwargs["output_dir"] = temp_dir
            logger.info("[%s] Temp output: %s (real: %s)",
                        self.stage_name, temp_dir, real_output_dir)

        try:
            output = self._execute_with_timeout(stage_data)
        except TimeoutError:
            msg = f"Stage timed out after {self.timeout_seconds}s"
            stage_record.mark_failed(msg)
            logger.error("[%s] %s", self.stage_name, msg)
            self._cleanup_temp(temp_dir)
            return StageResult(
                stage_name=self.stage_name,
                success=False,
                error=msg,
            )
        except Exception as e:
            tb = traceback.format_exc()
            stage_record.mark_failed(str(e), tb)
            logger.error("[%s] Failed: %s\n%s", self.stage_name, e, tb)
            self._cleanup_temp(temp_dir)
            return StageResult(
                stage_name=self.stage_name,
                success=False,
                error=str(e),
                traceback_str=tb,
            )
        finally:
            if real_output_dir:
                self._fixed_kwargs["output_dir"] = real_output_dir

        try:
            if isinstance(output, dict):
                self._validate_outputs(output)
        except ContractValidationError as e:
            stage_record.mark_failed(f"Output validation: {e}")
            self._cleanup_temp(temp_dir)
            return StageResult(
                stage_name=self.stage_name,
                success=False,
                output=output,
                error=f"Output validation failed: {e}",
            )

        # Check business status fields — a stage can have all required keys
        # but still report failure via its domain-specific status field.
        business_failure = self._check_business_status(output)
        if business_failure:
            stage_record.mark_failed(business_failure)
            self._cleanup_temp(temp_dir)
            logger.error("[%s] Business status failure: %s", self.stage_name, business_failure)
            return StageResult(
                stage_name=self.stage_name,
                success=False,
                output=output,
                error=business_failure,
            )

        # Validate that output paths point to real files on disk
        missing_files = self._validate_output_files(output)
        if missing_files:
            stage_record.mark_failed(f"Output files missing: {'; '.join(missing_files)}")
            self._cleanup_temp(temp_dir)
            logger.error("[%s] Missing output files: %s", self.stage_name, missing_files)
            return StageResult(
                stage_name=self.stage_name,
                success=False,
                output=output,
                error=f"Output files missing: {missing_files}",
            )

        is_not_implemented = (
            isinstance(output, dict)
            and output.get("implementation_status") == "NOT_IMPLEMENTED"
        )

        if is_not_implemented:
            stage_record.mark_not_implemented(
                f"{self.stage_name} is a stub (NOT_IMPLEMENTED)"
            )
            self._cleanup_temp(temp_dir)
            logger.info("[%s] Stub executed — NOT_IMPLEMENTED", self.stage_name)
        else:
            if temp_dir and real_output_dir:
                self._publish_temp_output(temp_dir, real_output_dir)
                output = self._remap_output_paths(output, temp_dir, real_output_dir)
            stage_record.mark_success()
            self._record_outputs(stage_record, output)
            logger.info("[%s] Completed successfully", self.stage_name)

        output_files = []
        if isinstance(output, dict):
            for v in output.values():
                if isinstance(v, (str, Path)):
                    p = Path(str(v))
                    if p.exists() and p.is_file():
                        output_files.append(str(p))
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, (str, Path)):
                            p = Path(str(item))
                            if p.exists() and p.is_file():
                                output_files.append(str(p))

        return StageResult(
            stage_name=self.stage_name,
            success=True,
            output=output,
            output_files=output_files,
        )

    # ------------------------------------------------------------------
    # Internal: timeout execution
    # ------------------------------------------------------------------

    def _execute_with_timeout(self, stage_data: dict[str, Any]) -> Any:
        merged = {**stage_data, **self._fixed_kwargs}
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = pool.submit(self._executor, **merged)
            return future.result(timeout=self.timeout_seconds)
        except concurrent.futures.TimeoutError:
            pool.shutdown(wait=False)
            raise TimeoutError(f"Stage timed out after {self.timeout_seconds}s")
        except Exception:
            pool.shutdown(wait=True)
            raise
        else:
            pool.shutdown(wait=True)

    # ------------------------------------------------------------------
    # Internal: temp output isolation
    # ------------------------------------------------------------------

    @staticmethod
    def _cleanup_temp(temp_dir: Optional[str]) -> None:
        if temp_dir and Path(temp_dir).exists():
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.debug("Cleaned up temp dir: %s", temp_dir)
            except Exception as e:
                logger.warning("Failed to clean temp dir %s: %s", temp_dir, e)

    @staticmethod
    def _publish_temp_output(temp_dir: str, real_output_dir: str) -> None:
        src = Path(temp_dir)
        dst = Path(real_output_dir)
        dst.mkdir(parents=True, exist_ok=True)
        for item in src.rglob("*"):
            if item.is_file():
                rel = item.relative_to(src)
                target = dst / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(item), str(target))
                logger.debug("Published: %s -> %s", item, target)
        logger.info("Published temp output %s -> %s", temp_dir, real_output_dir)

    @staticmethod
    def _remap_output_paths(output: Any, temp_dir: str, real_output_dir: str) -> Any:
        if not isinstance(output, dict):
            return output
        temp_prefix = str(Path(temp_dir))
        real_prefix = str(Path(real_output_dir))
        remapped = {}
        for key, value in output.items():
            if isinstance(value, str) and temp_prefix in value:
                remapped[key] = value.replace(temp_prefix, real_prefix)
            elif isinstance(value, list):
                remapped[key] = [
                    v.replace(temp_prefix, real_prefix) if isinstance(v, str) else v
                    for v in value
                ]
            else:
                remapped[key] = value
        return remapped

    # ------------------------------------------------------------------
    # Internal: script loading
    # ------------------------------------------------------------------

    def _make_script_function_executor(self) -> Callable:
        script_path = self._script_path
        func_name = self._func_name

        def executor(**kwargs):
            mod = _load_script_module(script_path)
            func = getattr(mod, func_name, None)
            if func is None:
                raise AttributeError(f"Function '{func_name}' not found in {script_path}")
            return func(**kwargs)

        return executor

    def _make_script_class_executor(self) -> Callable:
        script_path = self._script_path
        class_name = self._class_name
        method_name = self._method_name
        init_args = self._init_args
        init_kwargs = self._init_kwargs

        def executor(**kwargs):
            mod = _load_script_module(script_path)
            cls = getattr(mod, class_name, None)
            if cls is None:
                raise AttributeError(f"Class '{class_name}' not found in {script_path}")
            instance = cls(*init_args, **init_kwargs)
            method = getattr(instance, method_name, None)
            if method is None:
                raise AttributeError(f"Method '{method_name}' not found on {class_name}")
            return method(**kwargs)

        return executor

    # ------------------------------------------------------------------
    # Internal: contract validation
    # ------------------------------------------------------------------

    def _validate_inputs(self, stage_data: dict[str, Any]) -> None:
        errors = []
        for key in self.input_contract.required_inputs:
            if key not in stage_data:
                errors.append(f"Missing required input: '{key}'")
        if errors:
            raise ContractValidationError(errors)

    def _validate_outputs(self, output: dict[str, Any]) -> None:
        errors = []
        for key in self.output_contract.required_outputs:
            if key not in output:
                errors.append(f"Missing required output: '{key}'")
        if errors:
            raise ContractValidationError(errors)

    _BUSINESS_STATUS_FIELDS = {
        "extraction_status": "science_extraction_v2",
        "num_unit_status": "num_unit_normalization",
        "store_status": "canonical_store",
        "qa_status": "quality_gate",
        "report_status": "report_generation",
    }
    _BUSINESS_FAILURE_VALUES = {"FAILED", "ERROR"}

    def _check_business_status(self, output: dict[str, Any]) -> str | None:
        if not isinstance(output, dict):
            return None
        for field, stage_label in self._BUSINESS_STATUS_FIELDS.items():
            if field in output:
                status = str(output[field]).upper()
                if status in self._BUSINESS_FAILURE_VALUES:
                    error_detail = output.get("error", "no detail")
                    return f"{stage_label} reported {field}={status}: {error_detail}"
        return None

    _OUTPUT_PATH_KEYS = [
        "extraction_output_path",
        "num_unit_output_path",
        "store_path",
        "output_path",
        "qa_output_path",
        "report_output_path",
    ]

    def _validate_output_files(self, output: dict[str, Any]) -> list[str]:
        if not isinstance(output, dict):
            return []
        missing = []
        for key in self._OUTPUT_PATH_KEYS:
            if key in output:
                raw = output[key]
                if isinstance(raw, (str, Path)):
                    p = Path(str(raw))
                    if p.suffix:
                        if not p.exists():
                            missing.append(f"{key}={p}")
                    elif p.is_dir() and not p.exists():
                        missing.append(f"{key}={p}")
        return missing

    def _record_inputs(self, record: StageRecord, stage_data: dict[str, Any]) -> None:
        for key, value in stage_data.items():
            if isinstance(value, (str, Path)):
                p = Path(str(value))
                if p.exists() and p.is_file():
                    record.input_files.append(str(p))
                    h = compute_file_sha256(p)
                    if h:
                        record.input_hashes[str(p)] = h
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, (str, Path)):
                        p = Path(str(item))
                        if p.exists() and p.is_file():
                            record.input_files.append(str(p))
                            h = compute_file_sha256(p)
                            if h:
                                record.input_hashes[str(p)] = h

    def _record_outputs(self, record: StageRecord, output: Any) -> None:
        if isinstance(output, dict):
            for key, value in output.items():
                if isinstance(value, (str, Path)):
                    p = Path(str(value))
                    if p.exists() and p.is_file():
                        record.output_files.append(str(p))
                        h = compute_file_sha256(p)
                        if h:
                            record.output_hashes[str(p)] = h


class ContractValidationError(Exception):
    """Raised when data contract validation fails."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Contract validation failed: {'; '.join(errors)}")


def _load_script_module(script_path: Path):
    """Dynamically load a Python script as a module.

    Adds the script's directory to sys.path temporarily so that
    sibling imports (e.g. num_unit_001_loader) resolve correctly.
    """
    script_path = Path(script_path).resolve()
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    module_name = f"_pipeline_stage_{script_path.stem}"
    script_dir = str(script_path.parent)

    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    src_dir = str(script_path.parent.parent / "src")
    if src_dir not in sys.path and (script_path.parent.parent / "src").exists():
        sys.path.insert(0, src_dir)

    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create module spec for {script_path}")

    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod

    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        logger.error("Failed to load script %s: %s", script_path, e)
        raise

    return mod
