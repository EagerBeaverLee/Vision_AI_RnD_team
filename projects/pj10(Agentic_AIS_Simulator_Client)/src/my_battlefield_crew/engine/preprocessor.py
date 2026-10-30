import geopandas as gpd
import movingpandas as mpd
import duckdb
import shapely
from shapely.geometry import box
from datetime import datetime, timedelta

def init_ports_gdf():
    # 주요 항만 데이터
    ports_gdf = gpd.read_file('./src/my_battlefield_crew/data/spatial_data/major_ports.shp')
    ports_gdf = ports_gdf.to_crs("EPSG:4326")
    return ports_gdf

def init_zone_gdf():
    zone_configs = {
        # --- [Layer 1: 북부 연안 및 울산] Lat: 34.70 ~ 36.00 (일부 34.40 시작) ---
        'Zone_16':   [125.00, 34.40, 125.50, 36.00, '서해 남부 외해'],
        'Zone_5':    [125.50, 34.40, 126.60, 36.00, '목포-신안 해역'],
        'Zone_12':   [126.60, 34.40, 127.60, 36.00, '고흥-완도 연안'],
        'Zone_3':    [127.60, 34.70, 128.00, 36.00, '광양-여수 해역'],
        'Zone_4':    [128.00, 34.70, 128.30, 36.00, '남해 중앙 연안'],
        'Zone_2':    [128.30, 34.70, 128.70, 36.00, '거제-통영 해역'],
        'Zone_1':    [128.70, 34.70, 129.30, 36.00, '부산-가덕 해역'],
        'Zone_18':   [129.30, 34.70, 130.50, 36.00, '부산외항-울산남부'], # 부산 동쪽 빈틈 메움
        'Zone_14':   [130.50, 35.15, 132.50, 36.00, '울산-포항 해역'],
        
        # --- [Layer 2: 중단 외해 및 대한해협] Lat: 33.80 ~ 34.70 ---
        'Zone_7':    [125.00, 33.00, 126.20, 34.40, '서남해 외해'],
        'Zone_8':    [126.20, 33.80, 127.60, 34.40, '제주-육지 교차로 해역'],
        'Zone_9_1':  [127.60, 33.80, 128.30, 34.70, '여수-통영 외해'],
        'Zone_9_2':  [128.30, 33.80, 128.70, 34.70, '거제-가덕 외해'],
        'Zone_9_3':  [128.70, 33.80, 129.30, 34.70, '부산-대마도 입구 해역'], # 부산 하단 빈틈 메움
        'Zone_15_1': [129.30, 33.80, 130.50, 34.70, '대마도 남서 해역'],
        'Zone_17':   [130.50, 33.80, 131.50, 34.25, '시모노세키-기타큐슈 해역'],
        'Zone_15_2': [130.50, 34.25, 131.50, 35.15, '대마도 북동 해역'],
        
        # --- [Layer 3: 제주 및 일본 연안] Lat: 33.00 ~ 33.80 ---
        'Zone_6':    [126.20, 33.40, 126.90, 33.80, '제주 북부 연안'],
        'Zone_13':   [126.20, 33.00, 126.90, 33.40, '제주 남부 연안'],
        'Zone_11':   [126.90, 33.00, 129.50, 33.80, '제주 남동부 해역'],
        'Zone_15_3': [129.50, 33.00, 131.00, 33.80, '이키-후쿠오카 연안'],
        'Zone_15_4': [131.00, 33.00, 132.50, 35.15, '일본 가이요 외해'],
        
        # --- [Layer 4: 최남단 원거리] Lat: 31.00 ~ 33.00 ---
        'Zone_10':   [125.00, 31.00, 132.50, 33.00, '원거리 국제공해']
    }

    polygons = []
    ids = []
    names = []

    for zid, val in zone_configs.items():
        polygons.append(box(val[0], val[1], val[2], val[3]))
        ids.append(zid)
        names.append(val[4])

    zones_gdf = gpd.GeoDataFrame({'zone_id': ids, 'name': names}, 
                                geometry=polygons, crs="EPSG:4326")
    return zones_gdf

