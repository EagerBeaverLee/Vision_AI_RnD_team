import duckdb
import asyncio
from crewai.tools import tool
import json
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from my_battlefield_crew.chainlit_app.schemas import SimulationContext
from my_battlefield_crew.engine.preprocessor import compress_ship_data_duckdb_further

def generate_ship_table_widget(ship_data_dict: dict[str, pd.DataFrame]) -> str:
    """ship_data_dict를 받아 순수 HTML/JS로 동작하는 반응형 테이블 위젯을 생성하고

    메모리 라우트 URL을 반환합니다.
    """
    # 1. 각 상태별 데이터프레임을 JSON 직렬화가 가능한 dict 형태로 변환
    # serialized_data = {}
    # for status, df in ship_data_dict.items():
    #     # 필요한 주요 컬럼만 추출 (예: ShipName, mmsi, speed, type 등)
    #     cols = [c for c in ["ShipName", "mmsi", "speed", "type"] if c in df.columns]
    #     target_df = df[cols] if cols else df
    #     serialized_data[status] = target_df.to_dict(orient="records")

    json_payload = json.dumps(ship_data_dict, ensure_ascii=False)

    # 2. 외부 라이브러리(CDN) 전혀 없는 100% 오프라인 다크테마 HTML/JS 조립
    html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<style>
    body {{
        margin: 0; padding: 12px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        background-color: #0E1117; color: #E2E8F0; font-size: 13px;
    }}
    .header {{ font-weight: bold; font-size: 14px; margin-bottom: 10px; color: #38BDF8; }}
    .controls {{ display: flex; gap: 12px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }}
    .radio-group {{ display: flex; gap: 10px; background: #1E293B; padding: 4px 8px; border-radius: 6px; }}
    .radio-label {{ cursor: pointer; display: flex; align-items: center; gap: 4px; font-size: 12px; }}
    .search-input {{
        flex: 1; min-width: 160px; background: #1E293B; border: 1px solid #334155;
        color: #fff; padding: 5px 8px; border-radius: 6px; font-size: 12px; outline: none;
    }}
    .search-input:focus {{ border-color: #38BDF8; }}
    .table-container {{
        max-height: 180px; overflow-y: auto; border: 1px solid #334155; border-radius: 6px;
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
    <div class="header">📋 함정 상세 목록</div>
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

        // 1. 검색어 필터링 (ShipName or MMSI)
        const filtered = records.filter(row => {{
            const name = String(row.ShipName || '').toLowerCase();
            const mmsi = String(row.mmsi || '').toLowerCase();
            return name.includes(query) || mmsi.includes(query);
        }});

        // 2. 헤더 구성
        const headerTr = document.getElementById('tableHeader');
        headerTr.innerHTML = '';
        if (records.length > 0) {{
            Object.keys(records[0]).forEach(key => {{
                const th = document.createElement('th');
                th.textContent = key;
                headerTr.appendChild(th);
            }});
        }}

        // 3. 본문 렌더링
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

def _run_ship_status_extraction(context: SimulationContext) -> str:
    if context.ui_handler:
        context.ui_handler.on_tool_progress("기동 상태별 현황", "선박들의 상태를 추출 하여 이동/통과, 저속 운항, 정박/대기 카테고리로 분류한 정보를 반환합니다")

    ais_gdf = context.processing_list["ais_gdf"]
    shiptype_count_summary = ais_gdf.groupby('ShipType')['mmsi'].nunique().sort_values(ascending=False)
    data_dict_shiptype = shiptype_count_summary.to_dict()    

    stop_temp_df = compress_ship_data_duckdb_further(db_path=context.realtime_db_path, table_name="ship_logs", min_time=context.time.start_time, max_time=context.time.end_time)

    # 1. DuckDB 연결 (메모리 모드) 및 공간 확장 로드
    con = duckdb.connect(database=':memory:')
    con.execute("INSTALL spatial; LOAD spatial;")

    # 2. Pandas DataFrame을 DuckDB 메모리에 등록
    con.register('v_stop_data', stop_temp_df)

    # 2. 통합 쿼리 수행
    # - ShipName별 최신 행 추출 (tail(1) 대체)
    # - 시간 필터링 및 상태별 카테고리 분류
    query = f"""
        WITH latest_ships AS (
            SELECT 
                ShipName, mmsi, status, end_time,
                ROW_NUMBER() OVER(PARTITION BY ShipName ORDER BY end_time DESC, mmsi DESC) as rn
            FROM v_stop_data
        ),
        filtered_ships AS (
            SELECT ShipName, mmsi, status
            FROM latest_ships
            WHERE rn = 1
            AND CAST(end_time AS TIMESTAMP) <= CAST('{context.time.end_time}' AS TIMESTAMP)
            AND CAST(end_time AS TIMESTAMP) >= CAST('{context.time.end_time}' AS TIMESTAMP) - INTERVAL 1 HOUR
        )
        SELECT 
            ShipName, mmsi, status,
            CASE 
                WHEN status LIKE '%이동/통과%' THEN 'moving'
                WHEN status LIKE '%정박/대기%' THEN 'stop'
                WHEN status LIKE '%저속 운항%' THEN 'slow'
                ELSE 'others'
            END as category
        FROM filtered_ships
    """
    
    # 3. 데이터 가져오기 및 분류
    result_df = con.execute(query).df()
    
    def to_json_custom(target_df, category_name):
        # 중복 제거 후 리스트 딕셔너리 변환
        subset = target_df[target_df['category'] == category_name][['ShipName', 'mmsi', 'status']].drop_duplicates()
        records = subset.to_dict(orient='records')
        return records
    
    # 4. 각 카테고리별 JSON 생성
    moving_ships = to_json_custom(result_df, 'moving')
    stop_ships = to_json_custom(result_df, 'stop')
    slow_ships = to_json_custom(result_df, 'slow')

    render_map_dict = {
        "순항": moving_ships,
        "정박": stop_ships,
        "저속운항": slow_ships,
    }

    html_content = generate_ship_table_widget(render_map_dict)

    # 내부적으로 map_store 저장 + iframe 블록 조립 완료
    context.attach_table_block(key="ship_voyage_status", html_content=html_content)

    final_report = {
        "ship_types": data_dict_shiptype,
        "moving_ships": moving_ships,
        "stop_ships": stop_ships, 
        "slow_ships": slow_ships
    }
    if context.ui_handler:
        context.ui_handler.on_tool_complete("기동 상태별 현황")
        context.ui_handler.on_tool_result("기동 상태별 현황")

    return json.dumps(final_report, ensure_ascii=False, indent=4)


def ship_status_extraction(context: SimulationContext):
    @tool('Maritime Ships Voyage Status Analyzer')
    async def _ship_status_extraction() -> str:
        """
        현재 시점 기준 선박들의 상태를 추출 하여 이동/통과, 저속 운항, 정박/대기 카테고리로 분류하여 분석합니다.
        선박들의 현재 상태를 묻는 질문이나 선박 유형별 통계 관련 질문이 들어올 때 이 도구를 사용하세요.
        """
        if context.ui_handler:
            context.ui_handler.on_tool_start("기동 상태별 현황", "선박들의 상태를 추출 하여 이동/통과, 저속 운항, 정박/대기 카테고리로 분류한 정보를 반환합니다")
        # 데이터 처리 및 필터링 연산을 백그라운드 쓰레드에서 비동기 실행
        output_json = await asyncio.to_thread(_run_ship_status_extraction, context=context)
        return output_json
    return _ship_status_extraction
