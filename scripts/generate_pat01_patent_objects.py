"""Generate PAT01 PatentClaim and PatentExample objects from markdown and table data."""
import json
import re
from pathlib import Path

MINERU_ROOT = Path("data/test_corpus/mineru_output")
STORE_ROOT = Path("data/test_corpus/canonical_store")

md_path = MINERU_ROOT / "PAT01_test/US20100029974A1/auto/US20100029974A1.md"
table_cl_path = MINERU_ROOT / "PAT01_table_test/US20100029974A1/auto/US20100029974A1_content_list.json"
objects_path = STORE_ROOT / "extractions" / "PAT01_g3_objects.json"

with open(md_path, "r", encoding="utf-8") as f:
    md_text = f.read()

with open(table_cl_path, "r", encoding="utf-8") as f:
    table_cl = json.load(f)

with open(objects_path, "r", encoding="utf-8") as f:
    g3_objects = json.load(f)

# --- Extract Patent Claims ---
patent_claims = []
claims_section = re.search(
    r"(?:What is claimed is|Claims)[:\s]*(.*?)(?=\n\n\n|\nDescription|\n\[00|\Z)",
    md_text, re.DOTALL | re.IGNORECASE
)

if claims_section:
    claims_text = claims_section.group(1).strip()
    claim_pattern = re.compile(r"(\d+)\.\s+(.*?)(?=\n\d+\.|\Z)", re.DOTALL)
    for m in claim_pattern.finditer(claims_text):
        claim_num = int(m.group(1))
        claim_text = m.group(2).strip().replace("\n", " ")
        is_independent = claim_num <= 2 or claim_num in (5, 8, 11, 14)
        patent_claims.append({
            "object_id": f"PAT01_patent_claim_{claim_num:03d}",
            "object_type": "PatentClaim",
            "doc_id": "PAT01",
            "claim_number": claim_num,
            "claim_text": claim_text[:500],
            "claim_type": "independent" if is_independent else "dependent",
            "status": "EXTRACTED",
            "source_anchor": {
                "document_id": "PAT01",
                "element_type": "TEXT",
                "element_id": f"PAT01_claim_{claim_num}",
                "confidence": 0.9,
            },
        })

print(f"Extracted {len(patent_claims)} patent claims")

# --- Extract Table Data for Patent Examples ---
table_html = ""
for elem in table_cl:
    if elem.get("type") == "table" and elem.get("table_body"):
        table_html = elem["table_body"]
        break

patent_examples = []
if table_html:
    rows = re.findall(r"<tr>(.*?)</tr>", table_html, re.DOTALL)
    headers = []
    for i, row in enumerate(rows):
        cells = re.findall(r"<td>(.*?)</td>", row, re.DOTALL)
        cells = [c.strip() for c in cells]
        if i == 0:
            headers = cells
            continue
        if len(cells) >= 4:
            example_name = cells[0].strip()
            co_catalyst = cells[1].strip() if len(cells) > 1 else ""
            conversion = cells[2].strip() if len(cells) > 2 else ""
            selectivity = cells[3].strip() if len(cells) > 3 else ""
            yield_val = cells[4].strip() if len(cells) > 4 else ""

            is_comparative = "comparative" in example_name.lower()
            ex_num = re.search(r"(\d+)", example_name)
            ex_id = ex_num.group(1) if ex_num else str(i)

            patent_examples.append({
                "object_id": f"PAT01_patent_example_{ex_id}",
                "object_type": "PatentExample",
                "doc_id": "PAT01",
                "example_name": example_name,
                "example_type": "comparative" if is_comparative else "invention",
                "inorganic_co_catalyst": co_catalyst if co_catalyst else "None",
                "conversion_pct": conversion,
                "selectivity_pct": selectivity,
                "yield_pct": yield_val,
                "status": "EXTRACTED",
                "source_anchor": {
                    "document_id": "PAT01",
                    "element_type": "TABLE",
                    "element_id": "PAT01_p3_b53",
                    "confidence": 0.95,
                    "raw_text": table_html[:200],
                },
            })

print(f"Extracted {len(patent_examples)} patent examples from table")

# --- Update g3_objects ---
objects = g3_objects.get("objects", {})
objects["PatentClaim"] = patent_claims
objects["PatentExample"] = patent_examples

g3_objects["objects"] = objects
g3_objects["statistics"]["patent_claims"] = len(patent_claims)
g3_objects["statistics"]["patent_examples"] = len(patent_examples)
g3_objects["statistics"]["total_objects"] = (
    g3_objects["statistics"].get("total_objects", 0) + len(patent_claims) + len(patent_examples)
)

with open(objects_path, "w", encoding="utf-8") as f:
    json.dump(g3_objects, f, ensure_ascii=False, indent=2)
print(f"[OK] Updated: {objects_path}")
