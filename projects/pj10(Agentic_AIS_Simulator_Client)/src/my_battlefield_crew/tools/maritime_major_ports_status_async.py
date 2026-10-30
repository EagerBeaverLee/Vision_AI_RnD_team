import os
import json
import asyncio
import pandas as pd
import geopandas as gpd
import movingpandas as mpd
import shapely.geometry as Point
import duckdb
from datetime import timedelta, datetime
from crewai.tools import tool
from my_battlefield_crew.engine.preprocessor import compress_ship_data_duckdb_further
from my_battlefield_crew.chainlit_app.schemas import SimulationContext


def _run_major_ports_status_analysis(context: SimulationContext) -> str:
    if context.ui_handler:
        context.ui_handler.on_tool_progress("주요 항만별 입출항", "기동 중인 선박들의 주요 항구별 입출항(출발/도착) 및 정박 현황 정보를 반환합니다")
    
    stop_temp_df = compress_ship_data_duckdb_further(
        db_path=context.db_path,
        table_name="ship_logs",
        min_time=context.start_time,
        max_time=context.end_time
    )
    # 1. DuckDB 연결 (메모리 모드) 및 공간 확장 로드
    con = duckdb.connect(database=':memory:')
    con.execute("INSTALL spatial; LOAD spatial;")

    # 2. Pandas DataFrame을 DuckDB 메모리에 등록
    con.register('v_ais_data', stop_temp_df)

    # 3. DuckDB 통합 쿼리 수행
    # - ROW_NUMBER()로 mmsi별 최신 데이터(end_time 기준) 식별
    # - 시간 차이 계산 및 '정박/대기' 상태 필터링을 한 번에 처리
    query = f"""
        WITH latest_status AS (
            SELECT *,
                ROW_NUMBER() OVER(PARTITION BY mmsi ORDER BY end_time DESC) as rn
            FROM stop_temp_df
        )
        SELECT *
        FROM latest_status
        WHERE rn = 1  -- 각 mmsi별 가장 최신 행만 선택
        AND status LIKE '%정박/대기%'
        AND CAST(end_time AS TIMESTAMP) <= CAST('{context.curr_time}' AS TIMESTAMP)
        AND CAST(end_time AS TIMESTAMP) >= CAST('{context.curr_time}' AS TIMESTAMP) - INTERVAL 1 HOUR
    """

    # 4. 결과 실행 (Pandas DataFrame으로 반환)
    anchored_ships = con.execute(query).df()

    # 5. GeoDataFrame 변환 (공간 조인 등을 위해)
    if not anchored_ships.empty:
        geometry = gpd.points_from_xy(anchored_ships['lon'], anchored_ships['lat'])
        anchored_ships_gdf = gpd.GeoDataFrame(anchored_ships, geometry=geometry, crs="EPSG:4326")
    else:
        anchored_ships_gdf = gpd.GeoDataFrame(columns=anchored_ships.columns.tolist() + ['geometry'], crs="EPSG:4326")

    # 분석할 항구 리스트 (시각화와 동일하게 설정)
    target_ports = ['BUSAN HANG', 'ULSAN HANG', 'GWANGYANG HANG, HADONG HANG', 'MOKPO HANG']

    # 결과를 담을 메인 딕셔너리
    report_data = {
        "report_info": {
            "analysis_period": {
                "start": str(context.start_time),
                "end": str(context.end_time)
            },
            "generated_at": datetime.now().isoformat(),
            "target_ports": target_ports
        },
        "ports_analysis": []
    }

    def is_leaving(traj, poly):
        return traj.get_start_location().intersects(poly) and not traj.get_end_location().intersects(poly)

    def is_entering(traj, poly):
        return not traj.get_start_location().intersects(poly) and  traj.get_end_location().intersects(poly)


    for port_name in target_ports:
        # 1. 데이터 필터링 (기존 로직 동일)
        single_port_gdf = context.processing_list['port_gdf'][context.processing_list['port_gdf']['objnam'] == port_name]
        if single_port_gdf.empty: continue
        
        port_projected = single_port_gdf.to_crs(epsg=5179)
        port_projected['geometry'] = port_projected.geometry.buffer(500)
        port_aoi = port_projected.to_crs(epsg=4326).geometry.iloc[0]

        trips = context.processing_list.get("trips", [])
        p_departures = [t for t in trips if is_leaving(t, port_aoi)]
        p_arrivals = [t for t in trips if is_entering(t, port_aoi)]

        if not anchored_ships_gdf.empty:
            p_anchored = anchored_ships_gdf[anchored_ships_gdf.geometry.within(port_aoi)]
        else:
            p_anchored = anchored_ships_gdf

        # 2. 항구별 JSON 구조 생성
        port_entry = {
            "port_name": port_name,
            "summary": {
                "anchored_count": len(p_anchored),
                "departure_count": len(p_departures),
                "arrival_count": len(p_arrivals)
            },
            "details": {
                "anchored_ships": [
                    {
                        "name": str(row.get('ShipName', 'Unknown')),
                        "mmsi": int(row['mmsi']),
                        # 💡 문자열/Timestamp 타입에 상관없이 안전하게 일시 포맷팅
                        "anchored_since": str(pd.to_datetime(row['start_time']).strftime('%Y-%m-%d %H:%M:%S'))
                    } for _, row in p_anchored.iterrows()
                ],
                "departures": [
                    {
                        "name": str(t.df['ShipName'].iloc[0]) if 'ShipName' in t.df.columns else "Unknown",
                        "type": str(t.df['ShipType'].iloc[0]) if 'ShipType' in t.df.columns else "Unknown",
                        "mmsi": int(str(t.id).split('_')[0]),
                        "event_time": str(t.get_start_time())
                    } for t in p_departures
                ],
                "arrivals": [
                    {
                        "name": str(t.df['ShipName'].iloc[0]) if 'ShipName' in t.df.columns else "Unknown",
                        "type": str(t.df['ShipType'].iloc[0]) if 'ShipType' in t.df.columns else "Unknown",
                        "mmsi": int(str(t.id).split('_')[0]),
                        "event_time": str(t.get_end_time())
                    } for t in p_arrivals
                ]
            }
        }
        report_data["ports_analysis"].append(port_entry)

    if context.ui_handler:
        context.ui_handler.on_tool_complete("주요 항만별 입출항")
        context.ui_handler.on_tool_result("주요 항만별 입출항")

    return json.dumps(report_data, ensure_ascii=False, indent=4)


