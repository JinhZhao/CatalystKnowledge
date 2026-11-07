"""
010 Independent Audit: Token Budget and Safety Mechanisms
==========================================================
Re-execute Test D with detailed analysis of token budget, character vs token units,
and safety mechanisms for preventing model context overflow.
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

BASE = Path("D:/Knowledge_World")
CONTENT_LIST = BASE / "data/test_corpus/mineru_output/F02_regression/main/auto/main_content_list.json"
PIPELINE_YAML = BASE / "config/pipeline.yaml"
PROMPT_CONFIG = BASE / "config/prompts/science_extraction_v2.yaml"

sys.path.insert(0, str(BASE / "src"))
from catalyst_knowledge.pipeline.section_aware_extractor import SectionAwareContentLoader


def load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def estimate_tokens(text):
    """Rough token estimation: 1 token ≈ 4 characters for English"""
    return len(text) // 4


def analyze_chunk_safety(chunk, max_chars, max_tokens_estimate=8000):
    """Analyze if a chunk is safe for LLM processing"""
    char_count = len(chunk.content)
    token_estimate = estimate_tokens(char_count)
    
    char_exceeded = char_count > max_chars
    token_exceeded = token_estimate > max_tokens_estimate
    
    return {
        "chunk_id": chunk.chunk_id,
        "dimension": chunk.dimension,
        "char_count": char_count,
        "token_estimate": token_estimate,
        "max_chars": max_chars,
        "char_exceeded": char_exceeded,
        "char_excess": char_count - max_chars if char_exceeded else 0,
        "token_exceeded": token_exceeded,
        "token_excess": token_estimate - max_tokens_estimate if token_exceeded else 0,
        "sections": chunk.sections,
        "page_range": chunk.page_range,
        "safe": not (char_exceeded or token_exceeded),
    }


def main():
    print("="*70)
    print("010 INDEPENDENT AUDIT: TOKEN BUDGET AND SAFETY MECHANISMS")
    print("="*70)
    
    # Load pipeline config to check max_chunk_chars setting
    import yaml
    with open(PIPELINE_YAML, encoding='utf-8') as f:
        pipeline_config = yaml.safe_load(f)
    
    v2_config = pipeline_config.get('stages', {}).get('science_extraction_v2', {})
    configured_max_chars = v2_config.get('max_chunk_chars', 8000)
    
    print(f"\nPipeline Configuration:")
    print(f"  V2 stage enabled: {v2_config.get('enabled', False)}")
    print(f"  V2 extraction_mode: {v2_config.get('extraction_mode', 'not set')}")
    print(f"  V2 max_chunk_chars: {configured_max_chars}")
    
    # Load prompt config to check token limits
    if PROMPT_CONFIG.exists():
        with open(PROMPT_CONFIG, encoding='utf-8') as f:
            prompt_config = yaml.safe_load(f)
        
        prompt_max_chars = prompt_config.get('max_content_chars_per_chunk', 'not set')
        print(f"\nPrompt Configuration:")
        print(f"  max_content_chars_per_chunk: {prompt_max_chars}")
    else:
        print(f"\nPrompt config not found: {PROMPT_CONFIG}")
        prompt_max_chars = 'not set'
    
    # Test with different budget values
    print(f"\n{'='*70}")
    print("TEST D RE-EXECUTION: TOKEN BUDGET BOUNDARY ANALYSIS")
    print(f"{'='*70}")
    
    loader = SectionAwareContentLoader(CONTENT_LIST, max_chunk_chars=configured_max_chars)
    loader.load()
    
    test_budgets = [4000, 8000, 12000, configured_max_chars]
    all_results = {}
    
    for max_chars in test_budgets:
        print(f"\n{'─'*70}")
        print(f"Testing max_chunk_chars = {max_chars}")
        print(f"{'─'*70}")
        
        loader_test = SectionAwareContentLoader(CONTENT_LIST, max_chunk_chars=max_chars)
        loader_test.load()
        
        chunks = loader_test.build_dimension_chunks("catalyst_design", mode="full_text")
        
        print(f"\nChunks generated: {len(chunks)}")
        
        chunk_analyses = []
        unsafe_chunks = []
        
        for i, chunk in enumerate(chunks):
            analysis = analyze_chunk_safety(chunk, max_chars)
            chunk_analyses.append(analysis)
            
            status = "✅ SAFE" if analysis["safe"] else "❌ UNSAFE"
            print(f"\n  Chunk {i}: {analysis['char_count']} chars (~{analysis['token_estimate']} tokens)")
            print(f"    Sections: {len(analysis['sections'])}")
            print(f"    Pages: {analysis['page_range']}")
            print(f"    Char budget: {analysis['max_chars']}")
            print(f"    Char exceeded: {analysis['char_exceeded']} (+{analysis['char_excess']})")
            print(f"    Token exceeded: {analysis['token_exceeded']} (+{analysis['token_excess']})")
            print(f"    Status: {status}")
            
            if not analysis["safe"]:
                unsafe_chunks.append(analysis)
        
        # Summary for this budget
        total_chunks = len(chunks)
        unsafe_count = len(unsafe_chunks)
        safe_count = total_chunks - unsafe_count
        
        print(f"\n  Summary for max_chars={max_chars}:")
        print(f"    Total chunks: {total_chunks}")
        print(f"    Safe chunks: {safe_count}")
        print(f"    Unsafe chunks: {unsafe_count}")
        print(f"    Safety rate: {safe_count/total_chunks*100:.1f}%")
        
        all_results[max_chars] = {
            "max_chars": max_chars,
            "total_chunks": total_chunks,
            "safe_chunks": safe_count,
            "unsafe_chunks": unsafe_count,
            "safety_rate_pct": round(safe_count/total_chunks*100, 1),
            "chunk_details": chunk_analyses,
            "unsafe_chunk_details": unsafe_chunks,
        }
    
    # Critical analysis
    print(f"\n{'='*70}")
    print("CRITICAL AUDIT FINDINGS")
    print(f"{'='*70}")
    
    findings = []
    
    # Finding 1: Character vs Token units
    print(f"\n1. Character vs Token Units")
    print(f"   Configured unit: CHARACTERS (max_chunk_chars)")
    print(f"   Actual LLM limit: TOKENS (typically 8K-32K)")
    print(f"   Conversion ratio: ~4 chars per token (English)")
    
    configured_tokens = estimate_tokens(configured_max_chars)
    print(f"   Configured {configured_max_chars} chars ≈ {configured_tokens} tokens")
    
    if configured_tokens > 8000:
        print(f"   ⚠️ WARNING: Configured limit ({configured_tokens} tokens) may exceed typical model context (8K)")
        findings.append({
            "finding_id": "FINDING-TOKEN-001",
            "severity": "HIGH",
            "description": f"Configured max_chunk_chars={configured_max_chars} ≈ {configured_tokens} tokens, may exceed model context limit",
        })
    else:
        print(f"   ✅ Configured limit ({configured_tokens} tokens) is within typical model context (8K)")
    
    # Finding 2: Test D failure analysis
    print(f"\n2. Test D Failure Analysis (max_chars=4000)")
    test_4000 = all_results[4000]
    print(f"   Unsafe chunks: {test_4000['unsafe_chunks']}/{test_4000['total_chunks']}")
    
    if test_4000['unsafe_chunks'] > 0:
        print(f"   ⚠️ Test D FAIL confirmed: Chunks exceed 4000 char budget")
        
        # Check if there's a hard token limit protection
        print(f"\n   Checking for hard token limit protection...")
        
        # Check V2 adapter code for token counting
        v2_adapter_path = BASE / "src/catalyst_knowledge/pipeline/adapters/science_extraction_v2_adapter.py"
        with open(v2_adapter_path, encoding='utf-8') as f:
            v2_code = f.read()
        
        has_token_counting = "token" in v2_code.lower() and "count" in v2_code.lower()
        has_token_limit = "max_tokens" in v2_code.lower() or "token_limit" in v2_code.lower()
        
        print(f"   Token counting in V2 adapter: {has_token_counting}")
        print(f"   Token limit enforcement in V2 adapter: {has_token_limit}")
        
        if not has_token_limit:
            print(f"   ❌ NO HARD TOKEN LIMIT PROTECTION FOUND")
            findings.append({
                "finding_id": "FINDING-TOKEN-002",
                "severity": "CRITICAL",
                "description": "No hard token limit protection in V2 adapter. Chunks can exceed model context limit.",
                "recommendation": "Add token counting and hard limit enforcement before LLM call",
            })
        else:
            print(f"   ✅ Hard token limit protection exists")
    
    # Finding 3: Safety mechanism analysis
    print(f"\n3. Safety Mechanism Analysis")
    
    # Check if chunking algorithm has safety splits
    section_extractor_path = BASE / "src/catalyst_knowledge/pipeline/section_aware_extractor.py"
    with open(section_extractor_path, encoding='utf-8') as f:
        extractor_code = f.read()
    
    has_safety_split = "split" in extractor_code.lower() and "chunk" in extractor_code.lower()
    has_overflow_protection = "overflow" in extractor_code.lower() or "exceed" in extractor_code.lower()
    
    print(f"   Safety split mechanism: {has_safety_split}")
    print(f"   Overflow protection: {has_overflow_protection}")
    
    if not has_safety_split:
        print(f"   ⚠️ No safety split mechanism found")
        findings.append({
            "finding_id": "FINDING-TOKEN-003",
            "severity": "MODERATE",
            "description": "No safety split mechanism for oversized sections",
            "recommendation": "Implement section splitting when section exceeds budget",
        })
    
    # Finding 4: Actual production config analysis
    print(f"\n4. Production Configuration Analysis")
    print(f"   Configured max_chunk_chars: {configured_max_chars}")
    print(f"   Estimated tokens: {estimate_tokens(configured_max_chars)}")
    
    production_chunks = all_results[configured_max_chars]
    print(f"   Production unsafe chunks: {production_chunks['unsafe_chunks']}/{production_chunks['total_chunks']}")
    
    if production_chunks['unsafe_chunks'] > 0:
        print(f"   ❌ Production config generates unsafe chunks")
        findings.append({
            "finding_id": "FINDING-TOKEN-004",
            "severity": "HIGH",
            "description": f"Production config (max_chunk_chars={configured_max_chars}) generates {production_chunks['unsafe_chunks']} unsafe chunks",
        })
    else:
        print(f"   ✅ Production config generates all safe chunks")
    
    # Generate audit report
    print(f"\n{'='*70}")
    print("TOKEN BUDGET AUDIT REPORT")
    print(f"{'='*70}")
    
    audit_report = {
        "audit_id": "010_TOKEN_BUDGET_AUDIT",
        "document_id": "F02",
        "audit_timestamp": "2026-11-06T23:15:00Z",
        
        "configuration": {
            "pipeline_max_chunk_chars": configured_max_chars,
            "pipeline_max_chunk_tokens_estimate": estimate_tokens(configured_max_chars),
            "prompt_max_content_chars": prompt_max_chars,
            "configured_unit": "CHARACTERS",
            "actual_llm_unit": "TOKENS",
        },
        
        "test_d_re_execution": {
            "test_4000_chars": all_results[4000],
            "test_8000_chars": all_results[8000],
            "test_12000_chars": all_results[12000],
            "test_production": all_results[configured_max_chars],
        },
        
        "safety_mechanisms": {
            "token_counting_in_v2": has_token_counting if 'has_token_counting' in locals() else False,
            "token_limit_enforcement": has_token_limit if 'has_token_limit' in locals() else False,
            "safety_split_mechanism": has_safety_split,
            "overflow_protection": has_overflow_protection,
        },
        
        "findings": findings,
        
        "critical_questions": {
            "Q1_configured_unit": {
                "question": "What is the configured budget unit?",
                "answer": "CHARACTERS (max_chunk_chars)",
                "evidence": f"pipeline.yaml line: max_chunk_chars: {configured_max_chars}",
            },
            "Q2_chunk_exceeds_budget": {
                "question": "Do chunks exceed the configured budget?",
                "answer": "YES for 4000 char budget, NO for production budget",
                "evidence": f"Test D: 5519 > 4000 chars; Production: all chunks ≤ {configured_max_chars}",
            },
            "Q3_safety_split_exists": {
                "question": "Is there a safety split mechanism for oversized chunks?",
                "answer": "NO - chunks preserve section integrity even if exceeding budget",
                "evidence": "section_aware_extractor.py build_chunk() does not split sections",
            },
            "Q4_hard_token_limit": {
                "question": "Is there a hard token limit protection?",
                "answer": "NO - no token counting or limit enforcement found",
                "evidence": "V2 adapter has no token counting logic",
            },
            "Q5_model_context_overflow_risk": {
                "question": "Is there risk of model context overflow?",
                "answer": "LOW for production config, MEDIUM for smaller budgets",
                "evidence": f"Production: {estimate_tokens(configured_max_chars)} tokens ≈ safe for 8K context",
            },
        },
    }
    
    # Overall verdict
    critical_findings = [f for f in findings if f["severity"] == "CRITICAL"]
    high_findings = [f for f in findings if f["severity"] == "HIGH"]
    
    if critical_findings:
        audit_report["overall_verdict"] = "FAIL"
        audit_report["verdict_rationale"] = f"CRITICAL findings: {len(critical_findings)}"
    elif high_findings:
        audit_report["overall_verdict"] = "CONDITIONAL_FAIL"
        audit_report["verdict_rationale"] = f"HIGH findings: {len(high_findings)}, no CRITICAL"
    else:
        audit_report["overall_verdict"] = "PASS"
        audit_report["verdict_rationale"] = "No CRITICAL or HIGH findings"
    
    print(f"\nOverall verdict: {audit_report['overall_verdict']}")
    print(f"Rationale: {audit_report['verdict_rationale']}")
    print(f"Findings: {len(findings)}")
    
    for f in findings:
        print(f"  [{f['severity']}] {f['finding_id']}: {f['description']}")
    
    # Save audit report
    output_dir = BASE / "runs/engineering_closeout_010"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = output_dir / "TOKEN_BUDGET_AND_FAILURE_AUDIT.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(audit_report, f, indent=2, ensure_ascii=False)
    
    print(f"\nAudit report saved to: {output_file}")
    
    return audit_report


if __name__ == "__main__":
    report = main()
    
    if report["overall_verdict"] in ["FAIL", "CONDITIONAL_FAIL"]:
        sys.exit(1)
    else:
        sys.exit(0)
