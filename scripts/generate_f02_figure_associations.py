"""Generate F02 figure associations v2 from MinerU content_list and markdown."""
import json
import re

MINERU_ROOT = "data/test_corpus/mineru_output"
CL_PATH = f"{MINERU_ROOT}/F02_regression/main/auto/main_content_list.json"
MD_PATH = f"{MINERU_ROOT}/F02_regression/main/auto/main.md"
OUT_PATH = f"{MINERU_ROOT}/F02_figure_associations_v2.json"

with open(CL_PATH, "r", encoding="utf-8") as f:
    cl = json.load(f)

with open(MD_PATH, "r", encoding="utf-8") as f:
    md_lines = f.read().split("\n")

associations = []
fig_counter = 0
tbl_counter = 0

for elem_idx, elem in enumerate(cl):
    etype = elem.get("type", "text")
    page = elem.get("page_idx", 0)

    if etype == "image":
        fig_counter += 1
        element_id = f"F02_p{page}_b{elem_idx}"
        target_id = f"p{page}_img{elem_idx}"

        captions = elem.get("img_caption", [])
        footnotes = elem.get("img_footnote", [])
        caption_text = captions[0] if captions else (footnotes[0] if footnotes else "")

        fig_match = re.search(r"FIGURE\s+(\d+)", caption_text, re.IGNORECASE)
        if fig_match:
            fig_num = int(fig_match.group(1))
        else:
            fig_num = fig_counter

        figure_id = f"Figure {fig_num}"
        search_pattern = f"Figure {fig_num}"

        text_ref_found = False
        ref_line = None
        for li, line in enumerate(md_lines):
            if search_pattern in line and not line.strip().startswith("![") and not line.strip().startswith("FIGURE"):
                text_ref_found = True
                ref_line = li + 1
                break

        if text_ref_found:
            assoc = {
                "source_element_id": element_id,
                "target_element_id": target_id,
                "figure_id": figure_id,
                "namespace": "FIGURE",
                "association_type": "explicit_reference",
                "confidence": 0.95,
                "status": "CANDIDATE",
                "evidence": f"Text reference found at markdown line {ref_line}",
                "source_anchor": {
                    "document_id": "F02",
                    "element_type": "TEXT",
                    "element_id": element_id,
                    "page": page,
                    "confidence": 0.95,
                    "location": f"md_line_{ref_line}",
                    "raw_text": md_lines[ref_line - 1][:100],
                },
                "human_review": None,
            }
        else:
            assoc = {
                "source_element_id": "",
                "target_element_id": target_id,
                "figure_id": figure_id,
                "namespace": "FIGURE",
                "association_type": "unmatched",
                "confidence": 0.0,
                "status": "UNRESOLVED",
                "evidence": "Unresolved: no_text_ref_found",
                "source_anchor": {
                    "document_id": "F02",
                    "element_type": "IMAGE",
                    "element_id": element_id,
                    "page": page,
                    "confidence": 0.0,
                },
                "human_review": None,
            }
        associations.append(assoc)

    elif etype == "table":
        tbl_counter += 1
        element_id = f"F02_p{page}_b{elem_idx}"
        target_id = f"p{page}_tbl{elem_idx}"

        captions = elem.get("table_caption", [])
        caption_text = captions[0] if captions else ""

        tbl_match = re.search(r"TABLE\s+(\d+)", caption_text, re.IGNORECASE)
        tbl_num = int(tbl_match.group(1)) if tbl_match else tbl_counter
        table_id = f"Table {tbl_num}"
        search_pattern = f"Table {tbl_num}"

        text_ref_found = False
        ref_line = None
        for li, line in enumerate(md_lines):
            if search_pattern in line and not line.strip().startswith("![") and not line.strip().startswith("TABLE"):
                text_ref_found = True
                ref_line = li + 1
                break

        if text_ref_found:
            assoc = {
                "source_element_id": element_id,
                "target_element_id": target_id,
                "figure_id": table_id,
                "namespace": "TABLE",
                "association_type": "explicit_reference",
                "confidence": 0.95,
                "status": "CANDIDATE",
                "evidence": f"Text reference found at markdown line {ref_line}",
                "source_anchor": {
                    "document_id": "F02",
                    "element_type": "TEXT",
                    "element_id": element_id,
                    "page": page,
                    "confidence": 0.95,
                    "location": f"md_line_{ref_line}",
                    "raw_text": md_lines[ref_line - 1][:100],
                },
                "human_review": None,
            }
        else:
            assoc = {
                "source_element_id": "",
                "target_element_id": target_id,
                "figure_id": table_id,
                "namespace": "TABLE",
                "association_type": "unmatched",
                "confidence": 0.0,
                "status": "UNRESOLVED",
                "evidence": "Unresolved: no_text_ref_found",
                "source_anchor": {
                    "document_id": "F02",
                    "element_type": "TABLE",
                    "element_id": element_id,
                    "page": page,
                    "confidence": 0.0,
                },
                "human_review": None,
            }
        associations.append(assoc)

resolved = sum(1 for a in associations if a["status"] == "CANDIDATE")
unresolved = sum(1 for a in associations if a["status"] == "UNRESOLVED")
print(f"F02 figure associations: {len(associations)} total, {resolved} CANDIDATE, {unresolved} UNRESOLVED")

with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(associations, f, ensure_ascii=False, indent=2)
print(f"Saved: {OUT_PATH}")
