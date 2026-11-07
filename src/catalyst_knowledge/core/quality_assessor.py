"""Quality Assessor — LLM-based paper quality evaluation for knowledge ingestion.

Evaluates parsed papers across 5 dimensions:
1. completeness      — Are key sections present? (type-dependent)
2. format_quality    — Are sections clearly structured and readable?
3. data_richness     — Does the paper contain quantitative data (TOF, conversion, etc.)?
4. domain_relevance  — Is the paper relevant to catalysis?
5. novelty           — Does the paper contain new/non-duplicate knowledge?

Paper types (type-specific evaluation):
- research     : full article — requires Results, high data_richness weight
- review       : review/mini-review — requires any 2 sections, low data_richness weight
- communication: short communication/letter — relaxed section requirements

Threshold: overall_score >= 0.6 → accept, otherwise reject.
"""

from __future__ import annotations

import re
from catalyst_knowledge.prompts.loader import load_prompt
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class QualityReport:
    """Quality assessment result for a parsed paper."""

    overall_score: float = 0.0
    dimension_scores: dict[str, float] = field(default_factory=dict)
    verdict: str = "reject"  # "accept" | "reject"
    reason: str = ""
    suggestions: str = ""
    paper_type: str = "research"  # "research" | "review" | "communication"


# ---------------------------------------------------------------------------
# Paper type detection (rule-based, fast)
# ---------------------------------------------------------------------------

# Keywords that indicate review / communication papers
# Checked in title + abstract
PAPER_TYPE_KEYWORDS = {
    "review": [
        r"\breview\b", r"\bmini[\-\s]?review\b", r"\boverview\b",
        r"\bsurvey\b", r"\bprogress\b", r"\brecent advances\b",
        r"\bstate[\-\s]of[\-\s]the[\-\s]art\b", r"\btutorial\b",
        r"\bperspective\b", r"\broadmap\b",
    ],
    "communication": [
        r"\bcommunication\b", r"\bletter\b", r"\bshort\s+communication\b",
        r"\bpreliminary\b", r"\brapid\s+communication\b",
        r"\bhighlight\b", r"\bnote\b",
    ],
}

# Required sections per paper type (at least N of these must be present)
TYPE_REQUIRED_SECTIONS = {
    "research":      {"abstract", "result", "conclusion"},   # need 2/3
    "review":        {"abstract"},                            # need 1/1 (relaxed)
    "communication": {"abstract"},                            # need 1/1 (relaxed)
}
TYPE_MIN_REQUIRED = {
    "research": 2,     # need at least 2 of 3 required sections
    "review": 1,       # need at least abstract
    "communication": 1,
}

# Weights per paper type
TYPE_WEIGHTS = {
    "research": {
        "completeness": 0.25,
        "format_quality": 0.20,
        "data_richness": 0.25,   # research papers should have data
        "domain_relevance": 0.20,
        "novelty": 0.10,
    },
    "review": {
        "completeness": 0.20,
        "format_quality": 0.25,  # structure matters more for reviews
        "data_richness": 0.10,   # reviews cite data, not generate it
        "domain_relevance": 0.30,
        "novelty": 0.15,         # review insight/novel perspective
    },
    "communication": {
        "completeness": 0.15,    # short papers have fewer sections
        "format_quality": 0.20,
        "data_richness": 0.30,   # communications are data-dense
        "domain_relevance": 0.25,
        "novelty": 0.10,
    },
}

# Default weights (used when paper type is unknown or for fallback)
DEFAULT_WEIGHTS = TYPE_WEIGHTS["research"]


# ---------------------------------------------------------------------------
# Rule-based pre-checks (fast, no LLM needed)
# ---------------------------------------------------------------------------

DATA_PATTERNS = [
    # --- 百分比类 ---
    r"\d+\.?\d*\s*%",                       # percentages
    # --- 活性指标 ---
    r"TOF\s*[=:]\s*[\d.]+",                 # TOF values
    r"conversion\s*[=:]\s*[\d.]+",          # conversion
    r"selectivity\s*[=:]\s*[\d.]+",         # selectivity
    r"activation energy\s*[=:]\s*[\d.]+",   # Ea
    # --- 反应条件 ---
    r"\d+\s*(?:°C|K|MPa|bar|atm)",          # reaction conditions
    # --- 表征参数 ---
    r"BET\s*(?:surface area)?\s*[=:]\s*\d+",  # surface area
    # --- 电化学 ---
    r"(?:overpotential|η)\s*[=:]\s*[\d.]+\s*(?:mV|V)",  # overpotential
    r"(?:Tafel slope)\s*[=:]\s*[\d.]+\s*(?:mV/dec|mV dec-1)",  # Tafel slope
    r"(?:current density|j)\s*[=:]\s*[\d.]+\s*(?:mA/cm2|A/g)",  # current density
    r"(?:faradaic efficiency|FE)\s*[=:]\s*[\d.]+\s*%",  # faradaic efficiency
    # --- 光催化 ---
    r"(?:AQY|quantum yield)\s*[=:]\s*[\d.]+\s*%",  # quantum yield
    r"(?:band gap|Eg)\s*[=:]\s*[\d.]+\s*eV",  # band gap
    # --- 多相催化 ---
    r"(?:GHSV|WHSV|space velocity)\s*[=:]\s*[\d.]+\s*(?:h-1|h⁻¹)",  # space velocity
    # --- 结构参数 ---
    r"(?:particle size|粒径)\s*[=:]\s*[\d.]+\s*(?:nm|Å)",  # particle size
    r"(?:dispersion|分散度)\s*[=:]\s*[\d.]+\s*%",  # metal dispersion
]


