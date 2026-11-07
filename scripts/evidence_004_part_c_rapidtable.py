#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SINGLE-DOC-EVIDENCE-004 Part C: RapidTable表格结构化复用

C1: 盘点已有专项解析结果
C2: 建立结构化表格数据对象
C3: 优先PAT01 Table 1
C4: P01/F07/F02表格
C5: 表格验收
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from html.parser import HTMLParser

MINERU_ROOT = Path(r"D:\Knowledge_World\data\test_corpus\mineru_output")
RUNS_ROOT = Path(r"D:\Knowledge_World\runs")

@dataclass
class TableCell:
    """表格单元格"""
    cell_id: str
    row_index: int
    column_index: int
    raw_value: str
    unit: Optional[str]
    colspan: int
    rowspan: int
    is_header: bool

@dataclass
class TableRow:
    """表格行"""
    row_id: str
    row_index: int
    cells: List[TableCell]
    is_header_row: bool

@dataclass
class TableRecord:
    """表格记录"""
    table_id: str
    source_document_id: str
    table_page: int
    source_element_id: str
    rows: List[TableRow]
    caption: Optional[str]
    footnote: Optional[str]
    parsing_status: str  # HTML_PARSED, IMAGE_ONLY, PARTIAL
    total_rows: int
    total_cells: int

class HTMLTableParser(HTMLParser):
    """HTML表格解析器"""
    
    def __init__(self):
        super().__init__()
        self.tables = []
        self.current_table = []
        self.current_row = []
        self.current_cell = ""
        self.current_cell_attrs = {}
        self.in_cell = False
        self.in_row = False
        
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        
        if tag == "table":
            self.current_table = []
        elif tag == "tr":
            self.current_row = []
            self.in_row = True
        elif tag in ("td", "th"):
            self.current_cell = ""
            self.current_cell_attrs = attrs_dict
            self.in_cell = True
            
    def handle_endtag(self, tag):
        if tag == "table":
            if self.current_table:
                self.tables.append(self.current_table)
            self.current_table = []
        elif tag == "tr":
            if self.in_row and self.current_row:
                self.current_table.append(self.current_row)
            self.in_row = False
        elif tag in ("td", "th"):
            if self.in_cell:
                self.current_row.append({
                    "value": self.current_cell.strip(),
                    "attrs": self.current_cell_attrs,
                    "is_header": tag == "th"
                })
            self.in_cell = False
            
    def handle_data(self, data):
        if self.in_cell:
            self.current_cell += data

def parse_html_table(html: str) -> List[List[Dict]]:
    """解析HTML表格"""
    parser = HTMLTableParser()
    try:
        parser.feed(html)
        return parser.tables[0] if parser.tables else []
    except Exception as e:
        print(f"[WARNING] HTML parse error: {e}")
        return []

def build_table_record(
    doc_id: str,
    table_idx: int,
    page: int,
    element_id: str,
    html: str,
    caption: Optional[str],
    footnote: Optional[str]
) -> TableRecord:
    """构建TableRecord"""
    table_id = f"{doc_id}_table_{table_idx:03d}"
    
    rows_data = parse_html_table(html)
    
    if not rows_data:
        return TableRecord(
            table_id=table_id,
            source_document_id=doc_id,
            table_page=page,
            source_element_id=element_id,
            rows=[],
            caption=caption,
            footnote=footnote,
            parsing_status="IMAGE_ONLY",
            total_rows=0,
            total_cells=0
        )
    
    rows = []
    total_cells = 0
    
    for row_idx, row_data in enumerate(rows_data):
        row_id = f"{table_id}_r{row_idx:03d}"
        cells = []
        
        # 判断是否为表头行
        is_header_row = all(cell.get("is_header", False) for cell in row_data) if row_data else False
        
        for col_idx, cell_data in enumerate(row_data):
            cell_id = f"{row_id}_c{col_idx:03d}"
            attrs = cell_data.get("attrs", {})
            
            # 解析colspan和rowspan
            colspan = int(attrs.get("colspan", 1))
            rowspan = int(attrs.get("rowspan", 1))
            
            # 尝试提取单位
            raw_value = cell_data.get("value", "")
            unit = None
            unit_match = re.search(r'\(([^)]+)\)\s*$', raw_value)
            if unit_match:
                unit = unit_match.group(1)
            
            cell = TableCell(
                cell_id=cell_id,
                row_index=row_idx,
                column_index=col_idx,
                raw_value=raw_value,
                unit=unit,
                colspan=colspan,
                rowspan=rowspan,
                is_header=cell_data.get("is_header", False) or row_idx == 0
            )
            cells.append(cell)
            total_cells += 1
        
        row = TableRow(
            row_id=row_id,
            row_index=row_idx,
            cells=cells,
            is_header_row=is_header_row
        )
        rows.append(row)
    
    return TableRecord(
        table_id=table_id,
        source_document_id=doc_id,
        table_page=page,
        source_element_id=element_id,
        rows=rows,
        caption=caption,
        footnote=footnote,
        parsing_status="HTML_PARSED",
        total_rows=len(rows),
        total_cells=total_cells
    )

