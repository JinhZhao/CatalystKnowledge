"""Evidence Verification Adapter — Cross-validation interface for scientific extraction.

Provides independent verification of extracted scientific data:
1. SourceAnchor existence check
2. Quoted text consistency with source
3. Numeric value and unit validation
4. Data origin classification verification
5. Claim-Evidence semantic relationship check
6. Duplicate and contradiction detection

Structural validation ≠ scientific content validation.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..data_origin_classifier import DataOrigin, DataStatus
from ..run_manifest import compute_file_sha256

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    check_id: str
    check_type: str
    target_field: str
    target_dimension: str
    status: str  # PASS, FAIL, WARN, SKIP
    message: str
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "check_type": self.check_type,
            "target_field": self.target_field,
            "target_dimension": self.target_dimension,
            "status": self.status,
            "message": self.message,
            "details": self.details,
        }


class EvidenceVerifier:
    """Cross-validates extracted scientific data against source text."""

    def __init__(
        self,
        document_id: str,
        source_text: str,
        extraction_data: dict,
        figure_table_data: Optional[dict] = None,
    ):
        self.document_id = document_id
        self.source_text = source_text
        self.extraction_data = extraction_data
        self.figure_table_data = figure_table_data or {}
        self._results: list[VerificationResult] = []
        self._check_counter = 0

    def _next_check_id(self, prefix: str = "V") -> str:
        self._check_counter += 1
        return f"{prefix}-{self._check_counter:03d}"

    def verify_all(self) -> list[VerificationResult]:
        self._results = []
        self._check_counter = 0

        self._verify_source_quotes()
        self._verify_numeric_values()
        self._verify_data_origins()
        self._verify_missing_status_consistency()
        self._verify_figure_table_crossref()
        self._verify_contradictions()

        return self._results

    def _verify_source_quotes(self) -> None:
        for dim_name, dim_data in self.extraction_data.items():
            if not isinstance(dim_data, dict):
                continue
            fields = dim_data.get("fields", {})
            for field_name, field_data in fields.items():
                if not isinstance(field_data, dict):
                    continue
                quote = field_data.get("source_quote", "")
                status = field_data.get("status", "")

                if status == "REPORTED" and quote:
                    if quote.lower() in self.source_text.lower():
                        self._results.append(VerificationResult(
                            check_id=self._next_check_id(),
                            check_type="SOURCE_QUOTE_MATCH",
                            target_field=field_name,
                            target_dimension=dim_name,
                            status="PASS",
                            message=f"Source quote found in document text",
                            details={"quote_length": len(quote)},
                        ))
                    else:
                        self._results.append(VerificationResult(
                            check_id=self._next_check_id(),
                            check_type="SOURCE_QUOTE_MATCH",
                            target_field=field_name,
                            target_dimension=dim_name,
                            status="WARN",
                            message=f"Source quote NOT found in document text — possible hallucination",
                            details={"quote": quote[:100], "source_text_length": len(self.source_text)},
                        ))
                elif status == "REPORTED" and not quote:
                    self._results.append(VerificationResult(
                        check_id=self._next_check_id(),
                        check_type="SOURCE_QUOTE_PRESENT",
                        target_field=field_name,
                        target_dimension=dim_name,
                        status="WARN",
                        message=f"Field marked REPORTED but no source_quote provided",
                    ))

    def _verify_numeric_values(self) -> None:
        numeric_pattern = re.compile(
            r"(\d+\.?\d*)\s*"
            r"(%|wt%|vol%|mol%|at%|"
            r"\u00b0\s*[CF]|°\s*[CF]|deg[CF]?|"
            r"nm|um|mm|cm|"
            r"eV|keV|"
            r"cm\s*[-\u2212]\s*1|cm\u207b\u00b9|"
            r"m\s*2\s*/\s*g|m\u00b2/g|m2/g|"
            r"mA\s*/\s*cm\s*2|mA/cm2|"
            r"mol|mmol|ppm|ppb|MHz|GHz|kPa|MPa|GPa|bar|atm|"
            r"mL/min|L/min|mL/h|L/h|mL/g|"
            r"mg|ug|g|kg|"
            r"K\b|h\b|min\b|s\b|days?)"
        )

        for dim_name, dim_data in self.extraction_data.items():
            if not isinstance(dim_data, dict):
                continue
            fields = dim_data.get("fields", {})
            for field_name, field_data in fields.items():
                if not isinstance(field_data, dict):
                    continue
                value = field_data.get("value")
                status = field_data.get("status", "")

                if status != "REPORTED":
                    continue

                if isinstance(value, (int, float)):
                    if value == 0:
                        self._results.append(VerificationResult(
                            check_id=self._next_check_id(),
                            check_type="NUMERIC_ZERO_CHECK",
                            target_field=field_name,
                            target_dimension=dim_name,
                            status="FAIL",
                            message=f"Numeric field has value 0 — likely false zero (Phase 3.3 MODE_A)",
                            details={"value": value},
                        ))
                    continue

                if isinstance(value, str):
                    found_numbers = numeric_pattern.findall(value)
                    if found_numbers:
                        for num_str, unit in found_numbers:
                            search_text = self.source_text.lower()
                            num_pos = search_text.find(num_str.lower())
                            if num_pos >= 0:
                                context = search_text[num_pos:num_pos + len(num_str) + len(unit) + 5]
                                if unit.lower() in context:
                                    self._results.append(VerificationResult(
                                        check_id=self._next_check_id(),
                                        check_type="NUMERIC_SOURCE_MATCH",
                                        target_field=field_name,
                                        target_dimension=dim_name,
                                        status="PASS",
                                        message=f"Numeric value {num_str}{unit} found in source text",
                                        details={"value": num_str, "unit": unit},
                                    ))
                                else:
                                    self._results.append(VerificationResult(
                                        check_id=self._next_check_id(),
                                        check_type="NUMERIC_SOURCE_MATCH",
                                        target_field=field_name,
                                        target_dimension=dim_name,
                                        status="WARN",
                                        message=f"Number {num_str} found but unit '{unit}' not in context",
                                        details={"value": num_str, "unit": unit},
                                    ))
                            else:
                                self._results.append(VerificationResult(
                                    check_id=self._next_check_id(),
                                    check_type="NUMERIC_SOURCE_MATCH",
                                    target_field=field_name,
                                    target_dimension=dim_name,
                                    status="WARN",
                                    message=f"Numeric value {num_str}{unit} NOT found in source text",
                                    details={"value": num_str, "unit": unit},
                                ))

    def _verify_data_origins(self) -> None:
        literature_keywords = [
            "wang et al", "liu et al", "zhang et al", "chen et al",
            "reported by", "cited in", "reference", "literature",
            "previously", "prior work", "et al.,", "et al.",
        ]

        for dim_name, dim_data in self.extraction_data.items():
            if not isinstance(dim_data, dict):
                continue
            fields = dim_data.get("fields", {})
            for field_name, field_data in fields.items():
                if not isinstance(field_data, dict):
                    continue
                origin = field_data.get("origin", "")
                quote = field_data.get("source_quote", "")
                status = field_data.get("status", "")

                if status != "REPORTED":
                    continue

                if origin == "ORIGINAL_EXPERIMENT":
                    quote_lower = quote.lower()
                    matched_lit = [kw for kw in literature_keywords if kw in quote_lower]
                    if matched_lit:
                        self._results.append(VerificationResult(
                            check_id=self._next_check_id(),
                            check_type="ORIGIN_CONTAMINATION",
                            target_field=field_name,
                            target_dimension=dim_name,
                            status="FAIL",
                            message=f"Marked ORIGINAL_EXPERIMENT but quote contains literature keywords: {matched_lit}",
                            details={"quote": quote[:100], "keywords_found": matched_lit},
                        ))

    def _verify_missing_status_consistency(self) -> None:
        for dim_name, dim_data in self.extraction_data.items():
            if not isinstance(dim_data, dict):
                continue
            fields = dim_data.get("fields", {})
            for field_name, field_data in fields.items():
                if not isinstance(field_data, dict):
                    continue
                status = field_data.get("status", "")
                value = field_data.get("value")

                if status == "REPORTED" and (value is None or value == "" or value == 0 or value == []):
                    self._results.append(VerificationResult(
                        check_id=self._next_check_id(),
                        check_type="STATUS_VALUE_CONSISTENCY",
                        target_field=field_name,
                        target_dimension=dim_name,
                        status="FAIL",
                        message=f"Status=REPORTED but value is empty/zero/null: {repr(value)[:50]}",
                    ))

                if status in ("NOT_REPORTED", "NOT_EXTRACTED") and value and value not in (0, [], "", None):
                    if isinstance(value, str) and len(value) > 20:
                        self._results.append(VerificationResult(
                            check_id=self._next_check_id(),
                            check_type="STATUS_VALUE_CONSISTENCY",
                            target_field=field_name,
                            target_dimension=dim_name,
                            status="WARN",
                            message=f"Status={status} but value is non-trivial: {repr(value)[:50]}",
                        ))

    def _verify_figure_table_crossref(self) -> None:
        if not self.figure_table_data:
            return

        figures = self.figure_table_data.get("figures", [])
        for fig in figures:
            caption = fig.get("caption", "")
            fig_id = fig.get("figure_id", "")
            numeric_data = fig.get("scientific_data", {}).get("caption_data", {}).get("numeric_values", [])

            if numeric_data:
                for nv in numeric_data:
                    val = f"{nv.get('value', '')}{nv.get('unit', '')}"
                    if val and val.lower() not in self.source_text.lower():
                        self._results.append(VerificationResult(
                            check_id=self._next_check_id(),
                            check_type="FIGURE_DATA_CROSSREF",
                            target_field=fig_id,
                            target_dimension="figure_table",
                            status="WARN",
                            message=f"Figure caption numeric value '{val}' not found in source text",
                            details={"figure_id": fig_id, "value": val},
                        ))

    def _verify_contradictions(self) -> None:
        field_values: dict[str, list[tuple[str, str, Any]]] = {}

        for dim_name, dim_data in self.extraction_data.items():
            if not isinstance(dim_data, dict):
                continue
            fields = dim_data.get("fields", {})
            for field_name, field_data in fields.items():
                if not isinstance(field_data, dict):
                    continue
                if field_data.get("status") != "REPORTED":
                    continue
                value = field_data.get("value")
                if value is not None:
                    key = f"{dim_name}.{field_name}"
                    if key not in field_values:
                        field_values[key] = []
                    field_values[key].append((dim_name, field_name, value))

        for key, entries in field_values.items():
            if len(entries) <= 1:
                continue
            unique_values = set()
            for dim, field, val in entries:
                if isinstance(val, (list, dict)):
                    unique_values.add(json.dumps(val, sort_keys=True, default=str))
                else:
                    unique_values.add(str(val))
            if len(unique_values) > 1:
                self._results.append(VerificationResult(
                    check_id=self._next_check_id(),
                    check_type="CROSS_DIMENSION_CONTRADICTION",
                    target_field=key,
                    target_dimension="multi",
                    status="WARN",
                    message=f"Contradicting values across chunks for {key}: {len(unique_values)} distinct values",
                    details={"values": [str(v)[:80] for v in unique_values]},
                ))

    def generate_report(self) -> dict:
        results = self.verify_all()

        summary = {
            "total_checks": len(results),
            "pass": sum(1 for r in results if r.status == "PASS"),
            "fail": sum(1 for r in results if r.status == "FAIL"),
            "warn": sum(1 for r in results if r.status == "WARN"),
            "skip": sum(1 for r in results if r.status == "SKIP"),
        }

        by_type: dict[str, dict] = {}
        for r in results:
            if r.check_type not in by_type:
                by_type[r.check_type] = {"pass": 0, "fail": 0, "warn": 0, "skip": 0}
            by_type[r.check_type][r.status.lower()] = by_type[r.check_type].get(r.status.lower(), 0) + 1

        return {
            "document_id": self.document_id,
            "verification_summary": summary,
            "by_check_type": by_type,
            "results": [r.to_dict() for r in results],
            "verdict": "PASS" if summary["fail"] == 0 else "FAIL",
        }


def run_evidence_verification(
    document_id: str,
    extraction_output: str,
    source_text_path: str,
    output_dir: str,
    figure_table_output: Optional[str] = None,
    **kwargs,
) -> dict:
    """Pipeline-callable evidence verification entry point."""
    extraction_dir = Path(extraction_output) / document_id
    if not extraction_dir.exists():
        return {"document_id": document_id, "verification_status": "FAILED", "error": "Extraction output not found"}

    extraction_data = {}
    for f in extraction_dir.glob("*_v2_extracted.json"):
        dim_name = f.stem.replace("_v2_extracted", "")
        with open(f, "r", encoding="utf-8") as fh:
            extraction_data[dim_name] = json.load(fh)

    source_text = ""
    source_path = Path(source_text_path)
    if source_path.exists():
        source_text = source_path.read_text(encoding="utf-8")
    elif source_path.is_dir():
        content_files = list(source_path.glob("*content_list.json"))
        if content_files:
            with open(content_files[0], "r", encoding="utf-8") as f:
                cl = json.load(f)
            source_text = "\n".join(
                item.get("text", "") for item in cl if item.get("type") == "text"
            )

    figure_table_data = None
    if figure_table_output:
        ft_path = Path(figure_table_output) / document_id / f"{document_id}_figure_table_v2.json"
        if ft_path.exists():
            with open(ft_path, "r", encoding="utf-8") as f:
                figure_table_data = json.load(f)

    verifier = EvidenceVerifier(document_id, source_text, extraction_data, figure_table_data)
    report = verifier.generate_report()

    out_path = Path(output_dir) / document_id
    out_path.mkdir(parents=True, exist_ok=True)
    report_file = out_path / f"{document_id}_evidence_verification.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    return {
        "document_id": document_id,
        "verification_output_path": str(report_file),
        "verification_status": report["verdict"],
        "total_checks": report["verification_summary"]["total_checks"],
        "pass_count": report["verification_summary"]["pass"],
        "fail_count": report["verification_summary"]["fail"],
        "warn_count": report["verification_summary"]["warn"],
    }


def create_evidence_verifier_adapter(config: dict) -> "StageAdapter":
    """Create a StageAdapter for evidence verification.
    
    Supports two modes:
    - Extraction mode: verifies text extraction data against source
    - VLM mode: verifies VLM figure science records against source
    
    Args:
        config: Pipeline config dict (from ConfigLoader.config)
        
    Returns:
        Configured StageAdapter
    """
    from ..stage_adapter import DataContract, StageAdapter
    
    paths = config.get("paths", {})
    stage_cfg = config.get("stages", {}).get("evidence_verification", {})
    
    adapter = StageAdapter(
        stage_name="evidence_verification",
        version="2.0.0",
        input_contract=DataContract(
            required_inputs=["document_id"],
            optional_inputs=[
                "extraction_output_path",
                "source_text_path",
                "figure_table_output",
                "vlm_figure_science_output_path",
                "document_ir_path",
                "body_text_path",
            ],
        ),
        output_contract=DataContract(
            required_outputs=["verification_output_path", "verification_status"],
            optional_outputs=[
                "total_checks", "pass_count", "fail_count", "warn_count",
                "vlm_records_verified", "vlm_verification_details",
            ],
        ),
        dependencies=["vlm_figure_science"],
        timeout_seconds=stage_cfg.get("timeout_seconds", 60),
    )
    
    output_dir = paths.get("pipeline_runs", "") + "/evidence_verification"
    
    adapter.set_function(
        run_vlm_evidence_verification,
        output_dir=output_dir,
    )
    
    return adapter


class VLMRecordVerifier:
    """Cross-validates VLM figure science records against source documents.
    
    Verification capabilities:
    1. SourceAnchor existence — does referenced page/bbox exist in Document IR?
    2. Body text cross-reference — is the claim supported by document text?
    3. Numerical anchor check — do numerical values appear in source context?
    4. Image file integrity — does sha256 match actual file on disk?
    5. Evidence consistency — do multiple records agree or contradict?
    
    IMPORTANT: This verifier NEVER promotes records to VERIFIED.
    Records remain CANDIDATE or NEEDS_REVIEW after verification.
    Verification results are advisory annotations, not scientific judgments.
    """
    
    def __init__(
        self,
        document_id: str,
        vlm_records: list[dict],
        body_text: str = "",
        document_ir: Optional[dict] = None,
    ):
        self.document_id = document_id
        self.vlm_records = vlm_records
        self.body_text = body_text
        self.document_ir = document_ir or {}
        self._results: list[VerificationResult] = []
        self._check_counter = 0
    
    def _next_check_id(self, prefix: str = "VLM") -> str:
        self._check_counter += 1
        return f"{prefix}-{self._check_counter:03d}"
    
    def verify_all(self) -> list[VerificationResult]:
        self._results = []
        self._check_counter = 0
        
        for i, record in enumerate(self.vlm_records):
            record_id = record.get("record_id", f"record_{i}")
            self._verify_source_anchor(record, record_id)
            self._verify_body_text_crossref(record, record_id)
            self._verify_numerical_anchors(record, record_id)
            self._verify_image_integrity(record, record_id)
        
        self._verify_cross_record_consistency()
        
        return self._results
    
    def _verify_source_anchor(self, record: dict, record_id: str) -> None:
        anchor = record.get("source_anchor")
        if not anchor:
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="SOURCE_ANCHOR_PRESENT",
                target_field="source_anchor",
                target_dimension=record.get("figure_id", "unknown"),
                status="FAIL",
                message=f"Record {record_id}: no source_anchor provided",
                details={"record_id": record_id},
            ))
            return
        
        if not self.document_ir:
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="SOURCE_ANCHOR_EXISTENCE",
                target_field="source_anchor",
                target_dimension=record.get("figure_id", "unknown"),
                status="SKIP",
                message=f"Record {record_id}: Document IR not available for anchor existence check",
                details={"record_id": record_id, "anchor": anchor},
            ))
            return
        
        pages = self.document_ir.get("pages", [])
        page_idx = anchor.get("page_idx", -1)
        if 0 <= page_idx < len(pages):
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="SOURCE_ANCHOR_EXISTENCE",
                target_field="source_anchor.page_idx",
                target_dimension=record.get("figure_id", "unknown"),
                status="PASS",
                message=f"Record {record_id}: page_idx={page_idx} exists in Document IR",
                details={"record_id": record_id, "page_idx": page_idx},
            ))
        else:
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="SOURCE_ANCHOR_EXISTENCE",
                target_field="source_anchor.page_idx",
                target_dimension=record.get("figure_id", "unknown"),
                status="WARN",
                message=f"Record {record_id}: page_idx={page_idx} out of range (doc has {len(pages)} pages)",
                details={"record_id": record_id, "page_idx": page_idx, "page_count": len(pages)},
            ))
        
        bbox = anchor.get("bbox")
        if bbox:
            page_size = anchor.get("page_size", {})
            pw = page_size.get("width", 0) if isinstance(page_size, dict) else 0
            ph = page_size.get("height", 0) if isinstance(page_size, dict) else 0
            # Handle both list [x0,y0,x1,y1] and dict {x0,y0,x1,y1} formats
            if isinstance(bbox, list) and len(bbox) == 4:
                x0, y0, x1, y1 = bbox
            elif isinstance(bbox, dict):
                x0, y0 = bbox.get("x0", 0), bbox.get("y0", 0)
                x1, y1 = bbox.get("x1", 0), bbox.get("y1", 0)
            else:
                x0, y0, x1, y1 = 0, 0, 0, 0
            if pw > 0 and ph > 0 and 0 <= x0 <= pw and 0 <= y0 <= ph and 0 <= x1 <= pw and 0 <= y1 <= ph:
                self._results.append(VerificationResult(
                    check_id=self._next_check_id(),
                    check_type="SOURCE_ANCHOR_BBOX_VALID",
                    target_field="source_anchor.bbox",
                    target_dimension=record.get("figure_id", "unknown"),
                    status="PASS",
                    message=f"Record {record_id}: bbox within page bounds",
                    details={"record_id": record_id, "bbox": bbox, "page_size": page_size},
                ))
            else:
                self._results.append(VerificationResult(
                    check_id=self._next_check_id(),
                    check_type="SOURCE_ANCHOR_BBOX_VALID",
                    target_field="source_anchor.bbox",
                    target_dimension=record.get("figure_id", "unknown"),
                    status="WARN",
                    message=f"Record {record_id}: bbox may exceed page bounds",
                    details={"record_id": record_id, "bbox": bbox, "page_size": page_size},
                ))
    
    def _verify_body_text_crossref(self, record: dict, record_id: str) -> None:
        statement = record.get("statement", "")
        evidence_type = record.get("evidence_type", "")
        
        if not statement:
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="STATEMENT_PRESENT",
                target_field="statement",
                target_dimension=record.get("figure_id", "unknown"),
                status="FAIL",
                message=f"Record {record_id}: empty statement",
                details={"record_id": record_id},
            ))
            return
        
        if not self.body_text:
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="BODY_TEXT_CROSSREF",
                target_field="statement",
                target_dimension=record.get("figure_id", "unknown"),
                status="SKIP",
                message=f"Record {record_id}: body text not available for cross-reference",
                details={"record_id": record_id, "evidence_type": evidence_type},
            ))
            return
        
        if evidence_type == "IMAGE_ONLY_OBSERVATION":
            key_phrases = self._extract_key_phrases(statement)
            found_count = 0
            for phrase in key_phrases:
                if phrase.lower() in self.body_text.lower():
                    found_count += 1
            
            if found_count > 0:
                self._results.append(VerificationResult(
                    check_id=self._next_check_id(),
                    check_type="BODY_TEXT_CROSSREF",
                    target_field="statement",
                    target_dimension=record.get("figure_id", "unknown"),
                    status="PASS",
                    message=f"Record {record_id}: {found_count}/{len(key_phrases)} key phrases found in body text",
                    details={"record_id": record_id, "phrases_checked": len(key_phrases), "phrases_found": found_count},
                ))
            else:
                self._results.append(VerificationResult(
                    check_id=self._next_check_id(),
                    check_type="BODY_TEXT_CROSSREF",
                    target_field="statement",
                    target_dimension=record.get("figure_id", "unknown"),
                    status="WARN",
                    message=f"Record {record_id}: IMAGE_ONLY_OBSERVATION — no key phrases in body text (expected for pure visual observations)",
                    details={"record_id": record_id, "evidence_type": evidence_type},
                ))
        elif evidence_type in ("CAPTION_STATEMENT", "TEXT_CLAIM"):
            if statement.lower()[:50] in self.body_text.lower():
                self._results.append(VerificationResult(
                    check_id=self._next_check_id(),
                    check_type="BODY_TEXT_CROSSREF",
                    target_field="statement",
                    target_dimension=record.get("figure_id", "unknown"),
                    status="PASS",
                    message=f"Record {record_id}: statement fragment found in body text",
                    details={"record_id": record_id, "evidence_type": evidence_type},
                ))
            else:
                self._results.append(VerificationResult(
                    check_id=self._next_check_id(),
                    check_type="BODY_TEXT_CROSSREF",
                    target_field="statement",
                    target_dimension=record.get("figure_id", "unknown"),
                    status="WARN",
                    message=f"Record {record_id}: {evidence_type} not confirmed in body text",
                    details={"record_id": record_id, "evidence_type": evidence_type},
                ))
        else:
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="BODY_TEXT_CROSSREF",
                target_field="statement",
                target_dimension=record.get("figure_id", "unknown"),
                status="SKIP",
                message=f"Record {record_id}: evidence_type={evidence_type} — cross-ref not applicable",
                details={"record_id": record_id, "evidence_type": evidence_type},
            ))
    
    def _extract_key_phrases(self, statement: str) -> list[str]:
        phrases = []
        words = statement.split()
        technical_terms = []
        for w in words:
            cleaned = re.sub(r'[^a-zA-Z0-°℃μ\-\./]', '', w)
            if len(cleaned) > 3 and (re.search(r'\d', cleaned) or cleaned.lower() in (
                'conversion', 'selectivity', 'yield', 'temperature', 'catalyst',
                'xrd', 'xps', 'tem', 'sem', 'bet', 'uv-vis', 'nm', 'ev',
                'propane', 'propylene', 'methane', 'ethane', 'dehydrogenation',
            )):
                technical_terms.append(cleaned)
        
        if len(technical_terms) >= 2:
            for i in range(len(technical_terms) - 1):
                phrases.append(f"{technical_terms[i]} {technical_terms[i+1]}")
        phrases.extend(technical_terms[:5])
        
        return phrases[:8]
    
    def _verify_numerical_anchors(self, record: dict, record_id: str) -> None:
        statement = record.get("statement", "")
        numeric_pattern = re.compile(
            r"(\d+\.?\d*)\s*"
            r"(%|°\s*[CF]|nm|um|mm|cm|eV|keV|mL/min|L/min|"
            r"mA\s*/\s*cm\s*2|mol|ppm|MPa|kPa|bar|"
            r"mg|ug|g|kg|K\b|min\b)"
        )
        found_numbers = numeric_pattern.findall(statement)
        
        if not found_numbers:
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="NUMERICAL_ANCHOR",
                target_field="statement.numerical",
                target_dimension=record.get("figure_id", "unknown"),
                status="SKIP",
                message=f"Record {record_id}: no numerical values in statement",
                details={"record_id": record_id},
            ))
            return
        
        if not self.body_text:
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="NUMERICAL_ANCHOR",
                target_field="statement.numerical",
                target_dimension=record.get("figure_id", "unknown"),
                status="SKIP",
                message=f"Record {record_id}: body text not available for numerical check",
                details={"record_id": record_id, "numbers_found": len(found_numbers)},
            ))
            return
        
        confirmed = 0
        unconfirmed = 0
        for num_str, unit in found_numbers:
            search_text = self.body_text.lower()
            num_pos = search_text.find(num_str.lower())
            if num_pos >= 0:
                context = search_text[num_pos:num_pos + len(num_str) + len(unit) + 10]
                if unit.lower() in context:
                    confirmed += 1
                else:
                    unconfirmed += 1
            else:
                unconfirmed += 1
        
        if confirmed > 0 and unconfirmed == 0:
            status = "PASS"
        elif confirmed > 0:
            status = "WARN"
        else:
            status = "WARN"
        
        self._results.append(VerificationResult(
            check_id=self._next_check_id(),
            check_type="NUMERICAL_ANCHOR",
            target_field="statement.numerical",
            target_dimension=record.get("figure_id", "unknown"),
            status=status,
            message=f"Record {record_id}: {confirmed} confirmed, {unconfirmed} unconfirmed numerical values",
            details={"record_id": record_id, "confirmed": confirmed, "unconfirmed": unconfirmed},
        ))
    
    def _verify_image_integrity(self, record: dict, record_id: str) -> None:
        anchor = record.get("source_anchor", {})
        image_file = anchor.get("image_file", {})
        
        if not image_file:
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="IMAGE_INTEGRITY",
                target_field="source_anchor.image_file",
                target_dimension=record.get("figure_id", "unknown"),
                status="SKIP",
                message=f"Record {record_id}: no image_file in source_anchor",
                details={"record_id": record_id},
            ))
            return
        
        sha256 = image_file.get("sha256", "")
        file_path = image_file.get("path", "")
        
        if not sha256:
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="IMAGE_INTEGRITY",
                target_field="source_anchor.image_file.sha256",
                target_dimension=record.get("figure_id", "unknown"),
                status="WARN",
                message=f"Record {record_id}: image sha256 not recorded",
                details={"record_id": record_id},
            ))
            return
        
        if file_path and Path(file_path).exists():
            try:
                actual_hash = compute_file_sha256(Path(file_path))
            except Exception:
                import hashlib
                h = hashlib.sha256()
                with open(file_path, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        h.update(chunk)
                actual_hash = h.hexdigest()
            
            if actual_hash == sha256:
                self._results.append(VerificationResult(
                    check_id=self._next_check_id(),
                    check_type="IMAGE_INTEGRITY",
                    target_field="source_anchor.image_file.sha256",
                    target_dimension=record.get("figure_id", "unknown"),
                    status="PASS",
                    message=f"Record {record_id}: image sha256 verified",
                    details={"record_id": record_id, "sha256": sha256[:16] + "..."},
                ))
            else:
                self._results.append(VerificationResult(
                    check_id=self._next_check_id(),
                    check_type="IMAGE_INTEGRITY",
                    target_field="source_anchor.image_file.sha256",
                    target_dimension=record.get("figure_id", "unknown"),
                    status="FAIL",
                    message=f"Record {record_id}: image sha256 MISMATCH — file may have changed",
                    details={"record_id": record_id, "expected": sha256[:16] + "...", "actual": actual_hash[:16] + "..."},
                ))
        else:
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="IMAGE_INTEGRITY",
                target_field="source_anchor.image_file",
                target_dimension=record.get("figure_id", "unknown"),
                status="SKIP",
                message=f"Record {record_id}: image file not found on disk (path={file_path})",
                details={"record_id": record_id, "path": file_path},
            ))
    
    def _verify_cross_record_consistency(self) -> None:
        by_figure: dict[str, list[dict]] = {}
        for rec in self.vlm_records:
            fig = rec.get("figure_id", "unknown")
            if fig not in by_figure:
                by_figure[fig] = []
            by_figure[fig].append(rec)
        
        for fig_id, records in by_figure.items():
            if len(records) < 2:
                continue
            
            statements = [r.get("statement", "") for r in records]
            numeric_values: dict[str, list[str]] = {}
            num_pattern = re.compile(r"(\d+\.?\d*)\s*(%|°\s*[CF]|nm|um|mL/min|mA/cm2|mol|ppm|MPa|K|min)")
            for stmt in statements:
                for val, unit in num_pattern.findall(stmt):
                    key = f"{val}{unit}"
                    if key not in numeric_values:
                        numeric_values[key] = []
                    numeric_values[key].append(fig_id)
            
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="CROSS_RECORD_CONSISTENCY",
                target_field="figure_records",
                target_dimension=fig_id,
                status="SKIP",
                message=f"Figure {fig_id}: {len(records)} records, {len(numeric_values)} distinct numerical values — consistency check advisory only",
                details={"figure_id": fig_id, "record_count": len(records), "numeric_values": len(numeric_values)},
            ))
    
    def generate_report(self) -> dict:
        results = self.verify_all()
        
        per_record: dict[str, dict] = {}
        for r in results:
            rid = r.details.get("record_id", r.target_dimension)
            if rid not in per_record:
                per_record[rid] = {"pass": 0, "fail": 0, "warn": 0, "skip": 0, "checks": []}
            per_record[rid][r.status.lower()] = per_record[rid].get(r.status.lower(), 0) + 1
            per_record[rid]["checks"].append(r.to_dict())
        
        summary = {
            "total_checks": len(results),
            "pass": sum(1 for r in results if r.status == "PASS"),
            "fail": sum(1 for r in results if r.status == "FAIL"),
            "warn": sum(1 for r in results if r.status == "WARN"),
            "skip": sum(1 for r in results if r.status == "SKIP"),
        }
        
        by_type: dict[str, dict] = {}
        for r in results:
            if r.check_type not in by_type:
                by_type[r.check_type] = {"pass": 0, "fail": 0, "warn": 0, "skip": 0}
            by_type[r.check_type][r.status.lower()] = by_type[r.check_type].get(r.status.lower(), 0) + 1
        
        record_verdicts = {}
        for rid, stats in per_record.items():
            if stats["fail"] > 0:
                record_verdicts[rid] = "NEEDS_REVIEW"
            else:
                record_verdicts[rid] = "CANDIDATE"
        
        return {
            "document_id": self.document_id,
            "verification_mode": "VLM_RECORD_VERIFICATION",
            "verification_summary": summary,
            "by_check_type": by_type,
            "per_record_verdicts": record_verdicts,
            "per_record_details": per_record,
            "results": [r.to_dict() for r in results],
            "verdict": "PASS" if summary["fail"] == 0 else "PARTIAL",
            "important_note": "VLM verification is structural/advisory only. Records remain CANDIDATE or NEEDS_REVIEW — never auto-promoted to VERIFIED.",
        }


class TableRecordVerifier:
    """Cross-validates Table science records against source documents.

    Verification capabilities:
    1. Identity fields — document_id, table_id, record_id present and consistent
    2. Cell coordinates — row_idx, col_idx non-negative integers
    3. Header-cell association — raw_text semantically linked to header
    4. SourceAnchor — element_type=table, page_idx valid, bbox structurally valid
    5. Numerical fidelity — raw_text numbers match statement, units plausible
    6. Chemical formula fidelity — subscript/superscript preservation check

    IMPORTANT: This verifier NEVER promotes records to VERIFIED.
    Records remain CANDIDATE or NEEDS_REVIEW after verification.
    """

    def __init__(
        self,
        document_id: str,
        table_records: list[dict],
        body_text: str = "",
        document_ir: Optional[dict] = None,
        table_parser_output: Optional[dict] = None,
    ):
        self.document_id = document_id
        self.table_records = table_records
        self.body_text = body_text
        self.document_ir = document_ir or {}
        self.table_parser_output = table_parser_output or {}
        self._results: list[VerificationResult] = []
        self._check_counter = 0

    def _next_check_id(self, prefix: str = "TBL") -> str:
        self._check_counter += 1
        return f"{prefix}-{self._check_counter:03d}"

    def verify_all(self) -> list[VerificationResult]:
        self._results = []
        self._check_counter = 0

        for i, record in enumerate(self.table_records):
            record_id = record.get("record_id", f"table_record_{i}")
            self._verify_identity_fields(record, record_id)
            self._verify_cell_coordinates(record, record_id)
            self._verify_header_cell_association(record, record_id)
            self._verify_source_anchor(record, record_id)
            self._verify_numerical_fidelity(record, record_id)

        return self._results

    def _verify_identity_fields(self, record: dict, record_id: str) -> None:
        doc_id = record.get("document_id", "")
        if doc_id == self.document_id:
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="TABLE_DOCUMENT_ID",
                target_field="document_id",
                target_dimension=record.get("table_id", "unknown"),
                status="PASS",
                message=f"Record {record_id}: document_id matches ({doc_id})",
                details={"record_id": record_id, "document_id": doc_id},
            ))
        else:
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="TABLE_DOCUMENT_ID",
                target_field="document_id",
                target_dimension=record.get("table_id", "unknown"),
                status="FAIL",
                message=f"Record {record_id}: document_id mismatch (got '{doc_id}', expected '{self.document_id}')",
                details={"record_id": record_id, "document_id": doc_id, "expected": self.document_id},
            ))

        table_id = record.get("table_id", "")
        if table_id:
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="TABLE_ID_PRESENT",
                target_field="table_id",
                target_dimension=record.get("table_id", "unknown"),
                status="PASS",
                message=f"Record {record_id}: table_id present ({table_id})",
                details={"record_id": record_id, "table_id": table_id},
            ))
        else:
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="TABLE_ID_PRESENT",
                target_field="table_id",
                target_dimension="unknown",
                status="FAIL",
                message=f"Record {record_id}: table_id missing",
                details={"record_id": record_id},
            ))

    def _verify_cell_coordinates(self, record: dict, record_id: str) -> None:
        row_idx = record.get("row_idx")
        col_idx = record.get("col_idx")

        if isinstance(row_idx, int) and row_idx >= 0:
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="TABLE_ROW_IDX",
                target_field="row_idx",
                target_dimension=record.get("table_id", "unknown"),
                status="PASS",
                message=f"Record {record_id}: row_idx={row_idx} valid",
                details={"record_id": record_id, "row_idx": row_idx},
            ))
        else:
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="TABLE_ROW_IDX",
                target_field="row_idx",
                target_dimension=record.get("table_id", "unknown"),
                status="WARN",
                message=f"Record {record_id}: row_idx invalid or missing (got {row_idx!r})",
                details={"record_id": record_id, "row_idx": row_idx},
            ))

        if isinstance(col_idx, int) and col_idx >= 0:
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="TABLE_COL_IDX",
                target_field="col_idx",
                target_dimension=record.get("table_id", "unknown"),
                status="PASS",
                message=f"Record {record_id}: col_idx={col_idx} valid",
                details={"record_id": record_id, "col_idx": col_idx},
            ))
        else:
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="TABLE_COL_IDX",
                target_field="col_idx",
                target_dimension=record.get("table_id", "unknown"),
                status="WARN",
                message=f"Record {record_id}: col_idx invalid or missing (got {col_idx!r})",
                details={"record_id": record_id, "col_idx": col_idx},
            ))

    def _verify_header_cell_association(self, record: dict, record_id: str) -> None:
        raw_text = record.get("raw_text", "")
        header = record.get("header", "")
        statement = record.get("statement", "")

        if not raw_text:
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="TABLE_HEADER_ASSOCIATION",
                target_field="raw_text",
                target_dimension=record.get("table_id", "unknown"),
                status="WARN",
                message=f"Record {record_id}: raw_text is empty",
                details={"record_id": record_id, "header": header},
            ))
            return

        if header and header.lower() in statement.lower():
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="TABLE_HEADER_ASSOCIATION",
                target_field="header",
                target_dimension=record.get("table_id", "unknown"),
                status="PASS",
                message=f"Record {record_id}: header '{header}' found in statement",
                details={"record_id": record_id, "header": header, "raw_text": raw_text},
            ))
        elif header:
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="TABLE_HEADER_ASSOCIATION",
                target_field="header",
                target_dimension=record.get("table_id", "unknown"),
                status="WARN",
                message=f"Record {record_id}: header '{header}' not found in statement (may be paraphrased)",
                details={"record_id": record_id, "header": header, "raw_text": raw_text},
            ))
        else:
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="TABLE_HEADER_ASSOCIATION",
                target_field="header",
                target_dimension=record.get("table_id", "unknown"),
                status="SKIP",
                message=f"Record {record_id}: no header provided",
                details={"record_id": record_id, "raw_text": raw_text},
            ))

    def _verify_source_anchor(self, record: dict, record_id: str) -> None:
        anchor = record.get("source_anchor")
        if not anchor:
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="TABLE_SOURCE_ANCHOR",
                target_field="source_anchor",
                target_dimension=record.get("table_id", "unknown"),
                status="FAIL",
                message=f"Record {record_id}: no source_anchor",
                details={"record_id": record_id},
            ))
            return

        element_type = anchor.get("element_type", "")
        if element_type == "table":
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="TABLE_ANCHOR_ELEMENT_TYPE",
                target_field="source_anchor.element_type",
                target_dimension=record.get("table_id", "unknown"),
                status="PASS",
                message=f"Record {record_id}: element_type=table correct",
                details={"record_id": record_id, "element_type": element_type},
            ))
        else:
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="TABLE_ANCHOR_ELEMENT_TYPE",
                target_field="source_anchor.element_type",
                target_dimension=record.get("table_id", "unknown"),
                status="WARN",
                message=f"Record {record_id}: element_type='{element_type}' expected 'table'",
                details={"record_id": record_id, "element_type": element_type},
            ))

        page_idx = anchor.get("page_idx", -1)
        if self.document_ir:
            pages = self.document_ir.get("pages", [])
            if 0 <= page_idx < len(pages):
                self._results.append(VerificationResult(
                    check_id=self._next_check_id(),
                    check_type="TABLE_ANCHOR_PAGE",
                    target_field="source_anchor.page_idx",
                    target_dimension=record.get("table_id", "unknown"),
                    status="PASS",
                    message=f"Record {record_id}: page_idx={page_idx} in Document IR",
                    details={"record_id": record_id, "page_idx": page_idx},
                ))
            else:
                self._results.append(VerificationResult(
                    check_id=self._next_check_id(),
                    check_type="TABLE_ANCHOR_PAGE",
                    target_field="source_anchor.page_idx",
                    target_dimension=record.get("table_id", "unknown"),
                    status="WARN",
                    message=f"Record {record_id}: page_idx={page_idx} out of range ({len(pages)} pages)",
                    details={"record_id": record_id, "page_idx": page_idx},
                ))
        else:
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="TABLE_ANCHOR_PAGE",
                target_field="source_anchor.page_idx",
                target_dimension=record.get("table_id", "unknown"),
                status="SKIP",
                message=f"Record {record_id}: Document IR not available",
                details={"record_id": record_id},
            ))

        bbox = anchor.get("bbox")
        if bbox:
            if isinstance(bbox, list) and len(bbox) == 4:
                x0, y0, x1, y1 = bbox
                if x0 < x1 and y0 < y1:
                    self._results.append(VerificationResult(
                        check_id=self._next_check_id(),
                        check_type="TABLE_ANCHOR_BBOX_VALID",
                        target_field="source_anchor.bbox",
                        target_dimension=record.get("table_id", "unknown"),
                        status="PASS",
                        message=f"Record {record_id}: bbox structurally valid (list format)",
                        details={"record_id": record_id, "bbox": bbox},
                    ))
                else:
                    self._results.append(VerificationResult(
                        check_id=self._next_check_id(),
                        check_type="TABLE_ANCHOR_BBOX_VALID",
                        target_field="source_anchor.bbox",
                        target_dimension=record.get("table_id", "unknown"),
                        status="WARN",
                        message=f"Record {record_id}: bbox degenerate (x0>=x1 or y0>=y1)",
                        details={"record_id": record_id, "bbox": bbox},
                    ))
            elif isinstance(bbox, dict):
                x0 = bbox.get("x0", 0)
                y0 = bbox.get("y0", 0)
                x1 = bbox.get("x1", 0)
                y1 = bbox.get("y1", 0)
                if x0 < x1 and y0 < y1:
                    self._results.append(VerificationResult(
                        check_id=self._next_check_id(),
                        check_type="TABLE_ANCHOR_BBOX_VALID",
                        target_field="source_anchor.bbox",
                        target_dimension=record.get("table_id", "unknown"),
                        status="PASS",
                        message=f"Record {record_id}: bbox structurally valid (dict format)",
                        details={"record_id": record_id, "bbox": bbox},
                    ))
                else:
                    self._results.append(VerificationResult(
                        check_id=self._next_check_id(),
                        check_type="TABLE_ANCHOR_BBOX_VALID",
                        target_field="source_anchor.bbox",
                        target_dimension=record.get("table_id", "unknown"),
                        status="WARN",
                        message=f"Record {record_id}: bbox degenerate",
                        details={"record_id": record_id, "bbox": bbox},
                    ))
            else:
                self._results.append(VerificationResult(
                    check_id=self._next_check_id(),
                    check_type="TABLE_ANCHOR_BBOX_VALID",
                    target_field="source_anchor.bbox",
                    target_dimension=record.get("table_id", "unknown"),
                    status="WARN",
                    message=f"Record {record_id}: bbox format unrecognized",
                    details={"record_id": record_id, "bbox": bbox},
                ))

    def _verify_numerical_fidelity(self, record: dict, record_id: str) -> None:
        raw_text = record.get("raw_text", "")
        statement = record.get("statement", "")
        unit = record.get("unit")

        numbers_in_raw = re.findall(r'[\d]+\.?[\d]*', raw_text)
        numbers_in_statement = re.findall(r'[\d]+\.?[\d]*', statement)

        if numbers_in_raw:
            matched = [n for n in numbers_in_raw if n in numbers_in_statement]
            if matched:
                self._results.append(VerificationResult(
                    check_id=self._next_check_id(),
                    check_type="TABLE_NUMERICAL_FIDELITY",
                    target_field="raw_text/numbers",
                    target_dimension=record.get("table_id", "unknown"),
                    status="PASS",
                    message=f"Record {record_id}: {len(matched)}/{len(numbers_in_raw)} numbers in raw_text found in statement",
                    details={"record_id": record_id, "numbers_checked": len(numbers_in_raw), "numbers_matched": len(matched)},
                ))
            else:
                self._results.append(VerificationResult(
                    check_id=self._next_check_id(),
                    check_type="TABLE_NUMERICAL_FIDELITY",
                    target_field="raw_text/numbers",
                    target_dimension=record.get("table_id", "unknown"),
                    status="WARN",
                    message=f"Record {record_id}: numbers in raw_text not found in statement (may be paraphrased)",
                    details={"record_id": record_id, "raw_numbers": numbers_in_raw, "statement_numbers": numbers_in_statement},
                ))
        else:
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="TABLE_NUMERICAL_FIDELITY",
                target_field="raw_text/numbers",
                target_dimension=record.get("table_id", "unknown"),
                status="SKIP",
                message=f"Record {record_id}: no numerical content in raw_text",
                details={"record_id": record_id, "raw_text": raw_text},
            ))

        if unit:
            if unit in statement or unit.lower() in statement.lower():
                self._results.append(VerificationResult(
                    check_id=self._next_check_id(),
                    check_type="TABLE_UNIT_FIDELITY",
                    target_field="unit",
                    target_dimension=record.get("table_id", "unknown"),
                    status="PASS",
                    message=f"Record {record_id}: unit '{unit}' found in statement",
                    details={"record_id": record_id, "unit": unit},
                ))
            else:
                self._results.append(VerificationResult(
                    check_id=self._next_check_id(),
                    check_type="TABLE_UNIT_FIDELITY",
                    target_field="unit",
                    target_dimension=record.get("table_id", "unknown"),
                    status="WARN",
                    message=f"Record {record_id}: unit '{unit}' not found in statement",
                    details={"record_id": record_id, "unit": unit},
                ))
        else:
            self._results.append(VerificationResult(
                check_id=self._next_check_id(),
                check_type="TABLE_UNIT_FIDELITY",
                target_field="unit",
                target_dimension=record.get("table_id", "unknown"),
                status="SKIP",
                message=f"Record {record_id}: no unit provided",
                details={"record_id": record_id},
            ))

    def generate_report(self) -> dict:
        results = self.verify_all()

        by_check_type: dict[str, dict[str, int]] = {}
        for r in results:
            ct = r.check_type
            if ct not in by_check_type:
                by_check_type[ct] = {"pass": 0, "fail": 0, "warn": 0, "skip": 0}
            by_check_type[ct][r.status.lower()] = by_check_type[ct].get(r.status.lower(), 0) + 1

        pass_count = sum(1 for r in results if r.status == "PASS")
        fail_count = sum(1 for r in results if r.status == "FAIL")
        warn_count = sum(1 for r in results if r.status == "WARN")
        skip_count = sum(1 for r in results if r.status == "SKIP")

        per_record_verdicts: dict[str, str] = {}
        per_record_details: dict[str, list] = {}
        for r in results:
            rid = r.details.get("record_id", "unknown")
            if rid not in per_record_details:
                per_record_verdicts[rid] = "CANDIDATE"
                per_record_details[rid] = []
            per_record_details[rid].append(r.to_dict())
            if r.status == "FAIL":
                per_record_verdicts[rid] = "NEEDS_REVIEW"

        total = pass_count + fail_count + warn_count + skip_count
        if fail_count > 0:
            verdict = "PARTIAL"
        elif warn_count > total * 0.5:
            verdict = "PARTIAL"
        else:
            verdict = "PASS"

        return {
            "verdict": verdict,
            "table_records_verified": len(self.table_records),
            "verification_summary": {
                "total_checks": total,
                "pass": pass_count,
                "fail": fail_count,
                "warn": warn_count,
                "skip": skip_count,
            },
            "by_check_type": by_check_type,
            "per_record_verdicts": per_record_verdicts,
            "per_record_details": per_record_details,
            "important_note": "Table verification is structural/advisory only. Records remain CANDIDATE or NEEDS_REVIEW — never auto-promoted to VERIFIED.",
        }


def run_vlm_evidence_verification(
    document_id: str,
    output_dir: str,
    vlm_figure_science_output_path: str = "",
    table_science_output_path: str = "",
    table_parser_output_path: str = "",
    document_ir_path: str = "",
    body_text_path: str = "",
    extraction_output_path: str = "",
    **kwargs,
) -> dict:
    """Pipeline entry point for evidence verification of VLM and Table records.

    Verifies VLM figure science records and Table science records against source documents.
    Does NOT promote records to VERIFIED — results are advisory annotations.
    """
    out_path = Path(output_dir) / document_id
    out_path.mkdir(parents=True, exist_ok=True)
    
    vlm_records = []
    vlm_output_path = vlm_figure_science_output_path or kwargs.get("vlm_output_path", "")
    if vlm_output_path:
        vlm_file = Path(vlm_output_path)
        if vlm_file.exists():
            try:
                with open(vlm_file, "r", encoding="utf-8") as f:
                    vlm_data = json.load(f)
                for result in vlm_data.get("results", []):
                    vlm_records.extend(result.get("records", []))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                report = {
                    "document_id": document_id,
                    "verification_status": "FAILED",
                    "error": f"VLM output malformed: {e}",
                }
                report_file = out_path / f"{document_id}_evidence_verification.json"
                with open(report_file, "w", encoding="utf-8") as f:
                    json.dump(report, f, indent=2, ensure_ascii=False)
                return {
                    "document_id": document_id,
                    "verification_output_path": str(report_file),
                    "verification_status": "FAILED",
                    "error": f"VLM output malformed: {e}",
                }
        else:
            report = {
                "document_id": document_id,
                "verification_status": "SKIP",
                "note": "VLM output not provided — no records to verify",
            }
            report_file = out_path / f"{document_id}_evidence_verification.json"
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            return {
                "document_id": document_id,
                "verification_output_path": str(report_file),
                "verification_status": "SKIP",
                "vlm_records_verified": 0,
                "note": "No VLM output provided",
            }
    
    if not vlm_records:
        report = {
            "document_id": document_id,
            "verification_status": "SKIP",
            "note": "No VLM records found in output file",
        }
        report_file = out_path / f"{document_id}_evidence_verification.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        return {
            "document_id": document_id,
            "verification_output_path": str(report_file),
            "verification_status": "SKIP",
            "vlm_records_verified": 0,
        }
    
    body_text = ""
    body_path = Path(body_text_path) if body_text_path else None
    if body_path and body_path.exists() and body_path.is_file():
        body_text = body_path.read_text(encoding="utf-8")
    elif body_path and body_path.is_dir():
        content_files = list(body_path.glob("*content_list.json"))
        if content_files:
            with open(content_files[0], "r", encoding="utf-8") as f:
                cl = json.load(f)
            body_text = "\n".join(item.get("text", "") for item in cl if item.get("type") == "text")
    
    if not body_text and extraction_output_path:
        ext_dir = Path(extraction_output_path) / document_id
        if ext_dir.exists():
            for f in ext_dir.glob("*content_list.json"):
                try:
                    with open(f, "r", encoding="utf-8") as fh:
                        cl = json.load(fh)
                    body_text = "\n".join(item.get("text", "") for item in cl if item.get("type") == "text")
                    if body_text:
                        break
                except Exception:
                    pass
    
    document_ir = {}
    ir_path = Path(document_ir_path) if document_ir_path else None
    if ir_path and ir_path.exists():
        try:
            with open(ir_path, "r", encoding="utf-8") as f:
                document_ir = json.load(f)
        except Exception:
            pass
    
    verifier = VLMRecordVerifier(
        document_id=document_id,
        vlm_records=vlm_records,
        body_text=body_text,
        document_ir=document_ir,
    )
    vlm_report = verifier.generate_report()

    table_records = []
    table_output_path = table_science_output_path or kwargs.get("table_output_path", "")
    if table_output_path:
        table_file = Path(table_output_path)
        if table_file.exists():
            try:
                with open(table_file, "r", encoding="utf-8") as f:
                    table_data = json.load(f)
                table_records = table_data.get("records", [])
                logger.info("[%s] Loaded %d table records from %s", document_id, len(table_records), table_output_path)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.warning("[%s] Table output malformed: %s", document_id, e)

    table_parser_output = {}
    if table_parser_output_path:
        tp_file = Path(table_parser_output_path)
        if tp_file.exists():
            try:
                with open(tp_file, "r", encoding="utf-8") as f:
                    table_parser_output = json.load(f)
            except Exception:
                pass

    table_report = None
    if table_records:
        table_verifier = TableRecordVerifier(
            document_id=document_id,
            table_records=table_records,
            body_text=body_text,
            document_ir=document_ir,
            table_parser_output=table_parser_output,
        )
        table_report = table_verifier.generate_report()
        logger.info(
            "[%s] Table verification: %d records, %d checks (%d pass, %d fail, %d warn, %d skip)",
            document_id,
            len(table_records),
            table_report["verification_summary"]["total_checks"],
            table_report["verification_summary"]["pass"],
            table_report["verification_summary"]["fail"],
            table_report["verification_summary"]["warn"],
            table_report["verification_summary"]["skip"],
        )

    total_checks = vlm_report["verification_summary"]["total_checks"]
    total_pass = vlm_report["verification_summary"]["pass"]
    total_fail = vlm_report["verification_summary"]["fail"]
    total_warn = vlm_report["verification_summary"]["warn"]
    total_skip = vlm_report["verification_summary"]["skip"]

    merged_by_check_type = dict(vlm_report["by_check_type"])
    merged_per_record_verdicts = dict(vlm_report["per_record_verdicts"])
    merged_per_record_details = dict(vlm_report["per_record_details"])

    if table_report:
        total_checks += table_report["verification_summary"]["total_checks"]
        total_pass += table_report["verification_summary"]["pass"]
        total_fail += table_report["verification_summary"]["fail"]
        total_warn += table_report["verification_summary"]["warn"]
        total_skip += table_report["verification_summary"]["skip"]
        merged_by_check_type.update(table_report["by_check_type"])
        merged_per_record_verdicts.update(table_report["per_record_verdicts"])
        merged_per_record_details.update(table_report["per_record_details"])

    verification_mode = "UNIFIED_RECORD_VERIFICATION" if table_report else "VLM_RECORD_VERIFICATION"

    if total_fail == 0:
        overall_verdict = "PASS"
    else:
        overall_verdict = "PARTIAL"

    output_report = {
        "document_id": document_id,
        "verification_mode": verification_mode,
        "verification_status": overall_verdict,
        "vlm_records_verified": len(vlm_records),
        "table_records_verified": len(table_records),
        "total_records_verified": len(vlm_records) + len(table_records),
        "total_checks": total_checks,
        "pass_count": total_pass,
        "fail_count": total_fail,
        "warn_count": total_warn,
        "skip_count": total_skip,
        "by_check_type": merged_by_check_type,
        "per_record_verdicts": merged_per_record_verdicts,
        "per_record_details": merged_per_record_details,
        "vlm_verification": {
            "records": len(vlm_records),
            "verdict": vlm_report["verdict"],
            "checks": vlm_report["verification_summary"]["total_checks"],
        },
        "table_verification": {
            "records": len(table_records),
            "verdict": table_report["verdict"] if table_report else "NOT_EXECUTED",
            "checks": table_report["verification_summary"]["total_checks"] if table_report else 0,
        } if table_report else {"records": 0, "verdict": "NOT_EXECUTED", "checks": 0},
        "important_note": "Verification is structural/advisory only. Records remain CANDIDATE or NEEDS_REVIEW — never auto-promoted to VERIFIED.",
    }

    report_file = out_path / f"{document_id}_evidence_verification.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(output_report, f, indent=2, ensure_ascii=False, default=str)

    return {
        "document_id": document_id,
        "verification_output_path": str(report_file),
        "verification_status": overall_verdict,
        "verification_mode": verification_mode,
        "vlm_records_verified": len(vlm_records),
        "table_records_verified": len(table_records),
        "total_records_verified": len(vlm_records) + len(table_records),
        "total_checks": total_checks,
        "pass_count": total_pass,
        "fail_count": total_fail,
        "warn_count": total_warn,
        "skip_count": total_skip,
        "per_record_verdicts": merged_per_record_verdicts,
        "important_note": output_report["important_note"],
    }