def get_major_ports_status(context: SimulationContext):
    @tool("Maritime Major Ports Status")
    async def _get_major_ports_status() -> str:
        """현재 기동 중인 선박들의 주요 항구별 입출항(출발/도착) 및 정박 현황을 분석합니다.
        항만 현황, 입출항 선박 수, 정박 대기 관련 질문이 들어올 때 이 도구를 사용하세요"""
        if context.ui_handler:
            context.ui_handler.on_tool_start("주요 항만별 입출항", "기동 중인 선박들의 주요 항구별 입출항(출발/도착) 및 정박 현황 정보를 반환합니다")
        # MovingPandas Trajectory 분할 및 항구 공간 연산을 백그라운드 쓰레드에서 실행
        output_json = await asyncio.to_thread(_run_major_ports_status_analysis, context=context)
        return output_json
    return _get_major_ports_status


#######################
### original_backup
########################


# @tool("Maritime Major Ports Status")
# def get_major_ports_status() -> str:
#     """현재 기동 중인 선박들의 주요 항구별 입출항(출발/도착) 및 정박 현황을 분석합니다.
#     항만 현황, 입출항 선박 수, 정박 대기 관련 질문이 들어올 때 이 도구를 사용하세요"""

#     # 1.안전한 절대 경로 추적
#     current_dir = os.path.dirname(os.path.abspath(__file__))
#     parent_root = os.path.dirname(current_dir)

#     ais_path = os.path.join(parent_root, "cache","filtered_ais.parquet")
#     preprocessed_path = os.path.join(parent_root, "cache", "ais_compressed_step2.parquet")

#     if not os.path.exists(ais_path) or not os.path.exists(preprocessed_path):
#         return json.dumps({"error": "선행 분석 데이터가 없습니다. 파이프라인을 돌려주세요"})

#     ais = gpd.read_parquet(ais_path)

#     #일반 DataFrame일 경우 GeoDataFrame으로 강제 변환
#     if not isinstance(ais, gpd.GeoDataFrame):
#         geometry = [Point(xy) for xy in zip(ais['lon'], ais['lat'])]
#         ais = gpd.GeoDataFrame(ais, geometry=geometry, crs="EPSG:4326")
#     else:
#         ais = ais.to_crs("EPSG:4326") if ais.crs is None else ais

#     #MovingPandas 시간에 따른 궤적 생성을 위한 시간 컬럼 지정
#     if not isinstance(ais.index, pd.DatetimeIndex):
#         time_col = 't' if 't' in ais.columns else 'timestamp'
#         ais[time_col] = pd.to_datetime(ais[time_col])
#         ais = ais.set_index(time_col)

#     MIN_LENGTH = 1000
#     TRIP_ID = 'mmsi'
#     traj_collection = mpd.TrajectoryCollection(ais, TRIP_ID, min_length=MIN_LENGTH)
#     traj_collection = mpd.DouglasPeuckerGeneralizer(traj_collection).generalize(tolerance=0.001)
#     trips = mpd.ObservationGapSplitter(traj_collection).split(gap=timedelta(minutes=120)) #60분 이산 정박한 경우 trajectory 분할

#     ports_gdf = load_shp_file()

