import pandas as pd
import numpy as np

def compress_ship_data_py(df):
    # 1. 데이터 타입 변환 및 정렬
    df = df.copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed')
    df['course'] = pd.to_numeric(df['course'])
    df['speed'] = pd.to_numeric(df['speed'])
    df = df.sort_values(['ShipName','timestamp'])

    # 2. 변화량 및 트리거 계산
    df['prev_lon'] = df.groupby('ShipName')['longitude'].shift(1).fillna(df['longitude'])
    df['prev_lat'] = df.groupby('ShipName')['latitude'].shift(1).fillna(df['latitude'])
    df['prev_course'] = df.groupby('ShipName')['course'].shift(1).fillna(df['course'])
    df['prev_speed'] = df.groupby('ShipName')['speed'].shift(1).fillna(df['speed'])

    # 1) 위치 변화 비교
    df['pos_change'] = np.where(
        (df['longitude'].round(3) != df['prev_lon'].round(3)) | 
        (df['latitude'].round(3) != df['prev_lat'].round(3)), 1, 0
    )

    # 2) 침로 변화 비교(180도 회전 보정 포함)
    df['course_diff_raw'] = df['course'] - df['prev_course']
    df['course_diff'] = np.where(df['course_diff_raw'] > 180, df['course_diff_raw'] - 360,
                        np.where(df['course_diff_raw'] < -180, df['course_diff_raw'] + 360,
                        df['course_diff_raw']))
    df['course_change'] = np.where((df['course_diff'].abs() >= 20) & (df['speed'] >= 1.0), 1, 0)

    # 3) 속도 변화
    df['speed_diff'] = df['speed'] - df['prev_speed']
    df['speed_change'] = np.where(df['speed_diff'].abs() >= 2, 1, 0)

    # 4) 이벤트 트리거 
    df['event_trigger'] = np.where((df['pos_change'] == 1) | (df['course_change'] == 1) | (df['speed_change'] == 1), 1, 0)
    df['group_id'] = df.groupby('ShipName')['event_trigger'].cumsum()

    # 5. 그룹별 요약
    df_summarized = df.groupby(['ShipName', 'group_id']).agg(
        mmsi = ('mmsi', 'first'),
        higher_types = ('higher_types', 'first'),
        radius = ('radius','first'),
        start_time = ('timestamp', 'min'),
        end_time = ('timestamp', 'max'),
        lon = ('longitude', 'first'),
        lat = ('latitude', 'first'),
        first_course = ('course', 'first'), 
        avg_speed = ('speed', 'mean'),
        turn_val = ('course_diff', 'first'),
        accel_val = ('speed_diff', 'first')
    ).reset_index()

    # 6. 그룹 간 속도 차이 및 최종 상태 판별
    df_summarized['prev_avg_speed'] = df_summarized.groupby('ShipName')['avg_speed'].shift(1).fillna(df_summarized['avg_speed'])
    df_summarized['group_speed_diff'] = df_summarized['avg_speed'] - df_summarized['prev_avg_speed']

    def determine_status(row):
        # 1순위: 정박/대기
        if row['avg_speed'] < 1.0:
            return "정박/대기"

        # 2순위: 운항 중 상세 상태 
        # 선회 판단
        turn_desc = ""
        if abs(row['turn_val']) >= 20 and row['avg_speed'] >= 1.0:
            direction = "우선회" if row['turn_val'] > 0 else "좌선회"
            turn_desc = f"{direction}({round(abs(row['turn_val']), 1)}°)"

        # 가감속 판단
        accel_desc = ""
        if row['group_speed_diff'] >= 2:
            accel_desc = "가속"
        elif row['group_speed_diff'] < -2:
            accel_desc = "감속"

        # 기본 이동 상태
        move_desc = "이동/통과" if row['avg_speed'] >= 5.0 else "저속 운항"

        # 정보 결합 (불필요한 공백 제거)
        status_parts = [turn_desc, accel_desc, move_desc]
        return " ".join([p for p in status_parts if p != ""]).strip()

    df_summarized['status'] = df_summarized.apply(determine_status, axis=1)

    # 불필요한 중간 계산 컬럼 삭제 후 반환
    return df_summarized.drop(columns=['prev_avg_speed'])

def compress_ship_data_py_further(df):
    df['prev_status'] = df.groupby('ShipName')['status'].shift(1).fillna(df['status'])
    # 1) status 변화 비교
    df['status_change'] = np.where(
        df['status'] != df['prev_status'], 1, 0
    )
    df['group_id'] = df.groupby('ShipName')['status_change'].cumsum()
    df_summarized = df.groupby(['ShipName', 'group_id']).agg(
        mmsi = ('mmsi', 'first'),
        higher_types = ('higher_types', 'first'),
        radius = ('radius','first'),
        start_time = ('start_time', 'min'),
        end_time = ('end_time', 'max'),
        lon = ('lon', 'first'),
        lat = ('lat', 'first'),
        first_course = ('first_course', 'first'), 
        avg_speed = ('avg_speed', 'mean'),
        turn_val = ('turn_val', 'first'),
        accel_val = ('accel_val', 'first'),
        status = ('status', 'first')
    ).reset_index()
    return df_summarized