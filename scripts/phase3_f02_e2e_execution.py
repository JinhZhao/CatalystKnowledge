#!/usr/bin/env python3
"""
PIPELINE-001 Phase 3: F02 End-to-End Real Execution

Performs a complete real execution of the pipeline for F02 document:
- Real PDF parsing (not reusing existing MinerU output)
- Real LLM calls for six-dimension extraction
- All stages with FRESH_EXECUTION status
- SHA256 tracking for all inputs/outputs
- Isolated output directory (no overwriting historical data)
"""

import hashlib
import json
import os
import shutil
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# Set LLM credentials (SiliconFlow API)
os.environ['LLM_API_BASE'] = 'https://api.siliconflow.cn/v1'
os.environ['LLM_API_KEY'] = 'sk-axbgbaleimmmpyepwhbgnpldiesqfmwerrwvxbxnscczspdv'
os.environ['LLM_MODEL'] = 'deepseek-ai/DeepSeek-V4-Flash'

PROJECT_ROOT = Path(r"D:\Knowledge_World")
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Phase 3 run directory
RUN_ID = f"phase3_f02_e2e_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
RUN_DIR = PROJECT_ROOT / "runs" / "pipeline_001" / "phase3" / "f02_e2e"
RUN_DIR.mkdir(parents=True, exist_ok=True)

# F02 source data
F02_PDF = PROJECT_ROOT / "_test_download_frontiers" / "Frontiers_Catalysis_PDF_Alternative_Kit" / "downloaded_frontiers" / "papers" / "F02" / "main.pdf"
F02_MANIFEST_ENTRY = {
    "document_id": "F02",
    "group": "T1_Frontiers_Paper",
    "document_type": "research_article",
    "file_path": str(F02_PDF),
    "doi": "10.3389/fchem.2024.1439185",
    "title": "Photothermal oxidative dehydrogenation of propane to propylene over Cu/BN catalysts",
}

# Stage output directories
STAGE_DIRS = {
    "src001": RUN_DIR / "01_src001_identity",
    "pdf_parse": RUN_DIR / "02_pdf_parse",
    "document_ir": RUN_DIR / "03_document_ir",
    "figure_text": RUN_DIR / "04_figure_text",
    "extraction": RUN_DIR / "05_extraction",
    "num_unit": RUN_DIR / "06_num_unit",
    "quality_gate": RUN_DIR / "07_quality_gate",
    "store": RUN_DIR / "08_store",
    "report": RUN_DIR / "09_report",
}

