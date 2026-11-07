"""
NUM-UNIT-001 Phase 2: Rule-based Numerical Extraction

Extracts numerical candidates from Document IR output using regex patterns.
Does not perform semantic binding or unit inference - only pattern matching.

Output: NumericCandidate objects with raw_text, raw_value, raw_unit, etc.
"""

import re
import json
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class NumericCandidate:
    """Represents a numerical candidate extracted from text."""
    raw_text: str  # Original text snippet
    raw_value: str  # Parsed numeric value (string)
    raw_unit: Optional[str]  # Parsed unit (string or None)
    value_type: str  # "integer", "decimal", "scientific", "range", "percentage"
    quantity_type_candidate: Optional[str]  # Suggested quantity type (or None)
    document_id: str  # Source document ID
    element_id: str  # Source element ID (e.g., "main.md:50")
    source_anchor: Dict[str, Any]  # SourceAnchor information
    extraction_status: str  # "SUCCESS", "AMBIGUOUS_UNIT", "PARSE_ERROR"
    confidence: float  # Extraction confidence (0.0-1.0)
    
    # Additional fields for ranges and errors
    range_min: Optional[str] = None
    range_max: Optional[str] = None
    error_value: Optional[str] = None
    error_type: Optional[str] = None  # "±", "+/-", "error", "uncertainty"
    
    # Table-specific fields
    table_cell_ref: Optional[str] = None  # e.g., "Table 1, Row 2, Col 3"
    header_unit: Optional[str] = None  # Unit inherited from table header


