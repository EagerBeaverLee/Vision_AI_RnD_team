import json
import uuid
import pandas as pd
import movingpandas as mpd
import holoviews as hv
import hvplot.pandas
import duckdb
import geopandas as gpd
import threading
import io
from typing import Any, Dict, List
from bokeh.embed import file_html
from bokeh.resources import INLINE
from my_battlefield_crew.chainlit_app.schemas import SimulationContext

# GeoViews / Cartopy / PyProj의 전역 C 캐시 스레드 경합 방지용 락
_MAP_RENDER_LOCK = threading.Lock()

def generate_unusual_ships_widget_two(unusual_ships_data: List[Dict[str, Any]]) -> str:
    """특이 기동 선박 데이터 리스트를 받아 인터랙티브 HTML 테이블 문자열을 반환"""
    safe_json = json.dumps(unusual_ships_data, ensure_ascii=False).replace("</", "<\\/")

    print("#"*15 + "시각화 직전 unusual 리스트" + "#"*15)
    print(safe_json)
    print("#"*55)

    html_template = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<style>
    * {{
        box-sizing: border-box;
    }}
    html, body {{
        height: 100%;
        margin: 0;
        padding: 12px;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        background-color: #0E1117;
        color: #E2E8F0;
        font-size: 13px;
        display: flex;
        flex-direction: column;
        overflow: hidden;
    }}
    .header {{
        flex-shrink: 0;
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-weight: bold;
        font-size: 14px;
        margin-bottom: 10px;
        color: #38BDF8;
    }}
    .total-badge {{
        background: #1E293B;
        color: #94A3B8;
        font-size: 11px;
        padding: 2px 8px;
        border-radius: 10px;
        font-weight: normal;
    }}
    .controls {{
        flex-shrink: 0;
        width: 100%;
        margin-bottom: 10px;
    }}
    .search-input {{
        width: 100%;
        background: #1E293B;
        border: 1px solid #334155;
        color: #fff;
        padding: 7px 12px;
        border-radius: 6px;
        font-size: 12px;
        outline: none;
    }}
    .search-input:focus {{
        border-color: #38BDF8;
    }}
    .table-container {{
        flex: 1;
        min-height: 0;
        overflow-y: auto;
        border: 1px solid #334155;
        border-radius: 6px;
    }}
    table {{
        width: 100%;
        border-collapse: collapse;
        text-align: left;
    }}
    th {{
        background: #1E293B;
        padding: 8px 10px;
        position: sticky;
        top: 0;
        z-index: 1;
        font-weight: 600;
        color: #94A3B8;
        font-size: 12px;
        white-space: nowrap;
    }}
    td {{
        padding: 8px 10px;
        border-bottom: 1px solid #1E293B;
        font-size: 12px;
        vertical-align: middle;
    }}
    tbody tr:last-child td {{
        padding-bottom: 16px;
        border-bottom: none;
    }}
    tr:hover {{
        background-color: #162032;
    }}
    .ship-name {{
        font-weight: 600;
        color: #F8FAFC;
        white-space: nowrap;
    }}
    .count-badge {{
        display: inline-block;
        padding: 2px 8px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 11px;
        text-align: center;
        min-width: 28px;
    }}
    .turn-high {{
        background: rgba(245, 158, 11, 0.18);
        color: #FBBF24;
        border: 1px solid rgba(245, 158, 11, 0.4);
    }}
    .turn-norm {{
        background: rgba(56, 189, 248, 0.15);
        color: #38BDF8;
    }}
    .speed-high {{
        background: rgba(244, 63, 94, 0.18);
        color: #FB7185;
        border: 1px solid rgba(244, 63, 94, 0.4);
    }}
    .speed-norm {{
        background: #1E293B;
        color: #94A3B8;
    }}
    .status-flow {{
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 4px;
        line-height: 1.4;
    }}
    .status-chip {{
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 11px;
        white-space: nowrap;
        background: #1E293B;
        color: #CBD5E1;
        border: 1px solid #334155;
    }}
    .chip-turn {{
        background: rgba(245, 158, 11, 0.12);
        color: #FCD34D;
        border-color: rgba(245, 158, 11, 0.35);
    }}
    .chip-speed {{
        background: rgba(168, 85, 247, 0.15);
        color: #D8B4FE;
        border-color: rgba(168, 85, 247, 0.35);
    }}
    .arrow {{
        color: #475569;
        font-size: 10px;
    }}
    ::-webkit-scrollbar {{
        width: 6px;
        height: 6px;
    }}
    ::-webkit-scrollbar-thumb {{
        background: #475569;
        border-radius: 3px;
    }}