def detect_paper_type(title: str, abstract: str) -> str:
    """Detect paper type from title and abstract keywords.

    Returns: "research" | "review" | "communication"
    """
    text = f"{title} {abstract}".lower()

    # Check review keywords first (more common)
    for pattern in PAPER_TYPE_KEYWORDS["review"]:
        if re.search(pattern, text, re.IGNORECASE):
            return "review"

    # Check communication keywords
    for pattern in PAPER_TYPE_KEYWORDS["communication"]:
        if re.search(pattern, text, re.IGNORECASE):
            return "communication"

    return "research"


def rule_based_pre_check(parsed_paper: dict) -> dict[str, Any]:
    """Fast rule-based pre-check before LLM assessment.

    Returns dict with:
    - paper_type: detected type ("research" | "review" | "communication")
    - section_count: number of detected sections
    - has_required_sections: bool (type-dependent)
    - text_length: total character count
    - data_points_found: number of quantitative data points detected
    """
    full_text = parsed_paper.get("full_text", "")
    sections = parsed_paper.get("sections", [])
    abstract = parsed_paper.get("abstract", "")
    title = parsed_paper.get("title", "")

    # Paper type detection
    paper_type = detect_paper_type(title, abstract)

    # Section detection (type-dependent required sections)
    section_titles = [s.get("title", "").lower() for s in sections]
    required = TYPE_REQUIRED_SECTIONS[paper_type]
    min_required = TYPE_MIN_REQUIRED[paper_type]

    found_required = sum(
        1 for req in required
        if any(req in title for title in section_titles)
    )
    has_required = found_required >= min_required

    # Data point detection
    data_points = 0
    for pattern in DATA_PATTERNS:
        data_points += len(re.findall(pattern, full_text, re.IGNORECASE))

    return {
        "paper_type": paper_type,
        "section_count": len(sections),
        "has_required_sections": has_required,
        "text_length": len(full_text),
        "abstract_length": len(abstract),
        "data_points_found": data_points,
    }


# ---------------------------------------------------------------------------
# LLM-based quality assessment
# ---------------------------------------------------------------------------

QUALITY_SYSTEM_PROMPT = load_prompt("quality-assessor-system-prompt")


def build_quality_prompt(parsed_paper: dict, pre_check: dict) -> str:
    """Build the user prompt for quality assessment."""
    title = parsed_paper.get("title", "Unknown")
    abstract = parsed_paper.get("abstract", "")[:800]
    sections = parsed_paper.get("sections", [])
    paper_type = pre_check.get("paper_type", "research")

    # Build section summary
    section_summary = "\n".join(
        f"- {s.get('title', 'Untitled')}: {len(s.get('content', ''))} chars"
        for s in sections[:10]
    )

    # Extract key snippets (first 300 chars of each major section)
    key_snippets = []
    for s in sections[:5]:
        title_lower = s.get("title", "").lower()
        if any(kw in title_lower for kw in ["result", "discussion", "conclusion", "experimental"]):
            snippet = s.get("content", "")[:400]
            key_snippets.append(f"### {s.get('title', '')}\n{snippet}")

    snippets_text = "\n\n".join(key_snippets) if key_snippets else "(no key sections found)"

    # Type-specific section requirement description
    type_section_desc = {
        "research": "Abstract + Results + Conclusion (need at least 2 of 3)",
        "review": "Abstract + at least 2 organised sections",
        "communication": "Abstract + at least 1 data/results section",
    }

    return f"""Paper Title: {title}

Detected Paper Type (rule-based): {paper_type}
  → Use this as a hint, but override if you disagree based on content.

Abstract (first 800 chars):
{abstract}

Pre-check Results:
- Sections detected: {pre_check['section_count']}
- Required sections for '{paper_type}': {type_section_desc.get(paper_type, type_section_desc['research'])}
- Has required sections: {pre_check['has_required_sections']}
- Total text length: {pre_check['text_length']} chars
- Abstract length: {pre_check['abstract_length']} chars
- Quantitative data points found: {pre_check['data_points_found']}

Section Structure:
{section_summary}

Key Content Snippets:
{snippets_text}

Please assess this paper's quality for knowledge base inclusion.
Remember: apply the weights corresponding to the paper type you identify."""


