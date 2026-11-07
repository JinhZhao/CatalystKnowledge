#!/usr/bin/env python3
"""
FLOW-VERIFY-001 A线：PDF批量解析脚本（修复版）
- 使用Python而非bash+heredoc，避免Windows python3 stub问题
- 支持断点续跑、失败隔离、幂等执行
- 详细日志和异常处理
"""

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# 配置
MANIFEST_PATH = Path(r"D:\Knowledge_World\data\test_corpus\unified_test_manifest.json")
OUTPUT_BASE = Path(r"D:\Knowledge_World\data\test_corpus\mineru_output")
SUMMARY_PATH = OUTPUT_BASE / "batch_summary.json"
LOG_PATH = OUTPUT_BASE / "batch_processing.log"


def log(message, level="INFO"):
    """写入日志和控制台"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] [{level}] {message}"
    print(log_line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(log_line + "\n")


def load_manifest():
    """加载测试语料清单"""
    log(f"加载manifest: {MANIFEST_PATH}")
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    log(f"Manifest加载成功: {manifest['summary']['total_documents']}份文档")
    return manifest


def get_pending_pdfs(manifest):
    """获取待处理的PDF列表（基于实际输出检查，不依赖硬编码列表）"""
    pending = []
    skipped = []
    
    for doc in manifest["documents"]:
        if doc["signature_type"] != "PDF":
            skipped.append((doc["document_id"], "非PDF文件"))
            continue
        
        doc_id = doc["document_id"]
        prefix = doc_id.split('_')[0] if '_' in doc_id else doc_id
        
        # 检查输出目录是否存在且包含有效MD文件
        has_valid_output = False
        
        for out_dir in OUTPUT_BASE.iterdir():
            if not out_dir.is_dir():
                continue
            
            # 匹配文档ID或前缀
            if doc_id in out_dir.name or out_dir.name.startswith(prefix):
                # 递归搜索MD文件
                md_files = list(out_dir.rglob('*.md'))
                if len(md_files) > 0:
                    has_valid_output = True
                    skipped.append((doc_id, f"输出已存在({out_dir.name}, {len(md_files)} MD)"))
                    break
        
        if not has_valid_output:
            pending.append({
                "id": doc_id,
                "path": doc["file_path"],
                "group": doc["group"],
                "size": doc["file_size_bytes"],
                "sha256": doc["sha256"],
            })
    
    log(f"待处理PDF: {len(pending)}份")
    log(f"跳过: {len(skipped)}份")
    
    for doc_id, reason in skipped:
        log(f"  跳过 {doc_id}: {reason}", "DEBUG")
    
    return pending


def parse_single_pdf(doc, index, total):
    """解析单个PDF文件"""
    doc_id = doc["id"]
    pdf_path = doc["path"]
    output_dir = OUTPUT_BASE / f"{doc_id}_batch"
    
    log(f"\n{'='*70}")
    log(f"[{index}/{total}] 开始处理: {doc_id}")
    log(f"文件: {pdf_path}")
    log(f"大小: {doc['size']:,} bytes")
    log(f"输出: {output_dir}")
    
    start_time = time.time()
    result = {
        "document_id": doc_id,
        "group": doc["group"],
        "file_path": pdf_path,
        "file_size_bytes": doc["size"],
        "sha256": doc["sha256"],
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
        
        log(f"执行命令: {' '.join(cmd)}")
        
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=900,  # 15分钟超时（大型SI PDF可能需要更长时间）
            encoding="utf-8",
            errors="replace",
        )
        
        # 检查返回码
        if proc.returncode == 0:
            result["status"] = "PASS"
            log(f"[PASS] Success: {doc_id}")
            
            # 统计输出文件
            auto_dir = output_dir / "main" / "auto"
            if not auto_dir.exists():
                auto_dir = output_dir / "auto"
            
            if auto_dir.exists():
                md_files = list(auto_dir.glob("*.md"))
                json_files = list(auto_dir.glob("*.json"))
                image_dirs = list(auto_dir.glob("images"))
                
                result["md_count"] = len(md_files)
                result["json_count"] = len(json_files)
                result["image_dir_count"] = len(image_dirs)
                
                log(f"  Output: {len(md_files)} MD, {len(json_files)} JSON, {len(image_dirs)} image dirs")
            else:
                log(f"  [WARN] No auto directory found", "WARN")
        else:
            result["status"] = "FAILED"
            result["error"] = proc.stderr[:1000] if proc.stderr else "Unknown error"
            log(f"[FAIL] Failed: {doc_id}", "ERROR")
            log(f"  Error: {result['error'][:200]}", "ERROR")
            
            # 保存完整错误日志
            error_log_path = output_dir / "error.log"
            with open(error_log_path, "w", encoding="utf-8") as f:
                f.write(f"STDOUT:\n{proc.stdout}\n\nSTDERR:\n{proc.stderr}\n")
            log(f"  错误日志已保存: {error_log_path}", "ERROR")
            
    except subprocess.TimeoutExpired:
        result["status"] = "TIMEOUT"
        result["error"] = "Processing exceeded 15 minutes"
        log(f"[TIMEOUT] Timeout: {doc_id}", "ERROR")
        
    except FileNotFoundError as e:
        result["status"] = "FAILED"
        result["error"] = f"File not found: {e}"
        log(f"[FAIL] File not found: {pdf_path}", "ERROR")
        
    except Exception as e:
        result["status"] = "FAILED"
        result["error"] = str(e)
        log(f"[FAIL] Exception: {doc_id} - {e}", "ERROR")
        import traceback
        log(traceback.format_exc(), "ERROR")
    
    finally:
        processing_time = time.time() - start_time
        result["processing_time"] = round(processing_time, 2)
        log(f"耗时: {processing_time:.2f}秒")
    
    return result


def main():
    """主函数"""
    log("="*70)
    log("FLOW-VERIFY-001 A线：PDF批量解析（修复版）")
    log("="*70)
    log(f"开始时间: {datetime.now().isoformat()}")
    
    # 初始化日志文件
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write(f"Batch processing started at {datetime.now().isoformat()}\n")
    
    try:
        # 加载manifest
        manifest = load_manifest()
        
        # 获取待处理列表
        pending = get_pending_pdfs(manifest)
        
        if not pending:
            log("\n[DONE] All documents already processed, no action needed")
            return 0
        
        log(f"\n开始批量处理 {len(pending)} 份PDF...")
        
        # 逐个处理（串行，CPU环境限制并发）
        results = []
        pass_count = 0
        fail_count = 0
        timeout_count = 0
        
        for i, doc in enumerate(pending, 1):
            result = parse_single_pdf(doc, i, len(pending))
            results.append(result)
            
            if result["status"] == "PASS":
                pass_count += 1
            elif result["status"] == "TIMEOUT":
                timeout_count += 1
            else:
                fail_count += 1
        
        # 保存汇总
        summary = {
            "batch_time": datetime.now().isoformat(),
            "total_pdfs": len(pending),
            "pass_count": pass_count,
            "fail_count": fail_count,
            "timeout_count": timeout_count,
            "success_rate": f"{pass_count}/{len(pending)} ({pass_count/len(pending)*100:.1f}%)" if pending else "0/0",
            "results": results,
        }
        
        with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        
        log(f"\n{'='*70}")
        log(f"批量处理完成")
        log(f"成功: {pass_count}/{len(pending)}")
        log(f"失败: {fail_count}/{len(pending)}")
        log(f"超时: {timeout_count}/{len(pending)}")
        log(f"成功率: {summary['success_rate']}")
        log(f"汇总文件: {SUMMARY_PATH}")
        log(f"日志文件: {LOG_PATH}")
        log(f"结束时间: {datetime.now().isoformat()}")
        log(f"{'='*70}")
        
        return 0 if fail_count == 0 and timeout_count == 0 else 1
        
    except Exception as e:
        log(f"[FAIL] Batch main function exception: {e}", "ERROR")
        import traceback
        log(traceback.format_exc(), "ERROR")
        return 2


if __name__ == "__main__":
    sys.exit(main())