</style>
</head>
<body>
    <div class="header">
        <span>⚠️ 특이 기동 선박 상세 목록</span>
        <span class="total-badge" id="countBadge">총 0척</span>
    </div>
    <div class="controls">
        <input type="text" id="searchInput" class="search-input" placeholder="🔍 함정명 또는 기동 상태(예: 좌선회, 우선회, 가속, 감속, 정박) 검색" oninput="updateTable()">
    </div>
    <div class="table-container">
        <table>
            <thead>
                <tr>
                    <th>함정명</th>
                    <th style="text-align:center;">변침 횟수</th>
                    <th style="text-align:center;">속도 변화</th>
                    <th>기동 상태 변화 이력</th>
                </tr>
            </thead>
            <tbody id="tableBody"></tbody>
        </table>
    </div>

<script>
    const rawData = {safe_json};

    function getChipClass(statusText) {{
        if (statusText.includes("좌선회") || statusText.includes("우선회")) return "status-chip chip-turn";
        if (statusText.includes("가속") || statusText.includes("감속")) return "status-chip chip-speed";
        return "status-chip";
    }}

    function updateTable() {{
        const query = document.getElementById('searchInput').value.trim().toLowerCase();

        const filtered = rawData.filter(row => {{
            if (!query) return true;
            const nameMatch = String(row.ShipName || '').toLowerCase().includes(query);
            const statusMatch = (row.status_list || []).some(s => String(s).toLowerCase().includes(query));
            return nameMatch || statusMatch;
        }});

        document.getElementById('countBadge').textContent = `표시 ${{filtered.length}}척 / 전체 ${{rawData.length}}척`;

        const tbody = document.getElementById('tableBody');
        tbody.innerHTML = '';

        if (filtered.length === 0) {{
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:#64748B; padding:20px;">조건에 일치하는 특이 기동 선박이 없습니다.</td></tr>';
            return;
        }}

        filtered.forEach(row => {{
            const tr = document.createElement('tr');
            const turnCount = Number(row.turn_count || 0);
            const speedCount = Number(row.speed_change_count || 0);
            const statuses = Array.isArray(row.status_list) ? row.status_list : [];

            const turnClass = turnCount >= 4 ? 'count-badge turn-high' : 'count-badge turn-norm';
            const speedClass = speedCount >= 3 ? 'count-badge speed-high' : 'count-badge speed-norm';

            const flowHtml = statuses.map((st, idx) => {{
                const cleanText = String(st).replace(/\\s+/g, ' ').trim();
                const chip = `<span class="${{getChipClass(cleanText)}}">${{cleanText}}</span>`;
                return idx < statuses.length - 1 ? chip + '<span class="arrow">▶</span>' : chip;
            }}).join('');

            tr.innerHTML = `
                <td class="ship-name">${{row.ShipName || '-'}}</td>
                <td style="text-align:center;"><span class="${{turnClass}}">${{turnCount}}회</span></td>
                <td style="text-align:center;"><span class="${{speedClass}}">${{speedCount}}회</span></td>
                <td><div class="status-flow">${{flowHtml}}</div></td>
            `;
            tbody.appendChild(tr);
        }});
    }}

    updateTable();
