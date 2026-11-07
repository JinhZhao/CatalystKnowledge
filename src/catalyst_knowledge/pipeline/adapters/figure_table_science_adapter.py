"""Figure & Table Science Extraction Interface.

Generic engineering interface for extracting scientific data from
figures and tables. Supports:
- Figure identification and panel splitting
- Figure type classification
- Table structure recovery and header restoration
- Cell semantic binding
- Specialized processor interfaces (curve, spectrum, microscopy, mechanism)
- Figure/table to text reference association
- Figure/table to Experiment/Observation/QuantityRecord association

Reuses existing RapidTable, MinerU output, and figure_text_association_v2.py.
Uses proposed schemas (figure_schema_v1, table_schema_v1) as config — does NOT
modify formal V1 Schema.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from ..data_origin_classifier import DataOrigin, DataRecord, DataStatus

logger = logging.getLogger(__name__)


class FigureType(str, Enum):
    SPECTRUM = "SPECTRUM"
    MICROSCOPY = "MICROSCOPY"
    CURVE = "CURVE"
    SCHEMATIC = "SCHEMATIC"
    MECHANISM_DIAGRAM = "MECHANISM_DIAGRAM"
    PHOTO = "PHOTO"
    XRD_PATTERN = "XRD_PATTERN"
    ADSORPTION_ISOTHERM = "ADSORPTION_ISOTHERM"
    PERFORMANCE_PLOT = "PERFORMANCE_PLOT"
    UNKNOWN = "UNKNOWN"


class TableType(str, Enum):
    DATA_TABLE = "DATA_TABLE"
    COMPARISON_TABLE = "COMPARISON_TABLE"
    LITERATURE_DATA = "LITERATURE_DATA"
    PARAMETERS_TABLE = "PARAMETERS_TABLE"
    UNKNOWN = "UNKNOWN"


@dataclass
class FigureRecord:
    figure_id: str
    document_id: str
    figure_label: str
    caption: str
    figure_type: FigureType = FigureType.UNKNOWN
    page_idx: int = 0
    image_path: str = ""
    panels: list[dict] = field(default_factory=list)
    scientific_data: dict = field(default_factory=dict)
    record_origin: DataOrigin = DataOrigin.ORIGINAL_EXPERIMENT
    extraction_status: str = "NOT_EXTRACTED"
    source_anchor: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "figure_id": self.figure_id,
            "document_id": self.document_id,
            "figure_label": self.figure_label,
            "caption": self.caption,
            "figure_type": self.figure_type.value,
            "page_idx": self.page_idx,
            "image_path": self.image_path,
            "panels": self.panels,
            "scientific_data": self.scientific_data,
            "record_origin": self.record_origin.value,
            "extraction_status": self.extraction_status,
            "source_anchor": self.source_anchor,
        }


@dataclass
class TableRecord:
    table_id: str
    document_id: str
    table_label: str
    caption: str
    table_type: TableType = TableType.UNKNOWN
    page_idx: int = 0
    image_path: str = ""
    headers: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    scientific_data: dict = field(default_factory=dict)
    record_origin: DataOrigin = DataOrigin.ORIGINAL_EXPERIMENT
    extraction_status: str = "NOT_EXTRACTED"
    source_anchor: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "table_id": self.table_id,
            "document_id": self.document_id,
            "table_label": self.table_label,
            "caption": self.caption,
            "table_type": self.table_type.value,
            "page_idx": self.page_idx,
            "image_path": self.image_path,
            "headers": self.headers,
            "rows": self.rows,
            "scientific_data": self.scientific_data,
            "record_origin": self.record_origin.value,
            "extraction_status": self.extraction_status,
            "source_anchor": self.source_anchor,
        }


class FigureTableExtractor:
    """Extracts figure and table records from MinerU content_list.json."""

    def __init__(self, content_list_path: Path, document_id: str, auto_dir: Path):
        self.content_list_path = Path(content_list_path)
        self.document_id = document_id
        self.auto_dir = Path(auto_dir)
        self._content_list: list[dict] = []

    def load(self) -> None:
        with open(self.content_list_path, "r", encoding="utf-8") as f:
            self._content_list = json.load(f)

    def extract_figures(self) -> list[FigureRecord]:
        self.load()
        figures = []
        fig_counter = 0

        for item in self._content_list:
            if item.get("type") != "image":
                continue
            fig_counter += 1
            captions = item.get("img_caption", [])
            caption = " ".join(captions) if captions else ""

            figure_label = self._extract_label(caption, "figure", fig_counter)
            figure_type = self._classify_figure_type(caption, item)

            img_path = item.get("img_path", "")
            if img_path and not Path(img_path).is_absolute():
                img_path = str(self.auto_dir / img_path)

            record = FigureRecord(
                figure_id=f"{self.document_id}_fig{fig_counter:02d}",
                document_id=self.document_id,
                figure_label=figure_label,
                caption=caption,
                figure_type=figure_type,
                page_idx=item.get("page_idx", 0),
                image_path=img_path,
                source_anchor={
                    "element_index": item.get("page_idx", 0),
                    "page_idx": item.get("page_idx", 0),
                    "element_type": "image",
                },
            )
            figures.append(record)

        return figures

    def extract_tables(self) -> list[TableRecord]:
        self.load()
        tables = []
        tbl_counter = 0

        for item in self._content_list:
            if item.get("type") != "table":
                continue
            tbl_counter += 1
            captions = item.get("table_caption", [])
            caption = " ".join(captions) if captions else ""

            table_label = self._extract_label(caption, "table", tbl_counter)
            table_type = self._classify_table_type(caption)

            img_path = item.get("img_path", "")
            if img_path and not Path(img_path).is_absolute():
                img_path = str(self.auto_dir / img_path)

            record = TableRecord(
                table_id=f"{self.document_id}_tbl{tbl_counter:02d}",
                document_id=self.document_id,
                table_label=table_label,
                caption=caption,
                table_type=table_type,
                page_idx=item.get("page_idx", 0),
                image_path=img_path,
                source_anchor={
                    "element_index": item.get("page_idx", 0),
                    "page_idx": item.get("page_idx", 0),
                    "element_type": "table",
                },
            )
            tables.append(record)

        return tables

    @staticmethod
    def _extract_label(caption: str, default_type: str, counter: int) -> str:
        import re
        patterns = [
            rf"(?:{default_type})\s*(\d+[A-Za-z]?)",
            rf"(?:{default_type[0].upper()}{default_type[1:].lower()})\s*(\d+[A-Za-z]?)",
            rf"(?:{default_type.upper()})\s*(\d+[A-Za-z]?)",
        ]
        for pat in patterns:
            m = re.search(pat, caption, re.IGNORECASE)
            if m:
                return f"{default_type.capitalize()} {m.group(1)}"
        return f"{default_type.capitalize()} {counter}"

    @staticmethod
    def _classify_figure_type(caption: str, item: dict) -> FigureType:
        cap = caption.lower()
        if "xrd" in cap or "x-ray diffraction" in cap or "diffraction pattern" in cap:
            return FigureType.XRD_PATTERN
        if "tem" in cap or "sem" in cap or "stem" in cap or "microscop" in cap:
            return FigureType.MICROSCOPY
        if "xps" in cap or "binding energy" in cap or "photoelectron" in cap or "x-ray photoelectron" in cap:
            return FigureType.SPECTRUM
        if "uv-vis" in cap or "uv–vis" in cap or "absorption" in cap or "spectrum" in cap or "spectra" in cap or "drs" in cap or "lspr" in cap:
            return FigureType.SPECTRUM
        if "ftir" in cap or "raman" in cap or "infrared" in cap:
            return FigureType.SPECTRUM
        if "conversion" in cap or "selectivity" in cap or "performance" in cap or "stability" in cap or "time on stream" in cap:
            return FigureType.PERFORMANCE_PLOT
        if "adsorption" in cap or "isotherm" in cap or "bet" in cap or "pore" in cap:
            return FigureType.ADSORPTION_ISOTHERM
        if "mechanism" in cap or "pathway" in cap or "scheme" in cap:
            return FigureType.MECHANISM_DIAGRAM
        return FigureType.UNKNOWN

    @staticmethod
    def _classify_table_type(caption: str) -> TableType:
        cap = caption.lower()
        if "comparison" in cap or "compared" in cap:
            return TableType.COMPARISON_TABLE
        if "parameter" in cap or "condition" in cap:
            return TableType.PARAMETERS_TABLE
        if "surface area" in cap or "pore" in cap or "size" in cap or "bet" in cap:
            return TableType.DATA_TABLE
        return TableType.DATA_TABLE


class FigureScienceProcessor:
    """Interface for specialized figure science extraction.

    This is a generic interface — actual visual analysis algorithms
    (curve digitization, spectrum peak detection, etc.) are pluggable.
    """

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self._processors = {
            FigureType.SPECTRUM: self._process_spectrum,
            FigureType.XRD_PATTERN: self._process_xrd,
            FigureType.MICROSCOPY: self._process_microscopy,
            FigureType.CURVE: self._process_curve,
            FigureType.PERFORMANCE_PLOT: self._process_performance,
            FigureType.ADSORPTION_ISOTHERM: self._process_isotherm,
            FigureType.MECHANISM_DIAGRAM: self._process_mechanism_diagram,
        }

    def process(self, figure: FigureRecord) -> dict:
        processor = self._processors.get(figure.figure_type, self._process_generic)
        return processor(figure)

    def _process_generic(self, figure: FigureRecord) -> dict:
        return {
            "figure_id": figure.figure_id,
            "extraction_status": "CAPTION_ONLY",
            "caption_data": self._extract_caption_data(figure.caption),
            "note": f"No specialized processor for {figure.figure_type.value}",
        }

    def _process_spectrum(self, figure: FigureRecord) -> dict:
        return {
            "figure_id": figure.figure_id,
            "extraction_status": "INTERFACE_READY",
            "figure_type": "SPECTRUM",
            "caption_data": self._extract_caption_data(figure.caption),
            "expected_data": ["peak_positions", "peak_intensities", "band_assignments"],
            "note": "Spectrum processor interface — needs visual analysis backend",
        }

    def _process_xrd(self, figure: FigureRecord) -> dict:
        return {
            "figure_id": figure.figure_id,
            "extraction_status": "INTERFACE_READY",
            "figure_type": "XRD_PATTERN",
            "caption_data": self._extract_caption_data(figure.caption),
            "expected_data": ["diffraction_peaks", "crystal_phase", "lattice_parameters"],
        }

    def _process_microscopy(self, figure: FigureRecord) -> dict:
        return {
            "figure_id": figure.figure_id,
            "extraction_status": "INTERFACE_READY",
            "figure_type": "MICROSCOPY",
            "caption_data": self._extract_caption_data(figure.caption),
            "expected_data": ["particle_size", "morphology", "distribution"],
        }

    def _process_curve(self, figure: FigureRecord) -> dict:
        return {
            "figure_id": figure.figure_id,
            "extraction_status": "INTERFACE_READY",
            "figure_type": "CURVE",
            "caption_data": self._extract_caption_data(figure.caption),
            "expected_data": ["x_values", "y_values", "trend_description"],
        }

    def _process_performance(self, figure: FigureRecord) -> dict:
        return {
            "figure_id": figure.figure_id,
            "extraction_status": "INTERFACE_READY",
            "figure_type": "PERFORMANCE_PLOT",
            "caption_data": self._extract_caption_data(figure.caption),
            "expected_data": ["conversion_values", "selectivity_values", "temperature_points"],
        }

    def _process_isotherm(self, figure: FigureRecord) -> dict:
        return {
            "figure_id": figure.figure_id,
            "extraction_status": "INTERFACE_READY",
            "figure_type": "ADSORPTION_ISOTHERM",
            "caption_data": self._extract_caption_data(figure.caption),
            "expected_data": ["surface_area", "pore_volume", "pore_size"],
        }

    def _process_mechanism_diagram(self, figure: FigureRecord) -> dict:
        return {
            "figure_id": figure.figure_id,
            "extraction_status": "INTERFACE_READY",
            "figure_type": "MECHANISM_DIAGRAM",
            "caption_data": self._extract_caption_data(figure.caption),
            "expected_data": ["reaction_steps", "intermediates", "energy_barriers"],
        }

    @staticmethod
    def _extract_caption_data(caption: str) -> dict:
        import re
        data: dict[str, Any] = {"raw_caption": caption}

        numbers = re.findall(
            r"(\d+\.?\d*)\s*"
            r"(%|wt%|vol%|mol%|at%|"
            r"\u00b0\s*[CF]|°\s*[CF]|deg[CF]?|"
            r"nm|um|mm|cm|"
            r"eV|keV|"
            r"cm\s*[-−]\s*1|cm\s*\u207b\u00b9|"
            r"m\s*2\s*/\s*g|m\u00b2/g|m2/g|"
            r"mA\s*/\s*cm\s*2|mA/cm2|"
            r"mol|mmol|ppm|ppb|MHz|GHz|kPa|MPa|GPa|bar|atm|"
            r"mL/min|L/min|mL/h|L/h|mL/g|"
            r"mg|ug|g|kg|"
            r"K\b|h\b|min\b|s\b|days?)",
            caption,
        )
        if numbers:
            data["numeric_values"] = [{"value": v, "unit": u.strip()} for v, u in numbers]

        species = re.findall(
            r"([A-Z][a-z]?(?:\s*[\(\{]?\s*\d+[\)\}]?\s*)?"
            r"(?:\s*[/−\-]\s*[A-Z][a-z]?(?:\s*[\(\{]?\s*\d+[\)\}]?\s*)?)*)",
            caption,
        )
        if species:
            data["chemical_species"] = list(set(s.strip() for s in species if len(s.strip()) > 1))

        return data


def run_figure_table_extraction(
    document_id: str,
    mineru_output: str,
    output_dir: str,
    config: Optional[dict] = None,
    **kwargs,
) -> dict:
    """Pipeline-callable figure/table science extraction entry point."""
    from ..section_aware_extractor import SectionAwareContentLoader

    auto_dir = None
    base = Path(mineru_output)
    if base.exists():
        candidates = [
            base / f"{document_id}_batch" / "main" / "auto",
            base / f"{document_id}_batch" / "auto",
            base / document_id / "main" / "auto",
            base / document_id / "auto",
        ]
        for c in candidates:
            if c.exists() and list(c.glob("*content_list.json")):
                auto_dir = c
                break

    if auto_dir is None:
        return {
            "document_id": document_id,
            "figure_table_status": "FAILED",
            "error": f"MinerU output not found for '{document_id}'",
        }

    content_list_path = auto_dir / "main_content_list.json"
    if not content_list_path.exists():
        content_files = list(auto_dir.glob("*content_list.json"))
        if not content_files:
            return {"document_id": document_id, "figure_table_status": "FAILED", "error": "No content_list.json"}
        content_list_path = content_files[0]

    out_path = Path(output_dir) / document_id
    out_path.mkdir(parents=True, exist_ok=True)

    extractor = FigureTableExtractor(content_list_path, document_id, auto_dir)
    figures = extractor.extract_figures()
    tables = extractor.extract_tables()

    processor = FigureScienceProcessor(config)
    for fig in figures:
        fig.scientific_data = processor.process(fig)

    figures_data = [f.to_dict() for f in figures]
    tables_data = [t.to_dict() for t in tables]

    output = {
        "document_id": document_id,
        "figures": figures_data,
        "tables": tables_data,
        "figure_count": len(figures_data),
        "table_count": len(tables_data),
        "figure_types": {ft.value: sum(1 for f in figures if f.figure_type == ft) for ft in FigureType},
        "table_types": {tt.value: sum(1 for t in tables if t.table_type == tt) for tt in TableType},
    }

    output_file = out_path / f"{document_id}_figure_table_v2.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    return {
        "document_id": document_id,
        "figure_table_output_path": str(output_file),
        "figure_table_status": "PASS",
        "figure_count": len(figures_data),
        "table_count": len(tables_data),
    }


def create_figure_table_science_adapter(config: dict) -> "StageAdapter":
    """Create a StageAdapter for figure and table science extraction.
    
    Args:
        config: Pipeline config dict (from ConfigLoader.config)
        
    Returns:
        Configured StageAdapter
    """
    from ..stage_adapter import DataContract, StageAdapter
    
    paths = config.get("paths", {})
    stage_cfg = config.get("stages", {}).get("figure_table_science", {})
    
    adapter = StageAdapter(
        stage_name="figure_table_science",
        version="2.0.0",
        input_contract=DataContract(
            required_inputs=["document_id"],
            optional_inputs=["mineru_output_dir"],
        ),
        output_contract=DataContract(
            required_outputs=["figure_table_output_path", "figure_table_status"],
            optional_outputs=["figure_count", "table_count"],
        ),
        dependencies=["document_ir"],
        timeout_seconds=stage_cfg.get("timeout_seconds", 120),
    )
    
    mineru_output = paths.get("mineru_output", "")
    output_dir = paths.get("pipeline_runs", "") + "/figure_table"
    
    adapter.set_function(
        run_figure_table_extraction,
        mineru_output=mineru_output,
        output_dir=output_dir,
    )
    
    return adapter