# ---------------------------------------------------------------------------
# Main quality assessment function
# ---------------------------------------------------------------------------

QUALITY_THRESHOLD = 0.4


def assess_quality(llm_service, parsed_paper: dict) -> QualityReport:
    """Assess the quality of a parsed paper using LLM.

    Args:
        llm_service: LLMService instance for calling the LLM.
        parsed_paper: Dict with keys: title, abstract, sections, full_text, etc.

    Returns:
        QualityReport with scores, verdict, and reasoning.
    """
    # Step 1: Rule-based pre-check (includes paper type detection)
    pre_check = rule_based_pre_check(parsed_paper)
    paper_type = pre_check["paper_type"]
    weights = TYPE_WEIGHTS[paper_type]

    # Quick reject: very short text or no sections at all
    if pre_check["text_length"] < 200:
        return QualityReport(
            overall_score=0.0,
            dimension_scores={k: 0.0 for k in weights},
            verdict="reject",
            reason="Paper text is too short (< 200 chars) — likely a failed PDF extraction.",
            suggestions="Please re-export the PDF or provide a text/markdown version.",
            paper_type=paper_type,
        )

    if pre_check["section_count"] == 0 and not pre_check["abstract_length"]:
        return QualityReport(
            overall_score=0.1,
            dimension_scores={k: 0.1 for k in weights},
            verdict="reject",
            reason="No sections or abstract detected — PDF structure not parseable.",
            suggestions="Try converting the PDF to text first, or provide a structured format.",
            paper_type=paper_type,
        )

    # Step 2: LLM-based assessment
    prompt = build_quality_prompt(parsed_paper, pre_check)

    try:
        result = llm_service.generate_json(QUALITY_SYSTEM_PROMPT, prompt)
    except Exception as e:
        # LLM call failed — fall back to rule-based scoring
        return _fallback_assessment(pre_check, str(e))

    if not result:
        return _fallback_assessment(pre_check, "LLM returned empty response")

    # Step 3: Determine paper type (use LLM's if provided, else rule-based)
    llm_paper_type = result.get("paper_type", paper_type)
    if llm_paper_type in TYPE_WEIGHTS:
        paper_type = llm_paper_type
    weights = TYPE_WEIGHTS[paper_type]

    # Step 4: Build dimension scores
    dimension_scores = {
        dim: float(result.get(dim, 0.5)) for dim in weights
    }

    # Step 5: Calculate weighted overall score using type-specific weights
    overall = sum(dimension_scores[dim] * weights[dim] for dim in weights)

    # Step 6: Determine verdict
    verdict = "accept" if overall >= QUALITY_THRESHOLD else "reject"
    llm_verdict = result.get("verdict", verdict)
    if overall >= QUALITY_THRESHOLD and llm_verdict == "accept":
        verdict = "accept"

    return QualityReport(
        overall_score=round(overall, 3),
        dimension_scores=dimension_scores,
        verdict=verdict,
        reason=result.get("reason", ""),
        suggestions=result.get("suggestions", ""),
        paper_type=paper_type,
    )


def _fallback_assessment(pre_check: dict, error: str) -> QualityReport:
    """Generate a rule-based fallback assessment when LLM is unavailable."""
    paper_type = pre_check.get("paper_type", "research")
    weights = TYPE_WEIGHTS[paper_type]
    scores = {}

    # completeness: based on section count and required sections
    min_required = TYPE_MIN_REQUIRED[paper_type]
    required_sections = TYPE_REQUIRED_SECTIONS[paper_type]
    # Scale: having all required sections = 1.0, having none = 0.0
    section_ratio = min(1.0, pre_check["section_count"] / max(len(required_sections), 1))
    scores["completeness"] = section_ratio * (
        1.0 if pre_check["has_required_sections"] else 0.5
    )

    # format_quality: based on text length and structure
    text_score = min(1.0, pre_check["text_length"] / 5000)
    scores["format_quality"] = text_score

    # data_richness: based on data points found
    scores["data_richness"] = min(1.0, pre_check["data_points_found"] / 10)

    # domain_relevance: default to 0.5 (unknown without LLM)
    scores["domain_relevance"] = 0.5

    # novelty: default to 0.3 (conservative without LLM)
    scores["novelty"] = 0.3

    overall = sum(scores[dim] * weights[dim] for dim in weights)
    verdict = "accept" if overall >= QUALITY_THRESHOLD else "reject"

    return QualityReport(
        overall_score=round(overall, 3),
        dimension_scores=scores,
        verdict=verdict,
        reason=f"Rule-based fallback (LLM unavailable: {error})",
        suggestions="Consider running with LLM enabled for more accurate assessment.",
        paper_type=paper_type,
    )