</script>
</body>
</html>"""

    return html_template

def generate_unusual_ships_widget(unusual_ships_data: List[Dict[str, Any]]) -> str:
    """특이 기동 선박 데이터 리스트를 받아 인터랙티브 HTML 테이블 문자열을 반환"""
    # Python 데이터를 안전한 JSON 문자열로 직렬화 (스크립트 닫힘 태그 방지 포함)
    safe_json = json.dumps(unusual_ships_data, ensure_ascii=False).replace("</", "<\\/")

    html_template = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<style>
    body {{
        margin: 0; padding: 12px;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        background-color: #0E1117; color: #E2E8F0; font-size: 13px;
    }}
    .header {{
        display: flex; justify-content: space-between; align-items: center;
        font-weight: bold; font-size: 14px; margin-bottom: 10px; color: #38BDF8;
    }}
    .total-badge {{
        background: #1E293B; color: #94A3B8; font-size: 11px;
        padding: 2px 8px; border-radius: 10px; font-weight: normal;
    }}
    .controls {{
        display: flex; gap: 10px; align-items: center; margin-bottom: 10px; flex-wrap: wrap;
    }}
    .radio-group {{
        display: flex; gap: 10px; background: #1E293B; padding: 5px 10px; border-radius: 6px;
    }}
    .radio-label {{
        cursor: pointer; display: flex; align-items: center; gap: 4px; font-size: 12px; color: #CBD5E1;
    }}
    .search-input {{
        flex: 1; min-width: 180px; background: #1E293B; border: 1px solid #334155;
        color: #fff; padding: 5px 10px; border-radius: 6px; font-size: 12px; outline: none;
    }}
    .search-input:focus {{ border-color: #38BDF8; }}
    .table-container {{
        flex: 1; overflow-y: auto; border: 1px solid #334155; border-radius: 6px;
    }}
    table {{ width: 100%; border-collapse: collapse; text-align: left; }}
    th {{
        background: #1E293B; padding: 8px 10px; position: sticky; top: 0; z-index: 1;
        font-weight: 600; color: #94A3B8; font-size: 12px; white-space: nowrap;
    }}
    td {{
        padding: 8px 10px; border-bottom: 1px solid #1E293B; font-size: 12px; vertical-align: middle;
    }}
    tr:hover {{ background-color: #162032; }}
    .ship-name {{ font-weight: 600; color: #F8FAFC; white-space: nowrap; }}
    .count-badge {{
        display: inline-block; padding: 2px 8px; border-radius: 12px;
        font-weight: 600; font-size: 11px; text-align: center; min-width: 28px;
    }}
    .turn-high {{ background: rgba(245, 158, 11, 0.18); color: #FBBF24; border: 1px solid rgba(245, 158, 11, 0.4); }}
    .turn-norm {{ background: rgba(56, 189, 248, 0.15); color: #38BDF8; }}
    .speed-high {{ background: rgba(244, 63, 94, 0.18); color: #FB7185; border: 1px solid rgba(244, 63, 94, 0.4); }}
    .speed-norm {{ background: #1E293B; color: #94A3B8; }}
    .status-flow {{
        display: flex; flex-wrap: wrap; align-items: center; gap: 4px; line-height: 1.4;
    }}
    .status-chip {{
        padding: 2px 6px; border-radius: 4px; font-size: 11px; white-space: nowrap;
        background: #1E293B; color: #CBD5E1; border: 1px solid #334155;
    }}
    .chip-turn {{ background: rgba(245, 158, 11, 0.12); color: #FCD34D; border-color: rgba(245, 158, 11, 0.35); }}
    .chip-speed {{ background: rgba(168, 85, 247, 0.15); color: #D8B4FE; border-color: rgba(168, 85, 247, 0.35); }}
    .arrow {{ color: #475569; font-size: 10px; }}
    ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
    ::-webkit-scrollbar-thumb {{ background: #475569; border-radius: 3px; }}
</style>
</head>
<body>
    <div class="header">
        <span>⚠️ 특이 기동 선박 상세 목록</span>
        <span class="total-badge" id="countBadge">총 0척</span>
    </div>
    <div class="controls">
        <div class="radio-group">
            <label class="radio-label"><input type="radio" name="filterType" value="all" checked onchange="updateTable()"> 전체</label>
            <label class="radio-label"><input type="radio" name="filterType" value="highTurn" onchange="updateTable()"> 다빈도 변침 (4회↑)</label>
            <label class="radio-label"><input type="radio" name="filterType" value="speedChange" onchange="updateTable()"> 속도 변화 포함</label>
        </div>
        <input type="text" id="searchInput" class="search-input" placeholder="🔍 함정명 또는 기동 상태(예: 좌선회, 감속) 검색" oninput="updateTable()">
    </div>
    <div class="table-container">
        <table>
            <thead>
                <tr>
                    <th>함정명</th>
                    <th style="text-align:center;">변침 횟수</th>
                    <th style="text-align:center;">속도 변화</th>
                    <th>기동 상태 변화 이력</th>
                </tr>
            </thead>
            <tbody id="tableBody"></tbody>
        </table>
    </div>

<script>
    const rawData = {safe_json};

    function getChipClass(statusText) {{
        if (statusText.includes("좌선회") || statusText.includes("우선회")) return "status-chip chip-turn";
        if (statusText.includes("가속") || statusText.includes("감속")) return "status-chip chip-speed";
        return "status-chip";
    }}

    function updateTable() {{
        const filterType = document.querySelector('input[name="filterType"]:checked').value;
        const query = document.getElementById('searchInput').value.trim().toLowerCase();

        const filtered = rawData.filter(row => {{
            const turnCount = Number(row.turn_count || 0);
            const speedCount = Number(row.speed_change_count || 0);

            if (filterType === "highTurn" && turnCount < 4) return false;
            if (filterType === "speedChange" && speedCount === 0) return false;

            if (!query) return true;
            const nameMatch = String(row.ShipName || '').toLowerCase().includes(query);
            const statusMatch = (row.status_list || []).some(s => String(s).toLowerCase().includes(query));
            return nameMatch || statusMatch;
        }});

        document.getElementById('countBadge').textContent = `표시 ${{filtered.length}}척 / 전체 ${{rawData.length}}척`;

        const tbody = document.getElementById('tableBody');
        tbody.innerHTML = '';

        if (filtered.length === 0) {{
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:#64748B; padding:20px;">조건에 일치하는 특이 기동 선박이 없습니다.</td></tr>';
            return;
        }}

        filtered.forEach(row => {{
            const tr = document.createElement('tr');
            const turnCount = Number(row.turn_count || 0);
            const speedCount = Number(row.speed_change_count || 0);
            const statuses = Array.isArray(row.status_list) ? row.status_list : [];

            const turnClass = turnCount >= 4 ? 'count-badge turn-high' : 'count-badge turn-norm';
            const speedClass = speedCount >= 3 ? 'count-badge speed-high' : 'count-badge speed-norm';

            const flowHtml = statuses.map((st, idx) => {{
                const cleanText = String(st).replace(/\\s+/g, ' ').trim();
                const chip = `<span class="${{getChipClass(cleanText)}}">${{cleanText}}</span>`;
                return idx < statuses.length - 1 ? chip + '<span class="arrow">▶</span>' : chip;
            }}).join('');

            tr.innerHTML = `
                <td class="ship-name">${{row.ShipName || '-'}}</td>
                <td style="text-align:center;"><span class="${{turnClass}}">${{turnCount}}회</span></td>
                <td style="text-align:center;"><span class="${{speedClass}}">${{speedCount}}회</span></td>
                <td><div class="status-flow">${{flowHtml}}</div></td>
            `;
            tbody.appendChild(tr);
        }});
    }}

    updateTable();
</script>
</body>
</html>"""

    return html_template