#     def is_leaving(traj, poly):
#         # 시작점은 안에서, 끝은 밖에서
#         return traj.get_start_location().intersects(poly) and not traj.get_end_location().intersects(poly)
    
#     def is_entering(traj, poly):
#         # 시작점은 밖에서, 끝은 안에서
#         return not traj.get_start_location().intersects(poly) and traj.get_end_location().intersects(poly)
    
#     #축약된 데이터의 'end_time'이 검색시간 기준 1시간 이내인 행만 추출
#     # 5. 정박 상태 데이터 전처리
#     stop_temp_df = pd.read_parquet(preprocessed_path)
#     latest_indices = stop_temp_df.groupby('mmsi')['end_time'].idxmax()
#     latest_status_df = stop_temp_df.loc[latest_indices].copy()
#     latest_status_df['end_time'] = pd.to_datetime(latest_status_df['end_time'], utc=True)

#     # 🚨 버그 수정 포인트: end_time 변수가 없었으므로 데이터셋의 가장 '최신 시간'을 기준으로 삼습니다.
#     reference_time = latest_status_df['end_time'].max()
#     time_diff_threshold = reference_time - latest_status_df['end_time']

#     stop_condition = (
#         (time_diff_threshold >= pd.Timedelta(0)) &
#         (time_diff_threshold <= pd.Timedelta(hours=1)) &
#         (latest_status_df['status'].str.contains("정박/대기", na=False))
#     )

#     anchored_ships = latest_status_df[stop_condition]
#     geometry = gpd.points_from_xy(anchored_ships['lon'], anchored_ships['lat'])
#     anchored_ships_gdf = gpd.GeoDataFrame(anchored_ships, geometry=geometry, crs="EPSG:4326")

#     # 분석할 항구 리스트
#     target_ports = ['BUSAN HANG', 'ULSAN HANG', 'GWANGYANG HANG, HADONG HANG', 'MOKPO HANG']
#     port_summary_list=[]

#     for port_name in target_ports:
#     # 1. 해당 항구 폴리곤 추출 및 버퍼 설정
#         single_port_gdf = ports_gdf[ports_gdf['objnam'] == port_name]
#         if single_port_gdf.empty:
#             continue
        
#         # 입출항 판정용 버퍼(500m)
#         port_projected = single_port_gdf.to_crs(epsg=5179)
#         port_projected['geometry'] = port_projected.geometry.buffer(500)
#         port_aoi = port_projected.to_crs(epsg=4326).geometry.iloc[0]

#         # 2. 해당 항구 데이터 필터링
#         # 출발/도착 항적
#         p_departures = [t for t in trips if is_leaving(t, port_aoi)]
#         p_arrivals = [t for t in trips if is_entering(t, port_aoi)]
#         p_anchored = anchored_ships_gdf[anchored_ships_gdf.geometry.within(port_aoi)]

#         #---텍스트 디테일 리스트 빌딩 ---#
#         anchored_details = []
#         for _, row in p_anchored.iterrows():
#             anchored_time_str = row['start_time'] if isinstance(row['start_time'], str) else row['start_time'].strftime('%Y-%m-%d %H:%M:%S')
#             anchored_details.append(f"{row['higher_types']} '{row['ShipName']}({row['mmsi']})': {anchored_time_str}부터 정박 중")

#         departure_details = []
#         for t in p_departures:
#             parsed_mmsi = int(str(t.id).split('_')[0]) if '_' in str(t.id) else int(t.id)
#             ship_type = t.df['higher_types'].iloc[0] if 'higher_types' in t.df.columns else t.df['ShipType'].iloc[0]
#             departure_details.append(f"{ship_type} '{t.df['ShipName'].iloc[0]}({parsed_mmsi})': {t.get_start_time()} 에 출발")

#         arrival_details = []
#         for t in p_arrivals:
#             parsed_mmsi = int(str(t.id).split('_')[0]) if '_' in str(t.id) else int(t.id)
#             ship_type = t.df['higher_types'].iloc[0] if 'higher_types' in t.df.columns else t.df['ShipType'].iloc[0]
#             arrival_details.append(f"{ship_type} '{t.df['ShipName'].iloc[0]}({parsed_mmsi})': {t.get_end_time()} 에 도착")
        
#         port_entry = {
#             "port_name": port_name,
#             "anchored_count": len(p_anchored),
#             "departure_count": len(p_departures),
#             "arrival_count": len(p_arrivals),
#             "anchored_ships_detail": anchored_details,
#             "departures_detail": departure_details,
#             "arrivals_detail": arrival_details
#         }
        
#         port_summary_list.append(port_entry)
    
#     # print(json.dumps(port_summary_list, ensure_ascii=False, indent=4))

#     return json.dumps(port_summary_list, ensure_ascii=False, indent=4)

# if __name__ == "__main__":
    # 테스트를 위해 원본 파일 경로와 파라미터를 수동으로 지정하여 실행
    # get_major_ports_status()