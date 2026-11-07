"""TargetedExtractor — Re-extract failed fields with LLM.

Features:
- Conservative output (UNRESOLVED for uncertain data)
- Schema validation
- Source anchoring
- Confidence thresholding
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from .recovery_planner import RecoveryAction, RecoveryStrategy

logger = logging.getLogger(__name__)


@dataclass
class ExtractedField:
    """Result of targeted extraction."""
    field_path: str
    value: Any
    unit: Optional[str]
    status: str  # REPORTED, NOT_REPORTED, UNRESOLVED
    confidence: float
    source_anchor: dict
    source_quote: Optional[str]
    extraction_method: str
    timestamp: str
    validation_passed: bool = True
    validation_message: Optional[str] = None


class TargetedExtractor:
    """Re-extract failed fields using LLM with conservative output."""

    def __init__(self, llm_client: Optional[Any] = None):
        """Initialize with optional LLM client."""
        self.llm_client = llm_client
        self._extraction_count = 0

    def extract(
        self,
        action: RecoveryAction,
        document_text: str,
        prompt: Optional[str] = None,
    ) -> ExtractedField:
        """Execute targeted extraction for a single action.

        Args:
            action: Recovery action specification
            document_text: Full document text or context window
            prompt: Optional custom prompt (otherwise use template)

        Returns:
            ExtractedField with conservative output
        """
        self._extraction_count += 1

        # Extract context window
        context = self._extract_context(document_text, action.context_window)

        # Generate prompt if not provided
        if prompt is None:
            prompt = self._generate_prompt(action, context)

        # Call LLM
        if self.llm_client is None:
            # Return UNRESOLVED if no LLM client
            return self._create_unresolved(action, "LLM client not available")

        try:
            response = self._call_llm(prompt, action.model_config)
            parsed = self._parse_response(response, action.expected_output_schema)

            # Validate extraction
            validation_passed, validation_msg = self._validate_extraction(parsed, action)

            if not validation_passed:
                return self._create_unresolved(action, validation_msg)

            # Create extracted field
            return ExtractedField(
                field_path=action.target_field,
                value=parsed.get("value"),
                unit=parsed.get("unit"),
                status="REPORTED" if parsed.get("value") else "NOT_REPORTED",
                confidence=parsed.get("confidence", 0.5),
                source_anchor={
                    "document_id": "recovery",
                    "location": f"char_{action.context_window.char_offset_start or 0}",
                    "section": action.context_window.section or "unknown",
                },
                source_quote=parsed.get("quote"),
                extraction_method=f"LLM_{action.model_config.model_name}",
                timestamp=datetime.now().isoformat(),
                validation_passed=True,
                validation_message=None,
            )

        except Exception as e:
            logger.error(f"Extraction failed for {action.target_field}: {e}")
            return self._create_unresolved(action, str(e))

    def _extract_context(self, document_text: str, context_window: Any) -> str:
        """Extract context window from document text."""
        if context_window.char_offset_start is not None and context_window.char_offset_end is not None:
            start = max(0, context_window.char_offset_start - 200)
            end = min(len(document_text), context_window.char_offset_end + 200)
            return document_text[start:end]

        # If no offsets, return full text (or first 2000 chars)
        return document_text[:2000]

    def _generate_prompt(self, action: RecoveryAction, context: str) -> str:
        """Generate extraction prompt."""
        field_name = action.target_field.split(".")[-1]

        prompt_template = f"""Extract the value for "{field_name}" from the following document context.

CONTEXT:
{context}

INSTRUCTIONS:
1. If the value is clearly present, extract it with high confidence.
2. If the value might be present but ambiguous, extract it with low confidence.
3. If the value is NOT present, return status "NOT_REPORTED".
4. Always include the source quote (exact text from context).
5. Include units if present.

OUTPUT FORMAT (JSON):
{{
  "value": <extracted value or null>,
  "unit": <unit if present>,
  "confidence": <0.0 to 1.0>,
  "quote": <exact text from context>,
  "status": "REPORTED" or "NOT_REPORTED"
}}
"""
        return prompt_template

    def _call_llm(self, prompt: str, model_config: Any) -> str:
        """Call LLM with prompt and model config."""
        if self.llm_client is None:
            raise RuntimeError("LLM client not available")

        # Use LLM client to generate response
        response = self.llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            model=model_config.model_name,
            temperature=model_config.temperature,
            max_tokens=model_config.max_tokens,
        )

        return response

    def _parse_response(self, response: str, expected_schema: dict) -> dict:
        """Parse LLM response into structured data."""
        # Try to extract JSON from response
        try:
            # Look for JSON block
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())

            # Try parsing entire response
            return json.loads(response)

        except json.JSONDecodeError:
            # If JSON parsing fails, try to extract value with regex
            value_match = re.search(r'"value":\s*"?([^",}]+)"?', response)
            if value_match:
                return {
                    "value": value_match.group(1).strip(),
                    "unit": None,
                    "confidence": 0.3,
                    "quote": None,
                    "status": "REPORTED",
                }

            # Return empty result
            return {
                "value": None,
                "unit": None,
                "confidence": 0.0,
                "quote": None,
                "status": "NOT_REPORTED",
            }

    def _validate_extraction(self, parsed: dict, action: RecoveryAction) -> tuple[bool, Optional[str]]:
        """Validate extracted data against expected schema."""
        # Check required fields
        if "value" not in parsed:
            return False, "Missing 'value' field in extraction result"

        # Check value type
        expected_type = action.expected_output_schema.get("value_type", "text")
        value = parsed.get("value")

        if expected_type == "numerical" and value is not None:
            try:
                float(str(value).split()[0])
            except ValueError:
                return False, f"Expected numerical value but got: {value}"

        # Check confidence threshold
        confidence = parsed.get("confidence", 0.0)
        if confidence < 0.3:
            return False, f"Confidence too low: {confidence}"

        return True, None

    def _create_unresolved(self, action: RecoveryAction, reason: str) -> ExtractedField:
        """Create UNRESOLVED extraction result."""
        return ExtractedField(
            field_path=action.target_field,
            value=None,
            unit=None,
            status="UNRESOLVED",
            confidence=0.0,
            source_anchor={
                "document_id": "recovery",
                "location": "unresolved",
                "section": action.context_window.section or "unknown",
            },
            source_quote=None,
            extraction_method="UNRESOLVED",
            timestamp=datetime.now().isoformat(),
            validation_passed=False,
            validation_message=reason,
        )
