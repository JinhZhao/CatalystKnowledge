"""Verify v3 HTML report content quality."""
import re
from pathlib import Path

html = Path(r"D:\Knowledge_World\runs\real_e2e_gate_014\reports\F02_knowledge_report_v3.html").read_text(encoding="utf-8")

print(f"File size: {len(html):,} chars")

# Check for raw dict/JSON strings (should not appear in v3)
raw_dict_pattern = r"\{'[^']+':"
raw_dicts = re.findall(raw_dict_pattern, html)
print(f"\nRaw dict strings found: {len(raw_dicts)}")
if raw_dicts:
    print("  Examples:", raw_dicts[:3])

# Check overview section
if "Literature Overview" in html:
    print("\n[OK] Overview section present")
    if "Photothermal oxidative dehydrogenation" in html:
        print("[OK] Title displayed")
    if "10.3389/fchem.2024.1439185" in html:
        print("[OK] DOI displayed")
    if "Cu/BN" in html:
        print("[OK] Catalyst system displayed")

# Check dimension sections
print("\n--- Dimension Sections ---")
for dim in ["catalyst_design", "characterization", "performance", "mechanism", "structure_activity", "reliability"]:
    if f'id="dim-{dim}"' in html:
        print(f"[OK] {dim} section present")
    else:
        print(f"[FAIL] {dim} section MISSING")

# Check figure gallery
print("\n--- Figure Gallery ---")
if "Figure Gallery" in html:
    print("[OK] Figure Gallery section present")
img_count = html.count("data:image/jpeg;base64")
print(f"[{'OK' if img_count == 9 else 'FAIL'}] Embedded images: {img_count}/9")
details_count = html.count("<details>")
print(f"[{'OK' if details_count == 9 else 'FAIL'}] Expandable VLM sections: {details_count}/9")
vlm_count = html.count("vlm-record") - 1  # minus CSS definition
print(f"[{'OK' if vlm_count == 141 else 'WARN'}] VLM records displayed: {vlm_count}/141")

# Check table explorer
print("\n--- Table Explorer ---")
if "Table Explorer" in html:
    print("[OK] Table Explorer section present")
if "row data not extracted" in html or "No table data" in html:
    print("[OK] Honest about missing table data")
else:
    print("[WARN] May not be honest about missing data")

# Check QA section
print("\n--- QA Verification ---")
if "QA Verification" in html:
    print("[OK] QA section present")
if "Total Checks" in html:
    print("[OK] QA summary displayed")
if "PASS" in html and "FAIL" in html:
    print("[OK] Status badges present")

# Check knowledge objects
print("\n--- Knowledge Objects ---")
if "Knowledge Objects" in html:
    print("[OK] Knowledge Objects section present")
if "Relationships" in html:
    print("[OK] Relationships displayed")

# Check evidence section
print("\n--- Evidence & Provenance ---")
if "Evidence" in html and "Provenance" in html:
    print("[OK] Evidence section present")
if "ORIGINAL_EXPERIMENT" in html:
    print("[OK] Origin badges present")
if "DERIVED" in html:
    print("[OK] Provenance distribution displayed")

# Check sidebar navigation
print("\n--- Navigation ---")
if "sidebar" in html:
    print("[OK] Sidebar present")
nav_links = ["#overview", "#dimensions", "#figures", "#tables", "#qa", "#knowledge", "#evidence"]
for link in nav_links:
    if link in html:
        print(f"[OK] Nav link: {link}")

# Check styling
print("\n--- Styling ---")
if "background: white" in html or "background:white" in html:
    print("[OK] White background")
if "border-radius" in html:
    print("[OK] Rounded corners")
if "box-shadow" in html:
    print("[OK] Card shadows")

print("\n=== VERIFICATION COMPLETE ===")