def common_preprocessing(db_path, start_time, end_time):
    # 1. DuckDB 파일 연결 및 공간 확장 로드
    con = duckdb.connect(database=':memory:')
    con.execute("INSTALL spatial; LOAD spatial;")
    con.execute("INSTALL sqlite; LOAD sqlite;")
    
    # 읽기 전용으로 안전하게 마운트 후 기본 DB 설정
    con.execute(f"ATTACH '{db_path}' AS sqlite_db (TYPE sqlite, READ_ONLY);")
    con.execute("USE sqlite_db;")

    table_name = "ship_logs"

    # 2. 초기 데이터 필터링 (DuckDB)
    # CSV를 읽으면서 위경도/시간/속도를 즉시 필터링
    min_lon, max_lon, max_lat = 125.678, 131.229, 36.001

    # 쿼리 실행 (DB 내부에서 직접 필터링)
    query = f"""
        SELECT *, ST_AsWKB(ST_Point(longitude, latitude)) as geom_wkb, CAST(timestamp AS TIMESTAMP) as t
        FROM {table_name}
        WHERE longitude >= {min_lon} AND longitude <= {max_lon}
        AND latitude <= {max_lat}
        AND timestamp >= '{start_time}' 
        AND timestamp <= '{end_time}'
        AND speed > 0
        ORDER BY MMSI, t ASC  -- 이 줄이 필수입니다!
    """

    # 3. DuckDB 결과를 Pandas로 가져오기
    df = con.execute(query).df()

    # 4. WKB 컬럼을 이용해 즉시 GeoDataFrame 생성
    # 이 방식은 points_from_xy보다 대용량 처리 시 훨씬 빠릅니다.
    ais_gdf = gpd.GeoDataFrame(
        df, 
        geometry=shapely.from_wkb(df['geom_wkb'].apply(bytes)),
        crs="EPSG:4326"
    ).set_index('t')

    # 3. MovingPandas 집계 (클러스터 추출)
    traj_collection = mpd.TrajectoryCollection(ais_gdf, 'mmsi', min_length=1000)
    n_traj_collection = mpd.DouglasPeuckerGeneralizer(traj_collection).generalize(tolerance=0.001) #가장 빠름
    # 전처리 추가(실험 필요)
    trips = mpd.ObservationGapSplitter(n_traj_collection).split(gap=timedelta(minutes=120))
    aggregator = mpd.TrajectoryCollectionAggregator(
        trips, max_distance=100000, min_distance=2000, min_stop_duration=timedelta(minutes=120)
    )

    return ais_gdf, trips, aggregator

def init_geo_processing(db_path, start_time, end_time):
    port_gdf = init_ports_gdf()
    zone_gdf = init_zone_gdf()
    ais_gdf, trips, aggregator = common_preprocessing(db_path, start_time, end_time)
    return {
        "port_gdf": port_gdf,
        "zone_gdf": zone_gdf,
        "ais_gdf": ais_gdf,
        "trips": trips,
        "aggregator": aggregator
    }