def generate_ship_table_widget(ship_data_dict: dict[str, pd.DataFrame]) -> str:
    """ship_data_dict를 받아 순수 HTML/JS로 동작하는 반응형 테이블 위젯을 생성하고

    메모리 라우트 URL을 반환합니다.
    """
    json_payload = json.dumps(ship_data_dict, ensure_ascii=False)

    # 2. 외부 라이브러리(CDN) 전혀 없는 100% 오프라인 다크테마 HTML/JS 조립
    html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<style>
    html, body {{
        height: 100%;
        box-sizing: border-box;
        margin: 0; padding: 12px;
        display: flex; flex-direction: column; /* 세로 배치 */
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        background-color: #0E1117; color: #E2E8F0; font-size: 13px;
        overflow: hidden;
    }}
    .header {{
        display: flex; justify-content: space-between; align-items: center;
        font-weight: bold; font-size: 14px; margin-bottom: 10px; color: #38BDF8;
    }}
    .total-badge {{
        background: #1E293B; color: #94A3B8; font-size: 11px;
        padding: 2px 8px; border-radius: 10px; font-weight: normal;
    }}
    .controls {{ display: flex; gap: 12px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }}
    .radio-group {{ display: flex; gap: 10px; background: #1E293B; padding: 4px 8px; border-radius: 6px; }}
    .radio-label {{ cursor: pointer; display: flex; align-items: center; gap: 4px; font-size: 12px; }}
    .search-input {{
        flex: 1; min-width: 160px; background: #1E293B; border: 1px solid #334155;
        color: #fff; padding: 5px 8px; border-radius: 6px; font-size: 12px; outline: none;
    }}
    .search-input:focus {{ border-color: #38BDF8; }}
    .table-container {{
        flex 1; overflow-y: auto; border: 1px solid #334155; border-radius: 6px;
    }}
    table {{ width: 100%; border-collapse: collapse; text-align: left; }}
    th {{ background: #1E293B; padding: 8px; position: sticky; top: 0; font-weight: 600; color: #94A3B8; font-size: 12px; }}
    td {{ padding: 6px 8px; border-bottom: 1px solid #1E293B; font-size: 12px; }}
    tr:hover {{ background-color: #1E293B; }}
    /* 스크롤바 디자인 */
    ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
    ::-webkit-scrollbar-thumb {{ background: #475569; border-radius: 3px; }}
</style>
</head>
<body>
    <div class="header">
        <span>📋 함정 상세 목록</span>
        <span class="total-badge" id="countBadge">총 0척</span>
    </div>
    <div class="controls">
        <div class="radio-group">
            <label class="radio-label"><input type="radio" name="status" value="순항" checked onchange="updateTable()"> 순항</label>
            <label class="radio-label"><input type="radio" name="status" value="정박" onchange="updateTable()"> 정박</label>
            <label class="radio-label"><input type="radio" name="status" value="저속운항" onchange="updateTable()"> 저속운항</label>
        </div>
        <input type="text" id="searchInput" class="search-input" placeholder="🔍 함정명 또는 MMSI 검색" oninput="updateTable()">
    </div>
    <div class="table-container">
        <table id="shipTable">
            <thead>
                <tr id="tableHeader"></tr>
            </thead>
            <tbody id="tableBody"></tbody>
        </table>
    </div>

<script>
    const rawData = {json_payload};

    function updateTable() {{
        const status = document.querySelector('input[name="status"]:checked').value;
        const query = document.getElementById('searchInput').value.trim().toLowerCase();
        const records = rawData[status] || [];

        // 검색어 필터링 (ShipName or MMSI)
        const filtered = records.filter(row => {{
            const name = String(row.ShipName || '').toLowerCase();
            const mmsi = String(row.mmsi || '').toLowerCase();
            return name.includes(query) || mmsi.includes(query);
        }});

        // 상단 카운트 뱃지 업데이트 (현재 선택된 기동 상태 탭 기준)
        document.getElementById('countBadge').textContent = `표시 ${{filtered.length}}척 / 전체 ${{records.length}}척`;

        // 헤더 구성
        const headerTr = document.getElementById('tableHeader');
        headerTr.innerHTML = '';
        if (records.length > 0) {{
            Object.keys(records[0]).forEach(key => {{
                const th = document.createElement('th');
                th.textContent = key;
                headerTr.appendChild(th);
            }});
        }}

        // 본문 렌더링
        const tbody = document.getElementById('tableBody');
        tbody.innerHTML = '';
        if (filtered.length === 0) {{
            tbody.innerHTML = '<tr><td colspan="10" style="text-align:center; color:#64748B; padding:16px;">조회된 데이터가 없습니다.</td></tr>';
            return;
        }}

        filtered.forEach(row => {{
            const tr = document.createElement('tr');
            Object.values(row).forEach(val => {{
                const td = document.createElement('td');
                td.textContent = (val !== null && val !== undefined) ? val : '-';
                tr.appendChild(td);
            }});
            tbody.appendChild(tr);
        }});
    }}

    // 초기 실행
    updateTable();
</script>
</body>
</html>"""
    
    return html_content

def render_major_ports_map(i, port_name, plot_port_gdf, p_anchored, p_departures, p_arrivals, port_html_list):
    # 해당 항구 범위 계산 (줌인용) ---
    bounds = plot_port_gdf.geometry.total_bounds
    margin = 5000  # 개별 항구 줌인이므로 마진을 작게 설정

    p_xlim = (bounds[0] - margin, bounds[2] + margin)
    p_ylim = (bounds[1] - margin, bounds[3] + margin)

    # --- 개별 항구 레이어 생성 ---
    layers = []
    renderer = hv.renderer('bokeh')

    try:
        # 배경 지도 및 항구 폴리곤 (가장 아래)
        layers.append(plot_port_gdf.hvplot(
            # title=f"{port_name} 현황",
            color='red',
            alpha=0.2,
            geo=False,
            tiles='EsriImagery',
            xlim=p_xlim,
            ylim=p_ylim, 
            frame_width=320,
            frame_height=300,
            title=f"{port_name}"
        ))
    except Exception as e:
        import traceback
        print(f"[Port {i}] single_port_gdf 렌더링 오류:")
        traceback.print_exc()
    
    # 출발 항적
    if p_departures:
        try:
            dep_tc = mpd.TrajectoryCollection(p_departures).to_line_gdf().to_crs(epsg=3857).set_crs(None, allow_override=True)
            layers.append(dep_tc.hvplot(
                color="blue", label="출발", line_width=2, tiles=False, geo=False
            ))
        except Exception as e:
            print(f"[Port {i}] p_departures 오류: {e}")
    
    # 도착 항적 (tiles 제거, geo=True 명시)
    if p_arrivals:
        try:
            arr_tc = mpd.TrajectoryCollection(p_arrivals).to_line_gdf().to_crs(epsg=3857).set_crs(None, allow_override=True)
            layers.append(arr_tc.hvplot(
                color="orange", label="도착", line_width=2, tiles=False, geo=False
            ))
        except Exception as e:
            print(f"[Port {i}] p_arrivals 오류: {e}")
    
    # 정박 포인트
    if not p_anchored.empty:
        try:
            plot_anchored = p_anchored.to_crs(epsg=3857).set_crs(None, allow_override=True)
            layers.append(plot_anchored.hvplot.points(
                color='red', label="정박/대기", geo=False, size=5
            ))
        except Exception as e:
            print(f"[Port {i}] p_anchored 오류: {e}")

    if not layers:
        print(f"[Port {i}] 렌더링 가능한 레이어가 없어 지도를 건너뜁니다.")
        return

    res_plot = hv.Overlay(layers).opts(
        xaxis=None, 
        yaxis=None, 
        show_legend=False,
        bgcolor='#0E1117',
        default_tools=[],  # 드래그·휠 줌 기능 자체를 완전히 비활성화
        active_tools=[],
        toolbar=None,       # 툴바 탭(UI) 숨김
        # 에러가 났던 border_fill_color 대신 hooks를 사용하여 Bokeh 모델을 직접 수정
        hooks=[lambda plot, element: (
            setattr(plot.state, 'border_fill_color', '#0E1117'),
            setattr(plot.state.title, 'text_color', "#B8F7B9")
        )]
    )

    plot_state = renderer.get_plot(res_plot).state

    # 레이아웃 최적화
    plot_state.sizing_mode = 'stretch_both'

    # Bokeh의 file_html을 사용하여 HTML 문자열 생성
    html_content = file_html(plot_state, INLINE, f"Port {i}")

    # --- 항구별 오버레이 합체 후 리스트에 저장 ---
    port_html_list.append(html_content)
    

def speed_processing(context: SimulationContext):
    con = duckdb.connect(database=':memory:')
    con.execute("INSTALL spatial; LOAD spatial;")

    con.execute(f"ATTACH '{context.realtime_db_path}' AS sqlite_db (TYPE sqlite, READ_ONLY);")
    con.execute("USE sqlite_db;")
    

    # 2. 기준 구역(zones_gdf)을 DuckDB에 등록
    # 공간 조인을 위해 zones_gdf를 WKB로 변환하여 임시 테이블로 등록합니다.
    context.processing_list["zone_gdf"]['geom_wkb'] = context.processing_list["zone_gdf"]['geometry'].to_wkb()
    con.register('v_zones', context.processing_list["zone_gdf"][['name', 'geom_wkb']])

    # 3. DuckDB 통합 쿼리 (필터링 + 공간 조인 + 통계 요약)
    # 포인트 생성부터 구역 매칭, 평균/최대 속도 계산까지 SQL 한 번에 처리합니다.
    min_lon, max_lon, max_lat = 125.678, 131.229, 36.001

    integrated_query = f"""
        WITH filtered_ais AS (
            -- [단계 1] 기본 필터링 및 포인트 생성
            SELECT 
                speed,
                ST_Point(longitude, latitude) as point_geom
            FROM ship_logs
            WHERE longitude BETWEEN {min_lon} AND {max_lon}
            AND latitude <= {max_lat}
            AND timestamp >= '{context.time.start_time}' 
            AND timestamp <= '{context.time.end_time}'
            AND speed > 0
        ),
        joined_data AS (
            -- [단계 2] 구역 테이블(v_zones)과 공간 조인 (ST_Within)
            -- INNER JOIN을 통해 구역에 속하지 않은(NaN이 될) 데이터는 자동 필터링됩니다.
            SELECT 
                z.name,
                a.speed
            FROM filtered_ais a
            JOIN v_zones z ON ST_Within(a.point_geom, ST_GeomFromWKB(z.geom_wkb))
        )
        -- [단계 3] 구역별 속도 통계 산출
        SELECT 
            name,
            AVG(speed) as mean,
            MAX(speed) as max,
            COUNT(*) as count
        FROM joined_data
        GROUP BY name
        ORDER BY name ASC
    """

    # 4. 결과 실행 및 JSON 변환
    # 데이터 요약본만 파이썬으로 넘어오므로 매우 가볍습니다.
    speed_stats_df = con.execute(integrated_query).df()
    return speed_stats_df

def render_od_flow_map(context: SimulationContext):
    aggregator = context.processing_list.get("aggregator")
    flows = aggregator.get_flows_gdf()
    clusters = aggregator.get_clusters_gdf()

    zones_gdf = context.processing_list.get("zone_gdf").copy()
    zone_speed_stats = context.processing_list.get("speed_df")

    if zone_speed_stats is None:
        zone_speed_stats = speed_processing(context=context)
    
    
    # DuckDB 인메모리 조인 (with문으로 연결 자동 정리)
    with duckdb.connect(database=':memory:') as con:
        con.execute("INSTALL spatial; LOAD spatial;")        
        con.register('v_speed_stats', zone_speed_stats)    
        zones_gdf['geom_wkb'] = zones_gdf['geometry'].to_wkb()
        con.register('v_zones', zones_gdf[['name', 'geom_wkb']])
    
        final_viz_query = """
            SELECT 
                z.name,
                z.geom_wkb,
                CAST(s.mean AS DOUBLE) as mean,
                s.max,
                s.count
            FROM v_zones z
            INNER JOIN v_speed_stats s ON z.name = s.name
            ORDER BY s.mean DESC
        """
    
        # 4. 결과 실행 및 GeoDataFrame 복원
        viz_df = con.execute(final_viz_query).df()

    # DuckDB에서 가져온 WKB를 다시 Shapely geometry로 변환 (GeoPandas 최적화)
    zones_plot_data = gpd.GeoDataFrame(
        viz_df,
        geometry=gpd.GeoSeries.from_wkb(viz_df['geom_wkb'].apply(bytes)),   # bytearray 데이터 처리
        crs="EPSG:4326"
    ).drop(columns=['geom_wkb'])

    #################################################
    ## 최적화된 시각화 실행 (전달받은 viz_df 사용)
    #################################################

    with _MAP_RENDER_LOCK:
        renderer = hv.renderer("bokeh")

        # 해상구역 배경 (평균 속도 기반 채색)
        zones_speed = zones_plot_data.hvplot(
            geo=True, tiles="EsriImagery", alpha=0.45, c="mean",
            colorbar=False,
            # clabel="Avg Speed (knots)",
            line_color='black', line_width=1,
            cmap='YlOrRd', 
            hover_cols=['name', 'mean', 'count'], # mean_knots 대신 mean 사용
            frame_height=300, frame_width=520, legend=False,
            responsive=True # 이전의 레이아웃 어긋남 방지
        )

        # 2. 레이어 통합
        flow_cluster_map = (zones_speed * flows.hvplot(geo=True, hover_cols=['weight'], line_width='weight', alpha=0.5, color='#00FFFF') * clusters.hvplot(geo=True, color='red', size='n')
        ).opts(
            # title='Integrated Analysis: OD Flows, Avg Speed & Clusters',
            xaxis=None,            # x축 전체 숨기기
            yaxis=None,            # y축 전체 숨기기
            show_legend=False,     # 범례 숨기기
            bgcolor='#0E1117',
            default_tools=[],  # 드래그·휠 줌 기능 자체를 완전히 비활성화
            active_tools=[],
            toolbar=None,       # 툴바 탭(UI) 숨김
            # 에러가 났던 border_fill_color 대신 hooks를 사용하여 Bokeh 모델을 직접 수정
            hooks=[lambda plot, element: (
                setattr(plot.state, 'border_fill_color', '#0E1117'),
                setattr(plot.state.title, 'text_color', 'white')
            )]
        )

        plot_state = renderer.get_plot(flow_cluster_map).state
        plot_state.sizing_mode = 'stretch_both' # 레이아웃 최적화

        # 3. Bokeh의 file_html을 사용하여 HTML 문자열 생성
        html_content = file_html(plot_state, INLINE, "OD Flow Map")

    return html_content

def generate_direction_hist_widget(context: SimulationContext):
    ais_gdf = context.processing_list["ais_gdf"]
    tc = mpd.TrajectoryCollection(ais_gdf, traj_id_col='mmsi', t="start_time")
    traj = tc.trajectories[0]

    # 1. 히스토그램 생성
    hist = pd.DataFrame(traj.df).hvplot.hist(
        "course",
        bin_range=(0, 360),
        xlim=(0, 360),
        title="Histogram of direction",
        bins=90,
        color="#B8F7B9",
        line_color="#0E1117",
        responsive=True,
    )

    # 2. 90, 180, 270도 세로선 + 텍스트 레이블 한 번에 생성
    max_y = hist.range(1)[1] or 1  # y축 최댓값 자동 계산

    # 2. 90도마다 세로 빨간 선 생성 (90, 180, 270)
    vlines = hv.Overlay([
        hv.VLine(x).opts(
            color="#FF4B4B",      # 다크 배경에 잘 보이는 빨간색 (원하는 색상코드로 변경 가능)
            line_width=1,       # 선 두께
            line_dash="dashed"
        ) * 
        hv.Text(x + 2, max_y * 1.05, f"{x}°").opts(color="#FF4B4B", text_align="left", text_font_size="8pt")
        for x in [90, 180, 270]   # 양 끝(0, 360)까지 포함하려면 [0, 90, 180, 270, 360]
    ])

    plot = (hist * vlines).opts(
        bgcolor="#0E1117",   # 1. 그래프 안쪽(캔버스) 배경색
        default_tools=[],  # 드래그·휠 줌 기능 자체를 완전히 비활성화
        toolbar=None,       # 툴바 탭(UI) 숨김
        active_tools=[],
        hooks=[lambda plot, element: (
            setattr(plot.state, 'border_fill_color', '#0E1117'),       # 2. 바깥쪽 여백 배경색
            setattr(plot.state, 'background_fill_color', '#0E1117'),   # 3. 안쪽 배경색 강제 적용
            setattr(plot.state, 'outline_line_color', "#B8F7B9"),   # 차트 영역 사각 테두리
            setattr(plot.state.title, 'text_color', "#B8F7B9"),          # 4. 제목 글자색
            [
                setattr(ax, prop, "#B8F7B9")
                for ax in (plot.state.xaxis, plot.state.yaxis)
                for prop in (
                    'axis_line_color',
                    'major_tick_line_color',
                    'minor_tick_line_color',
                    'major_label_text_color',
                    'axis_label_text_color',
                )
            ],

            setattr(plot.state.xaxis, 'axis_line_color', "#B8F7B9"),
            setattr(plot.state.yaxis, 'axis_line_color', "#B8F7B9"),
            setattr(plot.state.xaxis, 'major_label_text_color', "#B8F7B9"),
            setattr(plot.state.xaxis, 'major_tick_line_color', "#B8F7B9"),
            setattr(plot.state.xaxis, 'minor_tick_line_color', "#B8F7B9"),
            setattr(plot.state.yaxis, 'major_label_text_color', "#B8F7B9"),
            setattr(plot.state.yaxis, 'major_tick_line_color', "#B8F7B9"),
            setattr(plot.state.yaxis, 'minor_tick_line_color', "#B8F7B9"),
            setattr(plot.state.xaxis, 'axis_label_text_color', "#B8F7B9"),
            setattr(plot.state.yaxis, 'axis_label_text_color', "#B8F7B9"),
            
        )]
    )

    bokeh_plot = hv.render(plot)

    html_content = file_html(bokeh_plot, INLINE, "Histogram")

    return html_content

def generate_direction_map_widget(context: SimulationContext):
    ais_gdf = context.processing_list["ais_gdf"]
    ais_gdf["dir_class"] = (((ais_gdf["course"] + 45) // 90) % 4)
    temp = ais_gdf.to_crs(epsg=3857)
    temp["mx"] = temp.geometry.x
    temp["my"] = temp.geometry.y

    # 2. 다크 테마 적용 훅
    def apply_dark_map(plot, element):
        p = plot.state
        p.border_fill_color = '#0E1117'
        p.background_fill_color = '#0E1117'
        p.outline_line_color = '#0E1117'
        if p.title:
            p.title.text_color = "#B8F7B9"
        # p.toolbar_location = None

    # 3. 4방위별 지도 리스트 생성
    plots = [
        temp[temp["dir_class"] == i].hvplot.points(
            x="mx", y="my",
            tiles="EsriImagery",
            # tiles="OSM",
            color="#B8F7B9",
            size=2,
            width=340,
            height=280,
            title=f"{int(i * 90)}° ~ {int((i + 1) * 90) - 1}°",
        ).opts(
            bgcolor="#0E1117",
            xaxis=None,            # x축 전체 숨기기
            yaxis=None,            # y축 전체 숨기기
            hooks=[apply_dark_map],
        )
        for i in sorted(temp["dir_class"].unique())
    ]

    # 4. 2x2 격자(한 줄에 2개씩) 또는 1x4 가로 배치(.cols(4))
    dir_layout = hv.Layout(plots).cols(2).opts(
        hv.opts.Tiles(default_tools=[], active_tools=[]),
        hv.opts.Points(default_tools=[], active_tools=[]),
        hv.opts.Overlay(default_tools=[], active_tools=[]),
        hv.opts.Layout(merge_tools=False),
    )

    # 5. 메모리(StringIO)로 HTML 저장
    buf = io.StringIO()
    hvplot.save(dir_layout, buf, resources=INLINE, toolbar=False)
    html_val = buf.getvalue()

    dark_css = """
<style>
html, body, .bk-root {
background-color: #0E1117 !important;
margin: 0 !important;
padding: 4px !important;
overflow-x: hidden;
}
</style>
"""
    
    html_content = html_val.replace("</head>", f"{dark_css}</head>")
    return html_content