for d in STAGE_DIRS.values():
    d.mkdir(parents=True, exist_ok=True)


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash of a file."""
    if not file_path.exists():
        return "FILE_NOT_FOUND"
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_dir_sha256(dir_path: Path) -> Dict[str, str]:
    """Compute SHA256 for all files in a directory."""
    hashes = {}
    if dir_path.exists():
        for f in sorted(dir_path.rglob("*")):
            if f.is_file():
                rel = f.relative_to(dir_path)
                hashes[str(rel)] = compute_sha256(f)
    return hashes


class Phase3Executor:
    """Execute Phase 3 stages with full tracking."""

    def __init__(self):
        self.results = {}
        self.stage_status = {}
        self.stage_hashes = {}
        self.start_time = datetime.now()

    def record_stage(self, stage_name: str, status: str, output: Dict = None,
                     error: str = None, input_hashes: Dict = None,
                     output_hashes: Dict = None, execution_type: str = "FRESH_EXECUTION"):
        """Record stage execution result."""
        self.stage_status[stage_name] = status
        self.stage_hashes[stage_name] = {
            "input": input_hashes or {},
            "output": output_hashes or {},
        }
        self.results[stage_name] = {
            "stage_name": stage_name,
            "status": status,
            "execution_type": execution_type,
            "output": output or {},
            "error": error,
            "timestamp": datetime.now().isoformat(),
        }
        print(f"  [{status}] {stage_name} ({execution_type})")

    # ====================================================================
    # Stage 1: SRC-001 Identity Registration
    # ====================================================================
    def run_src001(self):
        """SRC-001: Register F02 identity and verify SHA256."""
        print("\n=== Stage 1: SRC-001 Identity Registration ===")

        if not F02_PDF.exists():
            self.record_stage("src001", "FAILED", error=f"PDF not found: {F02_PDF}")
            return False

        pdf_sha256 = compute_sha256(F02_PDF)
        pdf_size = F02_PDF.stat().st_size

        identity = {
            "document_id": "F02",
            "file_path": str(F02_PDF),
            "file_size_bytes": pdf_size,
            "sha256": pdf_sha256,
            "signature_type": "PDF",
            "doi": F02_MANIFEST_ENTRY["doi"],
            "title": F02_MANIFEST_ENTRY["title"],
            "registration_timestamp": datetime.now().isoformat(),
        }

        identity_file = STAGE_DIRS["src001"] / "F02_identity.json"
        with open(identity_file, "w", encoding="utf-8") as f:
            json.dump(identity, f, indent=2, ensure_ascii=False)

        self.record_stage(
            "src001", "PASS",
            output=identity,
            input_hashes={"pdf": pdf_sha256},
            output_hashes={"identity": compute_sha256(identity_file)},
        )
        return True

    # ====================================================================
    # Stage 2: IR-001 PDF Parsing (Real execution)
    # ====================================================================
    def run_pdf_parse(self):
        """IR-001: Real PDF parsing via magic-pdf."""
        print("\n=== Stage 2: IR-001 PDF Parsing ===")

        output_dir = STAGE_DIRS["pdf_parse"] / "F02_batch"
        output_dir.mkdir(parents=True, exist_ok=True)

        import subprocess

        cmd = [
            "magic-pdf",
            "-p", str(F02_PDF),
            "-o", str(STAGE_DIRS["pdf_parse"]),
            "-m", "auto",
        ]

        print(f"  Executing: {' '.join(cmd)}")
        start = time.time()

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=900,
                encoding="utf-8",
                errors="replace",
            )
            elapsed = time.time() - start

            if proc.returncode == 0:
                auto_dir = output_dir / "main" / "auto"
                if not auto_dir.exists():
                    auto_dir = STAGE_DIRS["pdf_parse"] / "F02_batch" / "auto"

                output_files = {}
                if auto_dir.exists():
                    output_files = compute_dir_sha256(auto_dir)

                self.record_stage(
                    "pdf_parse", "PASS",
                    output={
                        "output_dir": str(auto_dir),
                        "processing_time_seconds": elapsed,
                        "md_count": len(list(auto_dir.glob("*.md"))) if auto_dir.exists() else 0,
                        "json_count": len(list(auto_dir.glob("*.json"))) if auto_dir.exists() else 0,
                    },
                    input_hashes={"pdf": compute_sha256(F02_PDF)},
                    output_hashes=output_files,
                    execution_type="FRESH_EXECUTION",
                )
                return True
            else:
                self.record_stage(
                    "pdf_parse", "FAILED",
                    error=f"magic-pdf returned {proc.returncode}: {proc.stderr[:500]}",
                    execution_type="FRESH_EXECUTION",
                )
                return False

        except subprocess.TimeoutExpired:
            self.record_stage("pdf_parse", "FAILED", error="Timeout after 900s")
            return False
        except FileNotFoundError:
            self.record_stage("pdf_parse", "FAILED", error="magic-pdf command not found")
            return False
        except Exception as e:
            self.record_stage("pdf_parse", "FAILED", error=str(e))
            return False

    # ====================================================================
    # Stage 3: Document IR
    # ====================================================================
    def run_document_ir(self):
        """Document IR: Extract blocks with stable Element IDs."""
        print("\n=== Stage 3: Document IR ===")

        from catalyst_knowledge.pipeline.adapters.document_ir_adapter import run_document_ir

        mineru_output = str(STAGE_DIRS["pdf_parse"])
        output_dir = str(STAGE_DIRS["document_ir"])

        result = run_document_ir(
            document_id="F02",
            mineru_output=mineru_output,
            output_dir=output_dir,
        )

        status = "PASS" if result.get("document_ir_status") == "PASS" else "FAILED"
        output_hashes = {}
        for key in ["document_ir_path", "blocks_output", "content_list_output"]:
            if key in result and result[key]:
                p = Path(result[key])
                if p.exists():
                    output_hashes[key] = compute_sha256(p)

        self.record_stage(
            "document_ir", status,
            output=result,
            output_hashes=output_hashes,
            execution_type="FRESH_EXECUTION",
        )
        return status == "PASS"

    # ====================================================================
    # Stage 4: Figure-Text Association
    # ====================================================================
    def run_figure_text(self):
        """FIG/TAB-001: Figure-text association."""
        print("\n=== Stage 4: Figure-Text Association ===")

        from catalyst_knowledge.pipeline.adapters.figure_text_adapter import (
            run_figure_text_association,
        )

        mineru_output = str(STAGE_DIRS["pdf_parse"])
        output_dir = str(STAGE_DIRS["figure_text"])

        result = run_figure_text_association(
            document_id="F02",
            mineru_output=mineru_output,
            output_dir=output_dir,
        )

        status = result.get("figure_text_status", "FAILED")
        output_hashes = {}
        if "figure_associations_path" in result and result["figure_associations_path"]:
            p = Path(result["figure_associations_path"])
            if p.exists():
                output_hashes["figure_associations"] = compute_sha256(p)

        self.record_stage(
            "figure_text", status,
            output=result,
            output_hashes=output_hashes,
            execution_type="FRESH_EXECUTION",
        )
        return status in ("PASS", "WARN")

    # ====================================================================
    # Stage 5: Six-Dimension Extraction (Real LLM)
    # ====================================================================
    def run_extraction(self):
        """EXT-001: Six-dimension LLM extraction (REAL CALL)."""
        print("\n=== Stage 5: Six-Dimension Extraction (Real LLM) ===")

        from catalyst_knowledge.pipeline.adapters.extraction_adapter import run_extraction

        # Load pipeline config
        from catalyst_knowledge.pipeline.config_loader import ConfigLoader
        config = ConfigLoader()
        config.load(str(PROJECT_ROOT / "config" / "pipeline.yaml"))

        mineru_output = str(STAGE_DIRS["pdf_parse"])
        output_dir = str(STAGE_DIRS["extraction"])

        result = run_extraction(
            document_id="F02",
            mineru_output=mineru_output,
            output_dir=output_dir,
            config=config.config,
            use_cache=False,  # FORCE REAL LLM CALL
        )

        status = result.get("extraction_status", "FAILED")
        output_hashes = compute_dir_sha256(STAGE_DIRS["extraction"] / "F02")

        self.record_stage(
            "extraction", status,
            output=result,
            output_hashes=output_hashes,
            execution_type="FRESH_EXECUTION",
        )
        return status in ("PASS", "PARTIAL")

    # ====================================================================
    # Stage 6: Num-Unit Normalization
    # ====================================================================
    def run_num_unit(self):
        """NUM-UNIT-001: Quantity recognition and normalization."""
        print("\n=== Stage 6: Num-Unit Normalization ===")

        from catalyst_knowledge.pipeline.adapters.num_unit_adapter import (
            run_num_unit_normalization,
        )

        extraction_output = str(STAGE_DIRS["extraction"] / "F02")
        output_dir = str(STAGE_DIRS["num_unit"])
        quantity_defs = str(PROJECT_ROOT / "config" / "quantity_definitions.yaml")

        result = run_num_unit_normalization(
            document_id="F02",
            extraction_output_path=extraction_output,
            output_dir=output_dir,
            quantity_definitions_path=quantity_defs,
        )

        status = result.get("num_unit_status", "FAILED")
        output_hashes = {}
        if "num_unit_output_path" in result and result["num_unit_output_path"]:
            p = Path(result["num_unit_output_path"])
            if p.exists():
                output_hashes["num_unit_output"] = compute_sha256(p)

        self.record_stage(
            "num_unit", status,
            output=result,
            output_hashes=output_hashes,
            execution_type="FRESH_EXECUTION",
        )
        return status == "PASS"

    # ====================================================================
    # Stage 7: Quality Gate
    # ====================================================================
    def run_quality_gate(self):
        """QA-001: Quality gate validation."""
        print("\n=== Stage 7: Quality Gate ===")

        from catalyst_knowledge.pipeline.adapters.quality_gate_adapter import (
            run_quality_gate,
        )

        extraction_output = str(STAGE_DIRS["extraction"] / "F02")
        output_dir = str(STAGE_DIRS["quality_gate"])

        result = run_quality_gate(
            document_id="F02",
            extraction_output_path=extraction_output,
            output_dir=output_dir,
        )

        status = result.get("qa_status", "FAILED")
        output_hashes = {}
        if "qa_report_path" in result and result["qa_report_path"]:
            p = Path(result["qa_report_path"])
            if p.exists():
                output_hashes["qa_report"] = compute_sha256(p)

        self.record_stage(
            "quality_gate", status,
            output=result,
            output_hashes=output_hashes,
            execution_type="FRESH_EXECUTION",
        )
        return status == "PASS"

    # ====================================================================
    # Stage 8: Canonical Store
    # ====================================================================
    def run_store(self):
        """STORE-001: Isolated canonical storage."""
        print("\n=== Stage 8: Canonical Store ===")

        from catalyst_knowledge.pipeline.adapters.store_adapter import (
            run_canonical_store,
        )

        store_dir = str(STAGE_DIRS["store"])
        extraction_output = str(STAGE_DIRS["extraction"] / "F02")
        qa_report = str(STAGE_DIRS["quality_gate"] / "F02_qa_report.json")

        result = run_canonical_store(
            document_id="F02",
            qa_report_path=qa_report,
            extraction_output_path=extraction_output,
            store_dir=store_dir,
        )

        status = result.get("store_status", "FAILED")
        output_hashes = compute_dir_sha256(STAGE_DIRS["store"])

        self.record_stage(
            "store", status,
            output=result,
            output_hashes=output_hashes,
            execution_type="FRESH_EXECUTION",
        )
        return status == "PASS"

    # ====================================================================
    # Stage 9: Report Generation
    # ====================================================================
    def run_report(self):
        """Report: Generate JSON and Markdown reports."""
        print("\n=== Stage 9: Report Generation ===")

        from catalyst_knowledge.pipeline.adapters.report_adapter import (
            run_report_generation,
        )

        store_path = str(STAGE_DIRS["store"])
        output_dir = str(STAGE_DIRS["report"])

        result = run_report_generation(
            document_id="F02",
            store_path=store_path,
            output_dir=output_dir,
        )

        status = result.get("report_status", "FAILED")
        output_hashes = {}
        if "report_path" in result and result["report_path"]:
            p = Path(result["report_path"])
            if p.exists():
                output_hashes["report"] = compute_sha256(p)
            # Also hash any generated files
            report_dir = p.parent if p.is_file() else p
            if report_dir.exists():
                output_hashes.update(compute_dir_sha256(report_dir))

        self.record_stage(
            "report", status,
            output=result,
            output_hashes=output_hashes,
            execution_type="FRESH_EXECUTION",
        )
        return status == "PASS"

    # ====================================================================
    # Full Execution
    # ====================================================================
    def run_all(self):
        """Execute all stages in order."""
        print(f"\n{'='*70}")
        print(f"PIPELINE-001 Phase 3: F02 End-to-End Real Execution")
        print(f"Run ID: {RUN_ID}")
        print(f"Run Directory: {RUN_DIR}")
        print(f"Start Time: {self.start_time.isoformat()}")
        print(f"{'='*70}")

        stages = [
            ("src001", self.run_src001),
            ("pdf_parse", self.run_pdf_parse),
            ("document_ir", self.run_document_ir),
            ("figure_text", self.run_figure_text),
            ("extraction", self.run_extraction),
            ("num_unit", self.run_num_unit),
            ("quality_gate", self.run_quality_gate),
            ("store", self.run_store),
            ("report", self.run_report),
        ]

        for stage_name, stage_func in stages:
            try:
                success = stage_func()
                if not success:
                    print(f"\n  WARNING: {stage_name} did not pass, continuing...")
            except Exception as e:
                print(f"\n  ERROR: {stage_name} raised exception: {e}")
                traceback.print_exc()
                self.record_stage(stage_name, "FAILED", error=str(e))

        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()

        # Save execution manifest
        manifest = {
            "run_id": RUN_ID,
            "document_id": "F02",
            "phase": 3,
            "start_time": self.start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": duration,
            "stages": self.results,
            "stage_status_summary": self.stage_status,
            "stage_hashes": self.stage_hashes,
        }

        manifest_file = RUN_DIR / "PHASE3_EXECUTION_MANIFEST.json"
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False, default=str)

        print(f"\n{'='*70}")
        print(f"Phase 3 Execution Complete")
        print(f"Duration: {duration:.1f}s")
        print(f"Stage Results:")
        for name, status in self.stage_status.items():
            print(f"  {name}: {status}")
        print(f"Manifest: {manifest_file}")
        print(f"{'='*70}")

        return manifest


if __name__ == "__main__":
    executor = Phase3Executor()
    manifest = executor.run_all()