def process_document_tables(doc_id: str, mineru_dir: Path) -> List[TableRecord]:
    """处理单个文档的所有表格"""
    tables = []
    
    # 查找content_list.json
    auto_dir = None
    for subdir in mineru_dir.iterdir():
        if subdir.is_dir():
            auto_candidate = subdir / "auto"
            if auto_candidate.exists():
                auto_dir = auto_candidate
                break
    
    if not auto_dir:
        print(f"[WARNING] No auto directory found for {doc_id}")
        return tables
    
    content_list_path = None
    for p in auto_dir.iterdir():
        if p.name.endswith("_content_list.json"):
            content_list_path = p
            break
    
    if not content_list_path:
        return tables
    
    with open(content_list_path, "r", encoding="utf-8") as f:
        content_list = json.load(f)
    
    # 提取表格元素
    table_elements = [e for e in content_list if e.get("type") == "table"]
    
    print(f"[RapidTable] {doc_id}: 发现{len(table_elements)}个表格")
    
    for idx, elem in enumerate(table_elements):
        element_id = f"{doc_id}_p{elem.get('page_idx', 0)}_b{content_list.index(elem)}"
        html = elem.get("table_body", "")
        caption = elem.get("table_caption")
        footnote = elem.get("table_footnote")
        page = elem.get("page_idx", 0)
        
        if html:
            table_record = build_table_record(
                doc_id=doc_id,
                table_idx=idx,
                page=page,
                element_id=element_id,
                html=html,
                caption=caption,
                footnote=footnote
            )
            tables.append(table_record)
            print(f"  Table {idx}: {table_record.parsing_status}, {table_record.total_rows} rows, {table_record.total_cells} cells")
        else:
            # 无HTML数据
            table_record = TableRecord(
                table_id=f"{doc_id}_table_{idx:03d}",
                source_document_id=doc_id,
                table_page=page,
                source_element_id=element_id,
                rows=[],
                caption=caption,
                footnote=footnote,
                parsing_status="IMAGE_ONLY",
                total_rows=0,
                total_cells=0
            )
            tables.append(table_record)
            print(f"  Table {idx}: IMAGE_ONLY (no HTML)")
    
    return tables

def main():
    """主函数"""
    doc_configs = {
        "F02": MINERU_ROOT / "F02_regression",
        "F07": MINERU_ROOT / "F07_table_test",
        "P01": MINERU_ROOT / "P01_table_segmented",
        "PAT01": MINERU_ROOT / "PAT01_table_test"
    }
    
    print("=" * 80)
    print("SINGLE-DOC-EVIDENCE-004 Part C: RapidTable表格结构化复用")
    print("=" * 80)
    
    all_tables = {}
    total_tables = 0
    total_html_parsed = 0
    total_image_only = 0
    total_rows = 0
    total_cells = 0
    
    for doc_id, mineru_dir in doc_configs.items():
        print(f"\n{'='*80}")
        print(f"处理文档: {doc_id}")
        print(f"{'='*80}")
        
        if not mineru_dir.exists():
            print(f"[ERROR] Directory not found: {mineru_dir}")
            continue
        
        tables = process_document_tables(doc_id, mineru_dir)
        all_tables[doc_id] = [asdict(t) for t in tables]
        
        # 统计
        doc_html = sum(1 for t in tables if t.parsing_status == "HTML_PARSED")
        doc_image = sum(1 for t in tables if t.parsing_status == "IMAGE_ONLY")
        doc_rows = sum(t.total_rows for t in tables)
        doc_cells = sum(t.total_cells for t in tables)
        
        print(f"\n{doc_id} 统计:")
        print(f"  表格总数: {len(tables)}")
        print(f"  HTML解析: {doc_html}")
        print(f"  仅图像: {doc_image}")
        print(f"  总行数: {doc_rows}")
        print(f"  总单元格: {doc_cells}")
        
        total_tables += len(tables)
        total_html_parsed += doc_html
        total_image_only += doc_image
        total_rows += doc_rows
        total_cells += doc_cells
    
    # 保存结果
    output_dir = RUNS_ROOT / "evidence_004"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = output_dir / "part_c_rapidtable_structuring.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_tables, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*80}")
    print("Part C完成")
    print(f"{'='*80}")
    print(f"结果已保存: {output_path}")
    print(f"\n汇总统计:")
    print(f"  表格总数: {total_tables}")
    print(f"  HTML解析成功: {total_html_parsed} ({total_html_parsed/total_tables*100:.1f}%)" if total_tables > 0 else "  HTML解析成功: 0")
    print(f"  仅图像: {total_image_only}")
    print(f"  总行数: {total_rows}")
    print(f"  总单元格: {total_cells}")

if __name__ == "__main__":
    main()