def compress_ship_data_duckdb(db_path, table_name, min_time, max_time, min_lon=125.678, max_lon=131.229, max_lat=36.001):
    con = duckdb.connect(database=':memory:')
    con.execute("INSTALL sqlite; LOAD sqlite;")
    con.execute(f"ATTACH '{db_path}' AS sqlite_db (TYPE SQLITE);")

    query = f"""
    WITH raw_data AS (
        -- 1. 데이터 로드 및 초기 필터링
        SELECT 
            *,
            CAST(timestamp AS TIMESTAMP) as ts,
            CAST(longitude AS DOUBLE) as lon_val,
            CAST(latitude AS DOUBLE) as lat_val,
            CAST(course AS DOUBLE) as c_course,
            CAST(speed AS DOUBLE) as s_speed,
            row_number() OVER () as temp_row_idx
        FROM sqlite_db.{table_name}
        WHERE longitude >= {min_lon} 
        AND longitude <= {max_lon} 
        AND latitude <= {max_lat}
        AND timestamp BETWEEN '{min_time}' AND '{max_time}'
        
    ),
    ordered_data AS (
        -- 2. 이전 값 계산 (정렬 안정성 확보)
        SELECT *,
            LAG(lon_val) OVER (PARTITION BY ShipName ORDER BY ts, temp_row_idx) as prev_lon,
            LAG(lat_val) OVER (PARTITION BY ShipName ORDER BY ts, temp_row_idx) as prev_lat,
            LAG(c_course) OVER (PARTITION BY ShipName ORDER BY ts, temp_row_idx) as prev_course,
            LAG(s_speed) OVER (PARTITION BY ShipName ORDER BY ts, temp_row_idx) as prev_speed
        FROM raw_data
    ),
    diff_calc AS (
        -- 3. 변화량 계산 (부동소수점 오차 방지를 위해 정수로 변환하여 비교)
        SELECT *,
            -- ROUND(3) 대신 1000을 곱해 정수로 만들어 비교 (Pandas와의 미세한 오차 제거)
            CASE WHEN CAST(lon_val * 1000 AS BIGINT) != CAST(COALESCE(prev_lon, lon_val) * 1000 AS BIGINT) 
                OR CAST(lat_val * 1000 AS BIGINT) != CAST(COALESCE(prev_lat, lat_val) * 1000 AS BIGINT) 
                THEN 1 ELSE 0 END as pos_change,
            
            CASE 
                WHEN (c_course - COALESCE(prev_course, c_course)) > 180 THEN (c_course - COALESCE(prev_course, c_course)) - 360
                WHEN (c_course - COALESCE(prev_course, c_course)) < -180 THEN (c_course - COALESCE(prev_course, c_course)) + 360
                ELSE (c_course - COALESCE(prev_course, c_course))
            END as course_diff,
            
            (s_speed - COALESCE(prev_speed, s_speed)) as speed_diff
        FROM ordered_data
    ),
    event_logic AS (
        -- 4. 이벤트 트리거 (>= 20 또는 >= 1.0 처럼 경계값에 미세 오차 고려 시도 가능하나 일단 정확히 일치 시도)
        SELECT *,
            CASE 
                WHEN pos_change = 1 
                OR (ABS(course_diff) >= 20.0 AND s_speed >= 1.0)
                OR ABS(speed_diff) >= 2.0 
                THEN 1 ELSE 0 
            END as event_trigger
        FROM diff_calc
    ),
    grouping AS (
        -- 5. 그룹 ID 생성 (Pandas cumsum과 동일)
        SELECT *,
            SUM(event_trigger) OVER (PARTITION BY ShipName ORDER BY ts, temp_row_idx ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) as group_id
        FROM event_logic
    ),
    summarized AS (
        -- 6. 그룹별 요약 (15개 컬럼 구성 시작)
        SELECT 
            ShipName,
            group_id,
            ANY_VALUE(mmsi) as mmsi, -- FIRST 대신 ANY_VALUE가 성능상 유리하나 의미는 같음
            ANY_VALUE(higher_types) as higher_types,
            ANY_VALUE(radius) as radius,
            MIN(ts) as start_time,
            MAX(ts) as end_time,
            ANY_VALUE(lon_val) as lon,
            ANY_VALUE(lat_val) as lat,
            ANY_VALUE(c_course) as first_course,
            AVG(s_speed) as avg_speed,
            ANY_VALUE(course_diff) as turn_val,
            ANY_VALUE(speed_diff) as accel_val
        FROM grouping
        GROUP BY ShipName, group_id
    ),
    final_stats AS (
        -- 7. 이전 그룹과의 속도 차이 계산
        SELECT *,
            avg_speed - COALESCE(LAG(avg_speed) OVER (PARTITION BY ShipName ORDER BY start_time), avg_speed) as group_speed_diff
        FROM summarized
    )
    -- 8. 최종 15개 컬럼 및 상태값 생성
    SELECT 
        ShipName, group_id, mmsi, higher_types, radius, start_time, end_time, 
        lon, lat, first_course, avg_speed, turn_val, accel_val, group_speed_diff,
        CASE 
            WHEN avg_speed < 1.0 THEN '정박/대기'
            ELSE 
                TRIM(
                    CONCAT_WS(' ',
                        CASE WHEN ABS(turn_val) >= 20.0 AND avg_speed >= 1.0 
                            THEN (CASE WHEN turn_val > 0 THEN '우선회' ELSE '좌선회' END) || '(' || ROUND(ABS(turn_val), 1) || '°)'
                            ELSE '' END,
                        CASE WHEN group_speed_diff >= 2.0 THEN '가속'
                            WHEN group_speed_diff <= -2.0 THEN '감속' -- < -2 대신 <= -2로 더 정확히
                            ELSE '' END,
                        CASE WHEN avg_speed >= 5.0 THEN '이동/통과' ELSE '저속 운항' END
                    )
                )
        END as status
    FROM final_stats
    ORDER BY ShipName, start_time
    """

    df_result = con.execute(query).df()
    con.execute("DETACH sqlite_db;")
    return df_result