class QuantityExtractor:
    """Extracts numerical candidates from Document IR."""
    
    def __init__(self):
        # Unicode normalization mappings
        self.unicode_mappings = {
            '²': '2', '³': '3', '⁻': '-', '⁺': '+',
            'μ': 'u', '°': 'deg', '±': '+/-',
            '×': 'x', '÷': '/'
        }
        
        # Number patterns (improved to avoid matching digits in units)
        self.integer_pattern = r'(?<![a-zA-Z])-?\d{1,3}(?:,\d{3})*(?!\.\d)(?![a-zA-Z]*[²³⁻⁺/])'
        self.decimal_pattern = r'(?<![a-zA-Z])-?\d{1,3}(?:,\d{3})*\.\d+(?![a-zA-Z]*[²³⁻⁺/])'
        self.scientific_pattern = r'(?<![a-zA-Z])-?\d+(?:\.\d+)?[eE][+-]?\d+'
        self.percentage_pattern = r'(?<![a-zA-Z])-?\d+(?:\.\d+)?\s*%'
        
        # Range patterns
        self.range_pattern = r'(-?\d+(?:\.\d+)?)\s*(?:-|to|–|—)\s*(-?\d+(?:\.\d+)?)'
        self.error_pattern = r'(-?\d+(?:\.\d+)?)\s*(?:±|\+/-)\s*(-?\d+(?:\.\d+)?)'
        
        # Unit patterns (improved for compound units)
        self.unit_pattern = r'(?:^|\s)((?:[a-zA-Zμ°]+[²³⁻⁺]?)*(?:/[a-zA-Zμ°]+[²³⁻⁺]?)?(?:\s*[·]\s*[a-zA-Zμ°]+[²³⁻⁺]?)*)'
        
        # Track extracted positions to avoid duplicates
        self._extracted_positions = set()
    
    def normalize_unicode(self, text: str) -> str:
        """Normalize Unicode characters to ASCII equivalents."""
        result = text
        for unicode_char, ascii_char in self.unicode_mappings.items():
            result = result.replace(unicode_char, ascii_char)
        return result
    
    def extract_from_text(self, text: str, document_id: str, element_id: str, 
                         source_anchor: Dict[str, Any]) -> List[NumericCandidate]:
        """Extract numerical candidates from a text string."""
        candidates = []
        self._extracted_positions = set()  # Reset for each text
        
        # Normalize Unicode
        normalized_text = self.normalize_unicode(text)
        
        # Extract ranges with errors first (most specific)
        for match in re.finditer(self.error_pattern, normalized_text):
            if not self._is_position_extracted(match.start(), match.end()):
                candidate = self._parse_error_match(match, text, document_id, element_id, source_anchor)
                if candidate:
                    candidates.append(candidate)
                    self._mark_position_extracted(match.start(), match.end())
        
        # Extract ranges
        for match in re.finditer(self.range_pattern, normalized_text):
            if not self._is_position_extracted(match.start(), match.end()):
                candidate = self._parse_range_match(match, text, document_id, element_id, source_anchor)
                if candidate:
                    candidates.append(candidate)
                    self._mark_position_extracted(match.start(), match.end())
        
        # Extract percentages
        for match in re.finditer(self.percentage_pattern, normalized_text):
            if not self._is_position_extracted(match.start(), match.end()):
                candidate = self._parse_percentage_match(match, text, document_id, element_id, source_anchor)
                if candidate:
                    candidates.append(candidate)
                    self._mark_position_extracted(match.start(), match.end())
        
        # Extract scientific notation
        for match in re.finditer(self.scientific_pattern, normalized_text):
            if not self._is_position_extracted(match.start(), match.end()):
                candidate = self._parse_scientific_match(match, text, document_id, element_id, source_anchor)
                if candidate:
                    candidates.append(candidate)
                    self._mark_position_extracted(match.start(), match.end())
        
        # Extract decimals
        for match in re.finditer(self.decimal_pattern, normalized_text):
            if not self._is_position_extracted(match.start(), match.end()):
                candidate = self._parse_decimal_match(match, text, document_id, element_id, source_anchor)
                if candidate:
                    candidates.append(candidate)
                    self._mark_position_extracted(match.start(), match.end())
        
        # Extract integers (last, to avoid duplicates)
        for match in re.finditer(self.integer_pattern, normalized_text):
            if not self._is_position_extracted(match.start(), match.end()):
                candidate = self._parse_integer_match(match, text, document_id, element_id, source_anchor)
                if candidate:
                    candidates.append(candidate)
                    self._mark_position_extracted(match.start(), match.end())
        
        return candidates
    
    def _is_position_extracted(self, start: int, end: int) -> bool:
        """Check if a position range has already been extracted."""
        for pos in range(start, end):
            if pos in self._extracted_positions:
                return True
        return False
    
    def _mark_position_extracted(self, start: int, end: int):
        """Mark a position range as extracted."""
        for pos in range(start, end):
            self._extracted_positions.add(pos)
    
    def _parse_integer_match(self, match: re.Match, original_text: str, 
                            document_id: str, element_id: str,
                            source_anchor: Dict[str, Any]) -> Optional[NumericCandidate]:
        """Parse an integer match."""
        raw_value = match.group(0).replace(',', '')
        
        # Try to extract unit
        raw_unit = self._extract_unit_after(match, original_text)
        
        # Get context snippet
        start = max(0, match.start() - 20)
        end = min(len(original_text), match.end() + 20)
        raw_text = original_text[start:end]
        
        return NumericCandidate(
            raw_text=raw_text,
            raw_value=raw_value,
            raw_unit=raw_unit,
            value_type="integer",
            quantity_type_candidate=None,
            document_id=document_id,
            element_id=element_id,
            source_anchor=source_anchor,
            extraction_status="SUCCESS",
            confidence=0.9 if raw_unit else 0.7
        )
    
    def _parse_decimal_match(self, match: re.Match, original_text: str,
                            document_id: str, element_id: str,
                            source_anchor: Dict[str, Any]) -> Optional[NumericCandidate]:
        """Parse a decimal match."""
        raw_value = match.group(0).replace(',', '')
        raw_unit = self._extract_unit_after(match, original_text)
        
        start = max(0, match.start() - 20)
        end = min(len(original_text), match.end() + 20)
        raw_text = original_text[start:end]
        
        return NumericCandidate(
            raw_text=raw_text,
            raw_value=raw_value,
            raw_unit=raw_unit,
            value_type="decimal",
            quantity_type_candidate=None,
            document_id=document_id,
            element_id=element_id,
            source_anchor=source_anchor,
            extraction_status="SUCCESS",
            confidence=0.9 if raw_unit else 0.7
        )
    
    def _parse_scientific_match(self, match: re.Match, original_text: str,
                               document_id: str, element_id: str,
                               source_anchor: Dict[str, Any]) -> Optional[NumericCandidate]:
        """Parse a scientific notation match."""
        raw_value = match.group(0)
        raw_unit = self._extract_unit_after(match, original_text)
        
        start = max(0, match.start() - 20)
        end = min(len(original_text), match.end() + 20)
        raw_text = original_text[start:end]
        
        return NumericCandidate(
            raw_text=raw_text,
            raw_value=raw_value,
            raw_unit=raw_unit,
            value_type="scientific",
            quantity_type_candidate=None,
            document_id=document_id,
            element_id=element_id,
            source_anchor=source_anchor,
            extraction_status="SUCCESS",
            confidence=0.95 if raw_unit else 0.8
        )
    
    def _parse_percentage_match(self, match: re.Match, original_text: str,
                               document_id: str, element_id: str,
                               source_anchor: Dict[str, Any]) -> Optional[NumericCandidate]:
        """Parse a percentage match."""
        raw_value = match.group(0).strip()
        
        start = max(0, match.start() - 20)
        end = min(len(original_text), match.end() + 20)
        raw_text = original_text[start:end]
        
        return NumericCandidate(
            raw_text=raw_text,
            raw_value=raw_value,
            raw_unit="%",
            value_type="percentage",
            quantity_type_candidate=None,
            document_id=document_id,
            element_id=element_id,
            source_anchor=source_anchor,
            extraction_status="SUCCESS",
            confidence=0.95
        )
    
    def _parse_range_match(self, match: re.Match, original_text: str,
                          document_id: str, element_id: str,
                          source_anchor: Dict[str, Any]) -> Optional[NumericCandidate]:
        """Parse a range match (e.g., '10-20' or '10 to 20')."""
        range_min = match.group(1)
        range_max = match.group(2)
        raw_unit = self._extract_unit_after(match, original_text)
        
        start = max(0, match.start() - 20)
        end = min(len(original_text), match.end() + 20)
        raw_text = original_text[start:end]
        
        return NumericCandidate(
            raw_text=raw_text,
            raw_value=f"{range_min}-{range_max}",
            raw_unit=raw_unit,
            value_type="range",
            quantity_type_candidate=None,
            document_id=document_id,
            element_id=element_id,
            source_anchor=source_anchor,
            extraction_status="SUCCESS",
            confidence=0.85 if raw_unit else 0.65,
            range_min=range_min,
            range_max=range_max
        )
    
    def _parse_error_match(self, match: re.Match, original_text: str,
                          document_id: str, element_id: str,
                          source_anchor: Dict[str, Any]) -> Optional[NumericCandidate]:
        """Parse an error/uncertainty match (e.g., '10±2' or '10+/-2')."""
        value = match.group(1)
        error = match.group(2)
        raw_unit = self._extract_unit_after(match, original_text)
        
        start = max(0, match.start() - 20)
        end = min(len(original_text), match.end() + 20)
        raw_text = original_text[start:end]
        
        return NumericCandidate(
            raw_text=raw_text,
            raw_value=value,
            raw_unit=raw_unit,
            value_type="decimal",
            quantity_type_candidate=None,
            document_id=document_id,
            element_id=element_id,
            source_anchor=source_anchor,
            extraction_status="SUCCESS",
            confidence=0.9 if raw_unit else 0.7,
            error_value=error,
            error_type="±"
        )
    
    def _extract_unit_after(self, match: re.Match, text: str) -> Optional[str]:
        """Extract unit string after a numeric match."""
        # Look for unit pattern after the match (up to 40 chars)
        after_text = text[match.end():match.end()+40]
        
        # Try to match compound units with slashes and dots
        # Pattern: letters/numbers with optional superscripts, slashes, dots
        unit_patterns = [
            r'\s*([a-zA-Zμ°]+[²³⁻⁺0-9]*(?:/[a-zA-Zμ°]+[²³⁻⁺0-9]*)?(?:\s*[·]\s*[a-zA-Zμ°]+[²³⁻⁺0-9]*)*)',
            r'\s*([a-zA-Zμ°]+[²³⁻⁺0-9]*)',
        ]
        
        for pattern in unit_patterns:
            unit_match = re.match(pattern, after_text)
            if unit_match:
                unit = unit_match.group(1).strip()
                # Filter out common non-unit words
                if unit.lower() in ['the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'is', 'was', 'are', 'were', 'been', 'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them', 'my', 'your', 'his', 'its', 'our', 'their', 'what', 'which', 'who', 'whom', 'whose', 'when', 'where', 'why', 'how', 'not', 'no', 'nor', 'as', 'if', 'then', 'than', 'too', 'very', 'just', 'about', 'above', 'after', 'again', 'all', 'also', 'am', 'an', 'any', 'because', 'before', 'between', 'both', 'during', 'each', 'few', 'further', 'here', 'into', 'more', 'most', 'other', 'out', 'over', 'own', 'same', 'so', 'some', 'such', 'through', 'under', 'until', 'up', 'while']:
                    continue
                # Normalize Unicode in unit
                return self.normalize_unicode(unit)
        
        return None
    
    def extract_from_document(self, document_path: Path, document_id: str) -> List[NumericCandidate]:
        """Extract numerical candidates from a Document IR markdown file."""
        candidates = []
        
        if not document_path.exists():
            return candidates
        
        with open(document_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        current_element_id = None
        current_section = None
        
        for line_num, line in enumerate(lines, 1):
            # Track section/element
            if line.startswith('#'):
                current_section = line.strip()
                current_element_id = f"{document_id}:{line_num}"
            
            # Extract from line
            source_anchor = {
                'document_id': document_id,
                'element_type': 'TEXT',
                'element_id': current_element_id or f"{document_id}:{line_num}",
                'location': current_section or 'main',
                'page': None,
                'block_index': line_num,
                'raw_text': line.strip(),
                'confidence': 1.0
            }
            
            line_candidates = self.extract_from_text(
                line, document_id, 
                current_element_id or f"{document_id}:{line_num}",
                source_anchor
            )
            candidates.extend(line_candidates)
        
        return candidates


def main():
    """Test extraction on sample documents."""
    print("="*60)
    print("NUM-UNIT-001 Phase 2: Rule-based Numerical Extraction")
    print("="*60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    extractor = QuantityExtractor()
    
    # Test with sample text
    test_text = """
    The catalyst has a specific surface area of 1,380 m2/g.
    Propane conversion was 16.8% with selectivity of 82.1%.
    Reaction temperature: 500 °C to 600 °C.
    Time on stream: 1000 h ± 50 h.
    Activation energy: 80.5 kJ/mol.
    Current density: 100 mA/cm2.
    """
    
    candidates = extractor.extract_from_text(
        test_text, 
        document_id="TEST",
        element_id="TEST:1",
        source_anchor={'document_id': 'TEST', 'element_type': 'TEXT', 'element_id': 'TEST:1'}
    )
    
    print(f"\nExtracted {len(candidates)} candidates from test text:")
    for i, cand in enumerate(candidates, 1):
        print(f"\n{i}. {cand.value_type}: {cand.raw_value} {cand.raw_unit or ''}")
        print(f"   Context: ...{cand.raw_text}...")
        print(f"   Confidence: {cand.confidence}")
        if cand.range_min:
            print(f"   Range: {cand.range_min} to {cand.range_max}")
        if cand.error_value:
            print(f"   Error: ±{cand.error_value}")
    
    # Test with real document
    print("\n" + "="*60)
    print("Testing with F02 Document IR")
    print("="*60)
    
    f02_path = Path('data/test_corpus/mineru_output/F02_regression/main/auto/main.md')
    if f02_path.exists():
        f02_candidates = extractor.extract_from_document(f02_path, 'F02')
        print(f"\nExtracted {len(f02_candidates)} candidates from F02")
        
        # Show first 10
        for i, cand in enumerate(f02_candidates[:10], 1):
            print(f"{i}. {cand.value_type}: {cand.raw_value} {cand.raw_unit or ''} (conf={cand.confidence:.2f})")
        
        # Save results
        output_dir = Path('runs')
        output_dir.mkdir(exist_ok=True)
        
        output_file = output_dir / 'NUM_UNIT_001_phase2_F02_candidates.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump([asdict(c) for c in f02_candidates], f, indent=2, ensure_ascii=False)
        
        print(f"\nResults saved: {output_file}")
    else:
        print(f"F02 document not found: {f02_path}")
    
    print("\n" + "="*60)
    print("Phase 2 Extraction Test Complete")
    print("="*60)


if __name__ == '__main__':
    main()
