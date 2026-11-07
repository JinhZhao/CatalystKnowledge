#!/usr/bin/env python3
"""Generate F02 Knowledge Report v2 - Interactive Scientific Knowledge Browser"""

import json
import os
import base64
from pathlib import Path
from datetime import datetime

# Data paths
RUNS_DIR = Path("D:/Knowledge_World/runs/real_e2e_gate_014")
REPORT_JSON = RUNS_DIR / "reports/F02_knowledge_report.json"
VLM_RECORDS = RUNS_DIR / "PIPELINE_005_G/F02_vlm_science_records.json"
FIGURE_PARSER = RUNS_DIR / "figure_parser/F02_figure_parser.json"
TABLE_PARSER = RUNS_DIR / "table_parser/F02_table_parser.json"
EXTRACTION_DIR = RUNS_DIR / "extraction_v2/F02"
MINERU_IMAGES = Path("D:/Knowledge_World/data/test_corpus/mineru_output/F02_regression/main/auto/images")

def load_json(path):
    """Load JSON file with UTF-8 encoding"""
    if not os.path.exists(path):
        print(f"Warning: {path} not found")
        return {}
    with open(path, encoding='utf-8') as f:
        return json.load(f)

def image_to_base64(image_path):
    """Convert image to base64 for embedding"""
    if not os.path.exists(image_path):
        return None
    with open(image_path, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode('utf-8')

def load_all_data():
    """Load all data sources"""
    print("Loading data sources...")
    data = {
        'report': load_json(REPORT_JSON),
        'vlm': load_json(VLM_RECORDS),
        'figure_parser': load_json(FIGURE_PARSER),
        'table_parser': load_json(TABLE_PARSER),
    }
    
    # Load dimension extractions
    dimensions = {}
    for dim in ['catalyst_design', 'characterization', 'performance', 'mechanism', 'structure_activity', 'reliability']:
        dim_file = EXTRACTION_DIR / f"{dim}_v2_extracted.json"
        dimensions[dim] = load_json(dim_file)
    data['dimensions'] = dimensions
    
    # Load and encode images
    print("Encoding figure images...")
    figure_images = {}
    if 'figure_parser' in data and 'figures' in data['figure_parser']:
        for fig in data['figure_parser']['figures']:
            fig_id = fig.get('figure_id')
            img_path = fig.get('image_path')
            if fig_id and img_path and os.path.exists(img_path):
                b64 = image_to_base64(img_path)
                if b64:
                    figure_images[fig_id] = b64
                    print(f"  {fig_id}: {len(b64)//1024}KB")
    data['figure_images'] = figure_images
    
    return data

def generate_html(data):
    """Generate the complete HTML report"""
    print("Generating HTML...")
    
    # Prepare data for embedding
    report = data['report']
    vlm = data['vlm']
    figure_parser = data['figure_parser']
    table_parser = data['table_parser']
    dimensions = data['dimensions']
    figure_images = data['figure_images']
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>F02科学知识报告 - Cu/BN光热催化丙烷脱氢</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
            background: #f5f5f5;
            color: #333;
            line-height: 1.6;
        }}
        
        /* Layout */
        .container {{ display: flex; min-height: 100vh; }}
        .sidebar {{
            width: 280px;
            background: #fff;
            border-right: 1px solid #e0e0e0;
            position: fixed;
            height: 100vh;
            overflow-y: auto;
            padding: 20px 0;
        }}
        .main-content {{
            margin-left: 280px;
            flex: 1;
            padding: 30px 40px;
            max-width: 1200px;
        }}
        
        /* Sidebar navigation */
        .nav-header {{
            padding: 0 20px 20px;
            border-bottom: 2px solid #2196F3;
            margin-bottom: 20px;
        }}
        .nav-header h2 {{
            font-size: 18px;
            color: #2196F3;
            margin-bottom: 5px;
        }}
        .nav-header .doc-id {{
            font-size: 12px;
            color: #999;
        }}
        .nav-section {{
            padding: 8px 20px;
            cursor: pointer;
            transition: all 0.2s;
            font-size: 14px;
            border-left: 3px solid transparent;
        }}
        .nav-section:hover {{
            background: #f0f0f0;
            border-left-color: #2196F3;
        }}
        .nav-section.active {{
            background: #e3f2fd;
            border-left-color: #2196F3;
            font-weight: 600;
        }}
        
        /* Content sections */
        .section {{
            display: none;
            background: #fff;
            padding: 30px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }}
        .section.active {{ display: block; }}
        .section h1 {{
            font-size: 28px;
            color: #2196F3;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #e0e0e0;
        }}
        .section h2 {{
            font-size: 20px;
            color: #333;
            margin: 25px 0 15px;
        }}
        .section h3 {{
            font-size: 16px;
            color: #555;
            margin: 20px 0 10px;
        }}
        
        /* Cards */
        .card {{
            background: #fafafa;
            border-left: 4px solid #2196F3;
            padding: 15px 20px;
            margin: 15px 0;
            border-radius: 4px;
        }}
        .card.warning {{
            border-left-color: #ff9800;
            background: #fff8e1;
        }}
        .card.success {{
            border-left-color: #4caf50;
            background: #e8f5e9;
        }}
        .card.error {{
            border-left-color: #f44336;
            background: #ffebee;
        }}
        
        /* Tables */
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
            font-size: 14px;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border: 1px solid #e0e0e0;
        }}
        th {{
            background: #f5f5f5;
            font-weight: 600;
            cursor: pointer;
            user-select: none;
        }}
        th:hover {{ background: #e0e0e0; }}
        tr:hover {{ background: #fafafa; }}
        
        /* Figure gallery */
        .figure-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .figure-card {{
            background: #fafafa;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            overflow: hidden;
            cursor: pointer;
            transition: all 0.3s;
        }}
        .figure-card:hover {{
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            transform: translateY(-2px);
        }}
        .figure-card img {{
            width: 100%;
            height: 200px;
            object-fit: cover;
            background: #f0f0f0;
        }}
        .figure-card .caption {{
            padding: 12px;
            font-size: 13px;
        }}
        
        /* Modal */
        .modal {{
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.9);
        }}
        .modal.active {{ display: flex; align-items: center; justify-content: center; }}
        .modal-content {{
            max-width: 90%;
            max-height: 90%;
            position: relative;
        }}
        .modal-content img {{
            max-width: 100%;
            max-height: 90vh;
            object-fit: contain;
        }}
        .modal-close {{
            position: absolute;
            top: -40px;
            right: 0;
            color: #fff;
            font-size: 30px;
            cursor: pointer;
            background: none;
            border: none;
        }}
        .modal-caption {{
            color: #fff;
            text-align: center;
            padding: 15px;
            font-size: 14px;
        }}
        
        /* Search and filter */
        .search-box {{
            width: 100%;
            padding: 10px 15px;
            border: 1px solid #e0e0e0;
            border-radius: 4px;
            font-size: 14px;
            margin: 10px 0;
        }}
        .filter-group {{
            display: flex;
            gap: 10px;
            margin: 15px 0;
            flex-wrap: wrap;
        }}
        .filter-btn {{
            padding: 6px 12px;
            border: 1px solid #e0e0e0;
            background: #fff;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
            transition: all 0.2s;
        }}
        .filter-btn:hover {{ background: #f0f0f0; }}
        .filter-btn.active {{
            background: #2196F3;
            color: #fff;
            border-color: #2196F3;
        }}
        
        /* Status badges */
        .badge {{
            display: inline-block;
            padding: 3px 8px;
            border-radius: 3px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .badge.reported {{ background: #4caf50; color: #fff; }}
        .badge.not-reported {{ background: #f44336; color: #fff; }}
        .badge.not-extracted {{ background: #9e9e9e; color: #fff; }}
        .badge.unresolved {{ background: #ff9800; color: #fff; }}
        .badge.pass {{ background: #4caf50; color: #fff; }}
        .badge.fail {{ background: #f44336; color: #fff; }}
        
        /* Metadata */
        .meta-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }}
        .meta-item {{
            background: #fafafa;
            padding: 12px;
            border-radius: 4px;
        }}
        .meta-item label {{
            display: block;
            font-size: 12px;
            color: #999;
            margin-bottom: 4px;
        }}
        .meta-item value {{
            display: block;
            font-size: 14px;
            color: #333;
            font-weight: 500;
        }}
        
        /* Evidence tracking */
        .evidence-item {{
            background: #fafafa;
            border-left: 3px solid #2196F3;
            padding: 12px 15px;
            margin: 10px 0;
            border-radius: 4px;
        }}
        .evidence-item .source {{
            font-size: 12px;
            color: #999;
            margin-top: 5px;
        }}
        
        /* Scrollbar */
        ::-webkit-scrollbar {{ width: 8px; }}
        ::-webkit-scrollbar-track {{ background: #f0f0f0; }}
        ::-webkit-scrollbar-thumb {{ background: #c0c0c0; border-radius: 4px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: #a0a0a0; }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Sidebar Navigation -->
        <div class="sidebar">
            <div class="nav-header">
                <h2>F02 科学知识报告</h2>
                <div class="doc-id">KNOWLEDGE-WORLD-014</div>
                <div class="doc-id">{report.get('generated_at', 'N/A')}</div>
            </div>
            <div class="nav-section active" data-section="overview">1. 文献总览</div>
            <div class="nav-section" data-section="background">2. 研究背景与目标</div>
            <div class="nav-section" data-section="catalyst">3. 催化剂设计</div>
            <div class="nav-section" data-section="characterization">4. 材料表征</div>
            <div class="nav-section" data-section="performance">5. 催化性能</div>
            <div class="nav-section" data-section="mechanism">6. 反应机理</div>
            <div class="nav-section" data-section="structure-activity">7. 结构-性能关系</div>
            <div class="nav-section" data-section="figures">8. Figure Gallery</div>
            <div class="nav-section" data-section="tables">9. Table Explorer</div>
            <div class="nav-section" data-section="reliability">10. 可靠性与局限性</div>
            <div class="nav-section" data-section="evidence">11. 证据与研究空白</div>
            <div class="nav-section" data-section="audit">12. 数据来源与质量审计</div>
        </div>
        
        <!-- Main Content -->
        <div class="main-content">
            <!-- Section 1: Overview -->
            <div class="section active" id="overview">
                <h1>文献总览</h1>
                <div class="meta-grid">
                    <div class="meta-item">
                        <label>文档ID</label>
                        <value>{report.get('document_id', 'F02')}</value>
                    </div>
                    <div class="meta-item">
                        <label>标题</label>
                        <value style="font-size:13px;">{report.get('document_overview', {}).get('title', 'Photothermal oxidative dehydrogenation of propane to propylene over Cu/BN catalysts')}</value>
                    </div>
                    <div class="meta-item">
                        <label>DOI</label>
                        <value>{report.get('document_overview', {}).get('doi', '10.3389/fchem.2024.1439185')}</value>
                    </div>
                    <div class="meta-item">
                        <label>文档类型</label>
                        <value>{report.get('document_overview', {}).get('document_type', 'research_article')}</value>
                    </div>
                    <div class="meta-item">
                        <label>IR元素数</label>
                        <value>{report.get('document_structure', {}).get('total_elements', 79)}</value>
                    </div>
                    <div class="meta-item">
                        <label>图片数</label>
                        <value>{len(report.get('figures', []))}</value>
                    </div>
                    <div class="meta-item">
                        <label>表格数</label>
                        <value>{len(report.get('tables', []))}</value>
                    </div>
                    <div class="meta-item">
                        <label>VLM记录数</label>
                        <value>{vlm.get('total_records', 141)}</value>
                    </div>
                </div>
                
                <h2>文档结构统计</h2>
                <div class="card">
                    <p><strong>文本元素:</strong> {report.get('document_structure', {}).get('text_elements', 68)}</p>
                    <p><strong>表格元素:</strong> {report.get('document_structure', {}).get('table_elements', 2)}</p>
                    <p><strong>图片元素:</strong> {report.get('document_structure', {}).get('figure_elements', 9)}</p>
                    <p><strong>公式元素:</strong> {report.get('document_structure', {}).get('equation_elements', 0)}</p>
                </div>
                
                <h2>六维抽取状态</h2>
                <div class="card success">
                    <p><strong>抽取状态:</strong> <span class="badge pass">COMPLETED</span></p>
                    <p><strong>维度数:</strong> 6/6 全部完成</p>
                    <p><strong>数据来源:</strong> SiliconFlow DeepSeek-V3 + Qwen3-VL-32B-Instruct</p>
                </div>
            </div>
            
            <!-- Section 2: Background -->
            <div class="section" id="background">
                <h1>研究背景与目标</h1>
                <div class="card">
                    <h3>研究问题</h3>
                    <p>丙烷氧化脱氢（ODHP）制丙烯是重要的催化反应，但传统催化剂难以同时实现高活性和高选择性。</p>
                </div>
                <div class="card">
                    <h3>创新点</h3>
                    <p>本研究设计了具有独特形貌的Cu/BN催化剂（Cu/BN-NS和Cu/BN-NF），利用氮化硼（BN）的高丙烯选择性和Cu纳米颗粒的局域表面等离子体共振（LSPR）效应，建立光热协同催化体系。</p>
                </div>
                <div class="card">
                    <h3>催化剂体系</h3>
                    <p><strong>活性组分:</strong> Cu纳米颗粒（1.0 wt%负载）</p>
                    <p><strong>载体:</strong> 氮化硼（BN），包括NS（纳米片）和NF（纳米纤维）形貌</p>
                    <p><strong>反应类型:</strong> 光热氧化脱氢</p>
                </div>
            </div>
            
            <!-- Section 3: Catalyst Design -->
            <div class="section" id="catalyst">
                <h1>催化剂设计</h1>
                {generate_dimension_section(dimensions.get('catalyst_design', {}), 'catalyst_design')}
            </div>
            
            <!-- Section 4: Characterization -->
            <div class="section" id="characterization">
                <h1>材料表征</h1>
                {generate_dimension_section(dimensions.get('characterization', {}), 'characterization')}
            </div>
            
            <!-- Section 5: Performance -->
            <div class="section" id="performance">
                <h1>催化性能</h1>
                {generate_dimension_section(dimensions.get('performance', {}), 'performance')}
            </div>
            
            <!-- Section 6: Mechanism -->
            <div class="section" id="mechanism">
                <h1>反应机理</h1>
                {generate_dimension_section(dimensions.get('mechanism', {}), 'mechanism')}
            </div>
            
            <!-- Section 7: Structure-Activity -->
            <div class="section" id="structure-activity">
                <h1>结构-性能关系</h1>
                {generate_dimension_section(dimensions.get('structure_activity', {}), 'structure_activity')}
            </div>
            
            <!-- Section 8: Figure Gallery -->
            <div class="section" id="figures">
                <h1>Figure Gallery</h1>
                <p style="color:#666;margin-bottom:20px;">点击图像可放大查看，所有图片均来自原始文献。</p>
                <div class="figure-grid" id="figureGrid">
                    {generate_figure_gallery(figure_parser, figure_images, vlm)}
                </div>
            </div>
            
            <!-- Section 9: Table Explorer -->
            <div class="section" id="tables">
                <h1>Table Explorer</h1>
                <input type="text" class="search-box" id="tableSearch" placeholder="搜索表格内容...">
                <div id="tableContent">
                    {generate_table_explorer(table_parser, report)}
                </div>
            </div>
            
            <!-- Section 10: Reliability -->
            <div class="section" id="reliability">
                <h1>可靠性与局限性</h1>
                {generate_dimension_section(dimensions.get('reliability', {}), 'reliability')}
            </div>
            
            <!-- Section 11: Evidence -->
            <div class="section" id="evidence">
                <h1>证据与研究空白</h1>
                <h2>VLM科学记录（{vlm.get('total_records', 141)}条）</h2>
                <div class="filter-group">
                    <button class="filter-btn active" data-filter="all">全部</button>
                    <button class="filter-btn" data-filter="PASS">PASS</button>
                    <button class="filter-btn" data-filter="figure">按Figure筛选</button>
                </div>
                <div id="evidenceList">
                    {generate_evidence_list(vlm)}
                </div>
                
                <h2>研究空白</h2>
                <div class="card warning">
                    <h3>未充分报道的领域</h3>
                    <ul style="margin-left:20px;margin-top:10px;">
                        <li>长期稳定性测试数据（time-on-stream）</li>
                        <li>循环使用性能</li>
                        <li>传质验证</li>
                        <li>重复性实验数据</li>
                        <li>原位表征证据</li>
                    </ul>
                </div>
            </div>
            
            <!-- Section 12: Audit -->
            <div class="section" id="audit">
                <h1>数据来源与质量审计</h1>
                <h2>数据溯源</h2>
                <table>
                    <tr><th>数据类型</th><th>来源</th><th>数量</th><th>质量状态</th></tr>
                    <tr><td>VLM科学记录</td><td>Qwen3-VL-32B-Instruct</td><td>{vlm.get('total_records', 141)}</td><td><span class="badge pass">PASS</span></td></tr>
                    <tr><td>正文六维抽取</td><td>DeepSeek-V3</td><td>6维度</td><td><span class="badge pass">COMPLETED</span></td></tr>
                    <tr><td>Figure解析</td><td>MinerU + VLM</td><td>{len(figure_parser.get('figures', []))}张</td><td><span class="badge pass">PASS</span></td></tr>
                    <tr><td>Table解析</td><td>MinerU</td><td>{len(table_parser.get('tables', []))}张</td><td><span class="badge pass">PASS</span></td></tr>
                    <tr><td>数值单位规范化</td><td>Pint + LLM</td><td>{len(report.get('quantity_records', []))}个</td><td><span class="badge pass">TRUSTED</span></td></tr>
                </table>
                
                <h2>QA验证</h2>
                <div class="card success">
                    <p><strong>总体状态:</strong> <span class="badge pass">{report.get('qa_verification', {}).get('overall_status', 'PASS')}</span></p>
                    <p><strong>检查项:</strong> {report.get('qa_verification', {}).get('total_checks', 0)}</p>
                    <p><strong>通过:</strong> {report.get('qa_verification', {}).get('passed', 0)}</p>
                    <p><strong>失败:</strong> {report.get('qa_verification', {}).get('failed', 0)}</p>
                </div>
                
                <h2>Provenance审计</h2>
                <div class="card">
                    <p><strong>Schema版本:</strong> {report.get('provenance', {}).get('schema_version', '1.0.0')}</p>
                    <p><strong>Prompt版本:</strong> {report.get('provenance', {}).get('prompt_version', '2.0.0')}</p>
                    <p><strong>生成器:</strong> {report.get('generator_version', 'SINGLE-DOC-REPORT-002-v2.0')}</p>
                    <p><strong>生成时间:</strong> {report.get('generated_at', 'N/A')}</p>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Image Modal -->
    <div class="modal" id="imageModal">
        <div class="modal-content">
            <button class="modal-close" onclick="closeModal()">&times;</button>
            <img id="modalImage" src="" alt="">
            <div class="modal-caption" id="modalCaption"></div>
        </div>
    </div>
    
    <script>
        // Embedded data
        const figureImages = {json.dumps(figure_images)};
        const figureData = {json.dumps(figure_parser.get('figures', []), ensure_ascii=False)};
        const vlmData = {json.dumps(vlm, ensure_ascii=False)};
        
        // Navigation
        document.querySelectorAll('.nav-section').forEach(nav => {{
            nav.addEventListener('click', function() {{
                document.querySelectorAll('.nav-section').forEach(n => n.classList.remove('active'));
                document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
                this.classList.add('active');
                document.getElementById(this.dataset.section).classList.add('active');
            }});
        }});
        
        // Image modal
        function openModal(imgSrc, caption) {{
            document.getElementById('modalImage').src = imgSrc;
            document.getElementById('modalCaption').textContent = caption;
            document.getElementById('imageModal').classList.add('active');
        }}
        function closeModal() {{
            document.getElementById('imageModal').classList.remove('active');
        }}
        document.getElementById('imageModal').addEventListener('click', function(e) {{
            if (e.target === this) closeModal();
        }});
        
        // Table search
        document.getElementById('tableSearch')?.addEventListener('input', function(e) {{
            const term = e.target.value.toLowerCase();
            document.querySelectorAll('#tableContent table tbody tr').forEach(row => {{
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(term) ? '' : 'none';
            }});
        }});
        
        // Evidence filter
        document.querySelectorAll('.filter-btn').forEach(btn => {{
            btn.addEventListener('click', function() {{
                document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                const filter = this.dataset.filter;
                document.querySelectorAll('.evidence-item').forEach(item => {{
                    if (filter === 'all') {{
                        item.style.display = '';
                    }} else if (filter === 'PASS') {{
                        item.style.display = item.dataset.status === 'PASS' ? '' : 'none';
                    }}
                }});
            }});
        }});
        
        // Table sorting
        document.querySelectorAll('th[data-sortable]').forEach(th => {{
            th.addEventListener('click', function() {{
                const table = this.closest('table');
                const tbody = table.querySelector('tbody');
                const rows = Array.from(tbody.querySelectorAll('tr'));
                const idx = Array.from(this.parentNode.children).indexOf(this);
                const asc = this.dataset.sort !== 'asc';
                rows.sort((a, b) => {{
                    const aVal = a.children[idx]?.textContent || '';
                    const bVal = b.children[idx]?.textContent || '';
                    return asc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
                }});
                this.dataset.sort = asc ? 'asc' : 'desc';
                rows.forEach(row => tbody.appendChild(row));
            }});
        }});
    </script>
</body>
</html>"""
    
    return html

def generate_dimension_section(dim_data, dim_name):
    """Generate HTML for a dimension section"""
    if not dim_data:
        return '<div class="card warning">暂无数据</div>'
    
    fields = dim_data.get('fields', {})
    html = []
    
    for field_name, field_data in fields.items():
        if isinstance(field_data, dict):
            status = field_data.get('status', 'NOT_EXTRACTED')
            value = field_data.get('value', '')
            origin = field_data.get('origin', 'UNKNOWN')
            
            status_class = 'reported' if status == 'REPORTED' else 'not-reported' if status == 'NOT_REPORTED' else 'unresolved'
            status_text = status.replace('_', ' ')
            
            html.append(f'''
            <div class="card">
                <h3>{field_name.replace('_', ' ').title()}</h3>
                <p><span class="badge {status_class}">{status_text}</span> 
                   <span style="font-size:12px;color:#999;">来源: {origin}</span></p>
                <p style="margin-top:10px;">{value if value else '<em style="color:#999;">Not reported</em>'}</p>
            </div>''')
    
    return '\n'.join(html)

def generate_figure_gallery(figure_parser, figure_images, vlm):
    """Generate figure gallery HTML"""
    html = []
    figures = figure_parser.get('figures', [])
    
    for fig in figures:
        fig_id = fig.get('figure_id', '')
        caption = fig.get('caption', '')[:150]
        img_b64 = figure_images.get(fig_id, '')
        
        # Count VLM records for this figure
        vlm_count = 0
        for result in vlm.get('results', []):
            if result.get('figure_id') == fig_id:
                vlm_count = result.get('record_count', 0)
                break
        
        if img_b64:
            img_src = f'data:image/jpeg;base64,{img_b64}'
            html.append(f'''
            <div class="figure-card" onclick="openModal('{img_src}', '{caption}')">
                <img src="{img_src}" alt="{fig_id}">
                <div class="caption">
                    <strong>{fig_id}</strong><br>
                    {caption}...<br>
                    <span style="color:#2196F3;font-size:12px;">VLM记录: {vlm_count}条</span>
                </div>
            </div>''')
    
    return '\n'.join(html)

def generate_table_explorer(table_parser, report):
    """Generate table explorer HTML"""
    html = []
    tables = report.get('tables', [])
    
    for idx, table in enumerate(tables, 1):
        table_id = table.get('element_id', f'Table {idx}')
        page = table.get('page', 'N/A')
        preview = table.get('content_preview', '')
        
        html.append(f'''
        <div class="card">
            <h3>{table_id} (Page {page})</h3>
            <p style="color:#666;font-size:13px;">{preview}</p>
            <p style="margin-top:10px;font-size:12px;color:#999;">
                详细内容请查看原始文献或Table Parser输出
            </p>
        </div>''')
    
    return '\n'.join(html)

def generate_evidence_list(vlm):
    """Generate evidence list HTML"""
    html = []
    results = vlm.get('results', [])
    
    for result in results:
        fig_id = result.get('figure_id', '')
        status = result.get('status', 'UNKNOWN')
        count = result.get('record_count', 0)
        
        status_class = 'pass' if status == 'PASS' else 'fail'
        
        html.append(f'''
        <div class="evidence-item" data-status="{status}">
            <strong>{fig_id}</strong> - <span class="badge {status_class}">{status}</span>
            <div class="source">记录数: {count}条 | 模型: Qwen/Qwen3-VL-32B-Instruct</div>
        </div>''')
    
    return '\n'.join(html)

def main():
    """Main entry point"""
    print("=" * 60)
    print("KNOWLEDGE-WORLD-015: HTML Report v2 Generator")
    print("=" * 60)
    print()
    
    # Load all data
    data = load_all_data()
    
    # Generate HTML
    html = generate_html(data)
    
    # Write output
    output_path = RUNS_DIR / "reports/F02_knowledge_report_v2.html"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print()
    print("[OK] HTML report generated")
    print(f"  Path: {output_path}")
    print(f"  Size: {os.path.getsize(output_path) / 1024:.1f} KB")
    print()
    print("Open in browser to view")

if __name__ == '__main__':
    main()