def compress_ship_data_duckdb_further(db_path, table_name, min_time, max_time, min_lon=125.678, max_lon=131.229, max_lat=36.001):
        con = duckdb.connect(database=':memory:')
        con.execute("INSTALL sqlite; LOAD sqlite;")
        con.execute(f"ATTACH '{db_path}' AS sqlite_db (TYPE SQLITE);")

        query = f"""
        -- [STEP 1] Raw 데이터 로드 및 1차 트리거 (정수 변환 비교로 정밀도 확보)
        WITH raw_data AS (
            SELECT *,
                CAST(timestamp AS TIMESTAMP) as ts,
                CAST(longitude AS DOUBLE) as lon_val,
                CAST(latitude AS DOUBLE) as lat_val,
                CAST(course AS DOUBLE) as c_course,
                CAST(speed AS DOUBLE) as s_speed,
                row_number() OVER () as temp_row_idx
            FROM sqlite_db.{table_name}
            WHERE longitude >= {min_lon} AND longitude <= {max_lon} AND latitude <= {max_lat}
                AND timestamp BETWEEN '{min_time}' AND '{max_time}'
        ),
        ordered_data AS (
            SELECT *,
                LAG(lon_val) OVER (PARTITION BY ShipName ORDER BY ts, temp_row_idx) as prev_lon,
                LAG(lat_val) OVER (PARTITION BY ShipName ORDER BY ts, temp_row_idx) as prev_lat,
                LAG(c_course) OVER (PARTITION BY ShipName ORDER BY ts, temp_row_idx) as prev_course,
                LAG(s_speed) OVER (PARTITION BY ShipName ORDER BY ts, temp_row_idx) as prev_speed
            FROM raw_data
        ),
        diff_calc AS (
            SELECT *,
                CASE WHEN CAST(lon_val * 1000 AS BIGINT) != CAST(COALESCE(prev_lon, lon_val) * 1000 AS BIGINT) 
                    OR CAST(lat_val * 1000 AS BIGINT) != CAST(COALESCE(prev_lat, lat_val) * 1000 AS BIGINT) 
                    THEN 1 ELSE 0 END as pos_change,
                CASE 
                    WHEN (c_course - COALESCE(prev_course, c_course)) > 180 THEN (c_course - COALESCE(prev_course, c_course)) - 360
                    WHEN (c_course - COALESCE(prev_course, c_course)) < -180 THEN (c_course - COALESCE(prev_course, c_course)) + 360
                    ELSE (c_course - COALESCE(prev_course, c_course))
                END as course_diff,
                (s_speed - COALESCE(prev_speed, s_speed)) as speed_diff
            FROM ordered_data
        ),
        event_logic AS (
            SELECT *,
                -- 경계값 오차 방지를 위해 0.000001 보정 (Pandas와의 일치성 향상)
                CASE WHEN pos_change = 1 OR (ABS(course_diff) >= 19.999999 AND s_speed >= 0.999999) OR ABS(speed_diff) >= 1.999999 THEN 1 ELSE 0 END as event_trigger
            FROM diff_calc
        ),
        grouping_v1 AS (
            SELECT *,
                SUM(event_trigger) OVER (PARTITION BY ShipName ORDER BY ts, temp_row_idx ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) as group_id_v1
            FROM event_logic
        ),
        summarized_v1 AS (
            -- [1차 압축] ANY_VALUE 대신 FIRST를 사용하여 Pandas .first()와 100% 일치화
            SELECT 
                ShipName, group_id_v1,
                FIRST(mmsi) as mmsi, FIRST(higher_types) as higher_types, FIRST(radius) as radius,
                MIN(ts) as start_time, MAX(ts) as end_time,
                FIRST(lon_val) as lon, FIRST(lat_val) as lat,
                FIRST(c_course) as first_course, AVG(s_speed) as avg_speed,
                FIRST(course_diff) as turn_val, FIRST(speed_diff) as accel_val
            FROM grouping_v1 
            GROUP BY ShipName, group_id_v1
        ),
        -- [STEP 2] 상태 판별 (부동소수점 오차 차단)
        status_calc AS (
            SELECT *,
                avg_speed - COALESCE(LAG(avg_speed) OVER (PARTITION BY ShipName ORDER BY start_time, group_id_v1), avg_speed) as group_speed_diff
            FROM summarized_v1
        ),
        status_final AS (
            SELECT *,
                CASE 
                    -- 1.0, 20.0 등의 경계값을 소수점 8자리에서 반올림 후 비교하여 Pandas와 일치시킴
                    WHEN ROUND(avg_speed, 8) < 1.0 THEN '정박/대기'
                    ELSE TRIM(CONCAT_WS(' ',
                        CASE WHEN ROUND(ABS(turn_val), 8) >= 20.0 AND ROUND(avg_speed, 8) >= 1.0 
                            THEN (CASE WHEN turn_val > 0 THEN '우선회' ELSE '좌선회' END) || '(' || ROUND(ABS(turn_val), 1) || '°)' ELSE '' END,
                        CASE WHEN ROUND(group_speed_diff, 8) >= 2.0 THEN '가속' 
                            WHEN ROUND(group_speed_diff, 8) < -2.0 THEN '감속' ELSE '' END,
                        CASE WHEN ROUND(avg_speed, 8) >= 5.0 THEN '이동/통과' ELSE '저속 운항' END
                    ))
                END as status
            FROM status_calc
        ),
        -- [STEP 3] 2차 압축
        v2_trigger AS (
            SELECT *,
                CASE WHEN status != COALESCE(LAG(status) OVER (PARTITION BY ShipName ORDER BY start_time, group_id_v1), status) 
                    THEN 1 ELSE 0 END as status_change
            FROM status_final
        ),
        v2_grouping AS (
            SELECT *,
                SUM(status_change) OVER (PARTITION BY ShipName ORDER BY start_time, group_id_v1 ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) as group_id
            FROM v2_trigger
        )
        -- [STEP 4] 최종 요약 (집계 방식 일치)
        SELECT 
            ShipName, group_id,
            FIRST(mmsi) as mmsi, FIRST(higher_types) as higher_types, FIRST(radius) as radius,
            MIN(start_time) as start_time, MAX(end_time) as end_time,
            FIRST(lon) as lon, FIRST(lat) as lat,
            FIRST(first_course) as first_course,
            AVG(avg_speed) as avg_speed,
            FIRST(turn_val) as turn_val,
            FIRST(accel_val) as accel_val,
            FIRST(status) as status
        FROM v2_grouping
        GROUP BY ShipName, group_id
        ORDER BY ShipName, start_time
        """

        df_result = con.execute(query).df()
        con.execute("DETACH sqlite_db;")
        return df_result
