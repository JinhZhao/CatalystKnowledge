#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SINGLE-DOC-PIPELINE-ENGINEERING-004-B
F02表格识别执行脚本

使用MinerU 1.3.12 + RapidTable/slanet_plus
启用table_enable=True对F02 PDF重新执行表格识别
输出到独立目录F02_table_enabled/
"""

import sys
import io
import os
import json
import time
import shutil
import logging
from pathlib import Path
from datetime import datetime

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Paths
F02_PDF = Path(r"D:\Knowledge_World\_test_download_frontiers\Frontiers_Catalysis_PDF_Alternative_Kit\downloaded_frontiers\papers\F02\main.pdf")
OUTPUT_BASE = Path(r"D:\Knowledge_World\data\test_corpus\mineru_output\F02_table_enabled")
RUNS_DIR = Path(r"D:\Knowledge_World\runs\pipeline_001_fix\PIPELINE_004_B")

# Execution log
exec_log = []

def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    exec_log.append(line)

def main():
    log("=" * 70)
    log("PIPELINE-004-B: F02表格识别（table_enable=True）")
    log("=" * 70)
    
    # Verify input
    if not F02_PDF.exists():
        log(f"FATAL: F02 PDF not found: {F02_PDF}", "ERROR")
        return 1
    
    pdf_size = F02_PDF.stat().st_size
    log(f"输入PDF: {F02_PDF}")
    log(f"PDF大小: {pdf_size:,} bytes")
    
    # Prepare output directory
    if OUTPUT_BASE.exists():
        log(f"输出目录已存在，将清除: {OUTPUT_BASE}")
        shutil.rmtree(OUTPUT_BASE)
    OUTPUT_BASE.mkdir(parents=True, exist_ok=True)
    log(f"输出目录: {OUTPUT_BASE}")
    
    # Verify config
    from magic_pdf.libs.config_reader import get_local_models_dir, get_table_recog_config
    models_dir = get_local_models_dir()
    table_config = get_table_recog_config()
    log(f"models_dir: {models_dir}")
    log(f"table_config (before override): {json.dumps(table_config)}")
    log(f"models_dir exists: {Path(models_dir).exists()}")
    
    # Check model files
    for subdir in ['Layout', 'MFD', 'MFR', 'OCR']:
        sub_path = Path(models_dir) / subdir
        log(f"  {subdir}/ exists: {sub_path.exists()}")
    
    slanet_path = Path(r"C:\Users\JinhuiZhao\AppData\Roaming\Python\Python311\site-packages\magic_pdf\resources\slanet_plus\slanet-plus.onnx")
    log(f"slanet-plus.onnx exists: {slanet_path.exists()} ({slanet_path.stat().st_size / 1024 / 1024:.1f} MB)" if slanet_path.exists() else "slanet-plus.onnx: NOT FOUND")
    
    # Read PDF
    log("\n读取PDF数据...")
    with open(F02_PDF, 'rb') as f:
        pdf_bytes = f.read()
    log(f"PDF读取完成: {len(pdf_bytes):,} bytes")
    
    # Execute MinerU parsing with table_enable=True
    log("\n启动MinerU解析（table_enable=True）...")
    log("这一步将使用slanet_plus进行表格结构识别+OCR")
    
    start_time = time.time()
    
    try:
        from magic_pdf.tools.common import do_parse
        
        do_parse(
            output_dir=str(OUTPUT_BASE),
            pdf_file_name="main",
            pdf_bytes_or_dataset=pdf_bytes,
            model_list=[],
            parse_method="auto",
            debug_able=False,
            f_draw_span_bbox=True,
            f_draw_layout_bbox=True,
            f_dump_md=True,
            f_dump_middle_json=True,
            f_dump_model_json=True,
            f_dump_orig_pdf=True,
            f_dump_content_list=True,
            start_page_id=0,
            end_page_id=None,
            lang="ch",  # ch模式使用完整OCR模型(ch_PP-OCRv3_det + ch_PP-OCRv4_rec)
            table_enable=True,  # KEY: enable table recognition
        )
        
        elapsed = time.time() - start_time
        log(f"\nMinerU解析完成: {elapsed:.1f}秒")
        
    except Exception as e:
        elapsed = time.time() - start_time
        log(f"\nMinerU解析失败 ({elapsed:.1f}秒): {e}", "ERROR")
        import traceback
        tb = traceback.format_exc()
        log(tb, "ERROR")
        
        # Save error log
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        with open(RUNS_DIR / "004b_execution_error.log", "w", encoding="utf-8") as f:
            f.write("\n".join(exec_log))
            f.write(f"\n\nEXCEPTION:\n{tb}")
        
        return 2
    
    # Inspect output
    log("\n" + "=" * 70)
    log("检查输出结果")
    log("=" * 70)
    
    auto_dir = OUTPUT_BASE / "main" / "auto"
    if not auto_dir.exists():
        # Try alternative structure
        auto_dir = OUTPUT_BASE / "auto"
    
    if not auto_dir.exists():
        log("ERROR: 未找到auto输出目录", "ERROR")
        # List what was created
        for item in OUTPUT_BASE.rglob("*"):
            log(f"  {item.relative_to(OUTPUT_BASE)}")
        return 3
    
    log(f"输出目录: {auto_dir}")
    
    # List output files
    for item in sorted(auto_dir.iterdir()):
        if item.is_file():
            log(f"  {item.name} ({item.stat().st_size:,} bytes)")
        elif item.is_dir():
            sub_count = len(list(item.iterdir()))
            log(f"  {item.name}/ ({sub_count} items)")
    
    # Check content_list for table entries
    content_list_path = None
    for p in auto_dir.iterdir():
        if p.name.endswith("_content_list.json"):
            content_list_path = p
            break
    
    if content_list_path:
        log(f"\n分析content_list.json...")
        with open(content_list_path, 'r', encoding='utf-8') as f:
            content_list = json.load(f)
        
        table_entries = [e for e in content_list if e.get('type') == 'table']
        log(f"表格条目数: {len(table_entries)}")
        
        for idx, te in enumerate(table_entries):
            log(f"\n--- Table {idx+1} ---")
            log(f"  page_idx: {te.get('page_idx')}")
            log(f"  table_caption: {te.get('table_caption', 'N/A')[:100]}")
            log(f"  has table_body: {'table_body' in te}")
            log(f"  has img_path: {'img_path' in te}")
            
            if 'table_body' in te:
                html = te['table_body']
                log(f"  table_body length: {len(html)} chars")
                # Count rows and cells
                tr_count = html.lower().count('<tr')
                td_count = html.lower().count('<td')
                th_count = html.lower().count('<th')
                log(f"  HTML统计: {tr_count} <tr>, {td_count} <td>, {th_count} <th>")
                # Print first 500 chars of HTML
                log(f"  HTML预览: {html[:500]}")
            else:
                log(f"  WARNING: 无table_body字段!")
                log(f"  所有keys: {list(te.keys())}")
    
    # Check middle.json for table model results
    middle_json_path = None
    for p in auto_dir.iterdir():
        if p.name.endswith("_middle.json"):
            middle_json_path = p
            break
    
    if middle_json_path:
        log(f"\n分析middle.json表格检测...")
        with open(middle_json_path, 'r', encoding='utf-8') as f:
            middle = json.load(f)
        
        pdf_info = middle.get('pdf_info', [])
        for page_idx, page in enumerate(pdf_info):
            if isinstance(page, dict):
                preproc = page.get('preproc_blocks', [])
                for b in preproc:
                    if b.get('type') == 'table':
                        inner = b.get('blocks', [])
                        log(f"  Page {page_idx}: table bbox={b.get('bbox')}")
                        for ib in inner:
                            ibtype = ib.get('type', '')
                            if ibtype == 'table_body':
                                vl = ib.get('virtual_lines', [])
                                has_spans = any(len(sl.get('spans', [])) > 0 for sl in vl) if vl else False
                                log(f"    table_body: {len(vl)} virtual_lines, has_spans={has_spans}")
                                if has_spans:
                                    # Show first few spans
                                    for vi, vline in enumerate(vl[:3]):
                                        spans = vline.get('spans', [])
                                        span_texts = [s.get('content', '')[:30] for s in spans[:5]]
                                        log(f"      line[{vi}]: {span_texts}")
    
    # Save execution log
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RUNS_DIR / "004b_execution.log", "w", encoding="utf-8") as f:
        f.write("\n".join(exec_log))
    log(f"\n执行日志已保存: {RUNS_DIR / '004b_execution.log'}")
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
