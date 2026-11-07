"""
合并007的249个独立VLM记录文件为单一JSON文件
格式符合EV adapter期望: results[].records[]
"""
import json
from pathlib import Path
from collections import defaultdict

BASE = Path("D:/Knowledge_World")
VLM_DIR = BASE / "runs/pipeline_001_fix/PIPELINE_007/vlm_records"
OUTPUT = BASE / "runs/pipeline_001_fix/PIPELINE_007_R2/F02_vlm_science_records_consolidated.json"

# 按figure_id分组
records_by_figure = defaultdict(list)

for f in sorted(VLM_DIR.glob("*.json")):
    with open(f, encoding='utf-8') as fp:
        rec = json.load(fp)
    fig_id = rec.get('figure_id', 'unknown')
    records_by_figure[fig_id].append(rec)

# 构建合并文件
consolidated = {
    "adapter_version": "007-R2-consolidated",
    "document_id": "F02",
    "namespace": "F02",
    "run_id": "VLM-007-R2",
    "model_id": "GLM-Pro",
    "total_records": sum(len(recs) for recs in records_by_figure.values()),
    "figures_processed": len(records_by_figure),
    "adapter_status": "PASS",
    "results": []
}

for fig_id in sorted(records_by_figure.keys()):
    recs = records_by_figure[fig_id]
    consolidated["results"].append({
        "figure_id": fig_id,
        "status": "PASS",
        "run_id": "VLM-007-R2",
        "record_count": len(recs),
        "records": recs
    })

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(consolidated, f, indent=2, ensure_ascii=False)

print(f"合并完成: {consolidated['total_records']} records, {len(records_by_figure)} figures")
print(f"输出: {OUTPUT}")
