#!/bin/bash
# FLOW-VERIFY-001 A线：24份PDF批量解析脚本（使用magic-pdf命令行）
# 支持断点续跑、失败隔离、幂等执行

set -e

MANIFEST="D:/Knowledge_World/data/test_corpus/unified_test_manifest.json"
OUTPUT_BASE="D:/Knowledge_World/data/test_corpus/mineru_output"
SUMMARY_FILE="$OUTPUT_BASE/batch_summary.json"

echo "============================================================"
echo "FLOW-VERIFY-001 A线：24份PDF批量解析"
echo "============================================================"
echo "开始时间: $(date -Iseconds)"

# 提取所有PDF文件路径（排除XLSX/ZIP）
echo ""
echo "提取PDF文档清单..."

# 使用Python提取PDF列表
python3 << 'PYEOF'
import json
from pathlib import Path

manifest_path = "D:/Knowledge_World/data/test_corpus/unified_test_manifest.json"
output_base = Path("D:/Knowledge_World/data/test_corpus/mineru_output")

with open(manifest_path, "r", encoding="utf-8") as f:
    manifest = json.load(f)

# 已处理的测试样本
already_processed = {"F07_test", "P01_test", "PAT01_test"}

# 提取PDF文档
pdf_docs = []
for doc in manifest["documents"]:
    if doc["signature_type"] == "PDF":
        doc_id = doc["document_id"]
        # 跳过已处理的
        if any(doc_id in ap for ap in already_processed):
            continue
        # 检查输出目录是否存在
        output_dir = output_base / f"{doc_id}_batch" / "auto"
        if output_dir.exists():
            continue
        pdf_docs.append({
            "id": doc_id,
            "path": doc["file_path"],
            "group": doc["group"],
            "size": doc["file_size_bytes"]
        })

# 输出待处理列表
print(f"总计 {len(pdf_docs)} 份PDF待处理")
for i, doc in enumerate(pdf_docs, 1):
    print(f"{i}. {doc['id']} ({doc['group']}) - {doc['size']:,} bytes")

# 保存为临时文件供bash使用
with open(output_base / "pending_pdfs.json", "w", encoding="utf-8") as f:
    json.dump(pdf_docs, f, ensure_ascii=False, indent=2)
PYEOF

echo ""
echo "开始批量处理..."
echo ""

# 读取待处理列表
PENDING_FILE="$OUTPUT_BASE/pending_pdfs.json"

if [ ! -f "$PENDING_FILE" ]; then
    echo "✅ 所有文档已处理完成"
    exit 0
fi

# 统计
TOTAL=$(python3 -c "import json; print(len(json.load(open('$PENDING_FILE'))))")
PASS_COUNT=0
FAIL_COUNT=0
INDEX=0

# 初始化汇总文件
echo "[" > "$SUMMARY_FILE"

# 逐个处理
python3 << PYEOF
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

pending_file = "$PENDING_FILE"
output_base = Path("$OUTPUT_BASE")
summary_file = Path("$SUMMARY_FILE")

with open(pending_file, "r", encoding="utf-8") as f:
    pdf_docs = json.load(f)

total = len(pdf_docs)
results = []
pass_count = 0
fail_count = 0

for i, doc in enumerate(pdf_docs, 1):
    doc_id = doc["id"]
    pdf_path = doc["path"]
    output_dir = output_base / f"{doc_id}_batch"
    
    print(f"\n{'='*60}")
    print(f"进度: {i}/{total}")
    print(f"文档: {doc_id}")
    print(f"文件: {pdf_path}")
    print(f"输出: {output_dir}")
    
    start_time = time.time()
    result = {
        "document_id": doc_id,
        "group": doc["group"],
        "file_path": pdf_path,
        "file_size_bytes": doc["size"],
        "status": "UNKNOWN",
        "error": None,
        "output_dir": str(output_dir),
        "processing_time": 0,
        "timestamp": datetime.now().isoformat(),
    }
    
    try:
        # 创建输出目录
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 调用magic-pdf命令行
        cmd = [
            "magic-pdf",
            "-p", pdf_path,
            "-o", str(output_dir),
            "-m", "auto",
        ]
        
        print(f"执行: {' '.join(cmd)}")
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10分钟超时
        )
        
        if proc.returncode == 0:
            result["status"] = "PASS"
            pass_count += 1
            print(f"✅ 成功")
            
            # 统计输出文件
            auto_dir = output_dir / "auto"
            if auto_dir.exists():
                md_files = list(auto_dir.glob("*.md"))
                json_files = list(auto_dir.glob("*.json"))
                image_dirs = list(auto_dir.glob("images"))
                result["md_count"] = len(md_files)
                result["json_count"] = len(json_files)
                result["image_dir_count"] = len(image_dirs)
        else:
            result["status"] = "FAILED"
            result["error"] = proc.stderr[:500] if proc.stderr else "Unknown error"
            fail_count += 1
            print(f"❌ 失败: {result['error'][:200]}")
            
    except subprocess.TimeoutExpired:
        result["status"] = "TIMEOUT"
        result["error"] = "Processing exceeded 10 minutes"
        fail_count += 1
        print(f"⏱️ 超时")
    except Exception as e:
        result["status"] = "FAILED"
        result["error"] = str(e)
        fail_count += 1
        print(f"❌ 异常: {e}")
    
    finally:
        processing_time = time.time() - start_time
        result["processing_time"] = round(processing_time, 2)
        print(f"耗时: {processing_time:.2f}秒")
        results.append(result)

# 保存汇总
summary = {
    "batch_time": datetime.now().isoformat(),
    "total_pdfs": total,
    "pass_count": pass_count,
    "fail_count": fail_count,
    "success_rate": f"{pass_count}/{total} ({pass_count/total*100:.1f}%)" if total > 0 else "0/0",
    "results": results,
}

with open(summary_file, "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print(f"\n{'='*60}")
print(f"批量处理完成")
print(f"成功: {pass_count}/{total}")
print(f"失败: {fail_count}/{total}")
print(f"汇总: {summary_file}")
print(f"结束时间: {datetime.now().isoformat()}")
print(f"{'='*60}")
PYEOF

echo ""
echo "✅ 批量处理脚本执行完成"
echo "汇总文件: $SUMMARY_FILE"
