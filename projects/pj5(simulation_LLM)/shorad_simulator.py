import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
from PIL import Image
import datetime
import numpy as np

# --- 한글 폰트 설정 (이 부분을 추가) ---
import matplotlib.font_manager as fm
# 시스템에 설치된 나눔고딕 폰트 경로를 찾아서 설정
font_path = 'C:/Windows/Fonts/malgun.ttf'  # Windows 기준
# 만약 Linux/macOS 환경이라면 다음 경로를 시도해 보세요.
# font_path = '/usr/share/fonts/truetype/nanum/NanumGothic.ttf'  # Linux
# font_path = '/Library/Fonts/AppleGothic.ttf'  # macOS
font_name = fm.FontProperties(fname=font_path, size=10).get_name()
plt.rc('font', family=font_name)
plt.rcParams['axes.unicode_minus'] = False # 마이너스 기호 깨짐 방지
# ----------------------------------------

# --- 1. 데이터베이스(DataFrame) 초기 설정 ---
# 시나리오 3 (복합 통합 공격 대응) 기반 데이터

# 기준 시간 설정 (T0)
BASE_TIME = datetime.datetime(2025, 10, 13, 10, 0, 0)

# 시뮬레이션 이벤트 목록 (시간 순서대로)
events = [
    # T0: 임무 시작
    (0, "SYSTEM", "작전 시작", "주요 항만 방어 임무 개시. 교리: 방어 심층화, 통합."),
    
    # T1: 1분 30초: 공격 개시 (SRBM, CM, UAS) 및 EW 영향
    (90, "THREAT", "복합 통합 공격 개시", "SRBM(고고도), CM(중고도), UAS(저고도) 동시 탐지."),
    (90, "THREAT", "EW 공격 감지", "CM, UAS 위협과 동반. Sentinel 레이더 부분 성능 저하."),
    (90, "DEFENSE", "Patriot", "SRBM에 대한 HIMAD(고고도 방어) 교전 준비 완료."),
    (90, "DEFENSE", "Avenger", "CM, UAS에 대한 SHORAD(최종 방어) 대기."),

    # T2: 2분 45초: Patriot SRBM 교전
    (165, "ENGAGEMENT", "Patriot SRBM 교전", "Patriot, SRBM 요격 성공. (방어 심층화 1단계 성공)"),
    (165, "THREAT", "CM, UAS 위협 유지", "CM이 방어 계층을 통과하여 최종 방어선 접근 중."),
    (165, "DEFENSE", "Patriot", "탄약 2발 소모, 재장전/대기 상태."),

    # T3: 3분 30초: Avenger CM/UAS 교전 시작
    (210, "ENGAGEMENT", "Avenger CM 교전 시작", "Avenger, CM 요격 시작. (SHORAD 임무 인계)"),
    (210, "ENGAGEMENT", "Avenger UAS 교전 시작", "Avenger, 근접 UAS 요격 시작. (복합 공격 대응)"),
    (210, "DEFENSE", "Avenger", "탄약 소모 시작. 상호 지원 및 회복 탄력성 점검 필요."),

    # T4: 4분 30초: UAS 1기 격파, CM 요격 실패 (가정)
    (270, "ENGAGEMENT", "UAS 격파 성공", "Avenger, UAS 1기 격파. CM 요격은 실패. (방책 조정 필요)"),
    (270, "THREAT", "CM 잔존", "CM이 목표에 근접, 피해 발생 위험 증가."),
    
    # T5: 5분 00초: 최종 방책 적용 및 상황 종료
    (300, "SYSTEM", "방책 적용/상황 종료", "교범 검색 기반 방책: 인접 SHORAD 자산의 상호 지원 재배치 완료.")
]

# DataFrame으로 변환
df_events = pd.DataFrame(events, columns=['time_offset', 'category', 'event', 'details'])
df_events['time_stamp'] = df_events['time_offset'].apply(lambda x: (BASE_TIME + datetime.timedelta(seconds=x)).strftime('%H:%M:%S'))

# --- 2. 시각화 함수 ---

def plot_hardcoded_movement_at_time(current_time_offset):
    """
    하드코딩된 경로와 함께 적군 및 아군의 영향권(원) 및 다음 이동 방향 화살표를 시각화합니다.
    배경으로 'map.png' 이미지를 사용하며, 300초 경과 시점의 오류를 수정했습니다.
    """
    st.subheader("적/아군 2차원 위치 추이: 배경 맵 적용 시뮬레이션")
    
    # =========================================================
    # 1. 하드코딩된 경로 정의 (이전 코드와 동일)
    # =========================================================
    
    ROK_SCOUTS = np.array([
        # [263.2, 50.3],
        [251.2, 60.3],
        [239.2, 70.3],
        [227.2, 80.3],
        [215.2, 90.3],
        [209.2, 100.3],
        [204.2, 110.3],
        [204.2, 110.3],
        [196.2, 117.3],
        [184.2, 124.3],
        [172.2, 127.3],
        [172.2, 127.3]
        # [158.2, 129.3]
    ])

    ROK_MAIN = np.array([
        # [275.2, 40.3],
        [263.2, 50.3],
        [251.2, 60.3],
        [239.2, 70.3],
        [227.2, 80.3],
        [218.2, 85.3],
        [215.2, 90.3],
        [215.2, 90.3],
        [218.2, 93.3],
        [218.2, 93.3],
        [218.2, 93.3],
        [218.2, 93.3]
        # [209.2, 100.3],
        # [204.2, 110.3]
        # [196.2, 117.3]
        # [184.2, 124.3]
        # [172.2, 127.3]
    ])

    ROK_EW = np.array([
        # [289.0, 30.1],
        [275.0, 40.1],
        [263.0, 50.1],
        [251.0, 60.1],
        [239.0, 70.1],
        [227.0, 80.1],
        [221.0, 85.1],
        [221.0, 85.1],
        [223.0, 88.1],
        [223.0, 88.1],
        [223.0, 88.1],
        [223.0, 88.1]
        # [215.0, 90.1],
        # [209.0, 100.1]
        # [204.0, 110.1]
        # [196.0, 117.1]
        # [184.0, 124.1]
    ])

    KPA_SOF = np.array([
        [180.0, 94.0],
        [180.0, 94.0],
        [191.0, 105.0],
        [203.0, 110.0],
        [190.0, 112.0],
        [203.0, 110.0],
        [190.0, 112.0],
        [190.0, 112.0],
        [190.0, 112.0],
        [190.0, 112.0],
        [190.0, 112.0]
    ])

    KPA_EW = np.array([
        [196.6,47.5],
        [196.6,47.5],
        [196.6,47.5],
        [196.6,47.5],
        [196.6,47.5],
        [196.6,47.5],
        [196.6,47.5],
        [196.6,47.5],
        [196.6,47.5],
        [196.6,47.5],
        [196.6,47.5]
    ])

    KPA_FS = np.array([
        [260.0, 110.0],
        [260.0, 110.0],
        [260.0, 110.0],
        [260.0, 110.0],
        [260.0, 110.0],
        [260.0, 110.0],
        [260.0, 110.0],
        [260.0, 110.0],
        [260.0, 110.0],
        [260.0, 110.0],
        [260.0, 110.0],
    ])
    
    total_time = 300
    tick_interval = 30
    ARROW_LENGTH = 15

    # 현재 시간을 300초 내로 제한
    if current_time_offset < 0:
        current_time_offset = 0
    if current_time_offset > total_time:
        current_time_offset = total_time

    # =========================================================
    # 2. 동적 반지름 계산 (새로 추가된 로직) 📏
    # =========================================================

    kpa_ew_radius = 100
    # 아군 원 반지름: 240초부터 20으로 커짐
    if current_time_offset >= 180:
        rok_ew_radius = 15
        # rok_scouts_radius = 10
    else:
        rok_ew_radius = 40
        # rok_scouts_radius = 30

    # =========================================================
    # 3. 현재 위치 및 다음 목표 위치 계산 (오류 수정 지점)
    # =========================================================
    
    current_tick_index = int(current_time_offset // tick_interval)
    
    # 🚨 UnboundLocalError 수정 로직:
    if current_time_offset == total_time: # 300초일 경우
        current_tick_index = len(ROK_EW) - 1 # 마지막 인덱스 (10)
        rok_ew_pos = ROK_EW[current_tick_index]
        rok_scouts_pos = ROK_SCOUTS[current_tick_index]
        rok_main_pos = ROK_MAIN[current_tick_index]
        kpa_ew_pos = KPA_EW[current_tick_index]
        kpa_sof_pos = KPA_SOF[current_tick_index]
        kpa_fs_pos = KPA_FS[current_tick_index]

        
        # 다음 이동할 위치를 현재 위치와 동일하게 설정 (화살표 벡터 0)
        rok_ew_next_pos = rok_ew_pos 
        rok_scouts_next_pos = rok_scouts_pos
        rok_main_next_pos = rok_main_pos
        kpa_ew_next_pos = kpa_ew_pos
        kpa_sof_next_pos = kpa_sof_pos
        kpa_fs_next_pos = kpa_fs_pos
        
    else: # 0초부터 299.9초 사이일 경우
        # 현재 위치 (선형 보간) 계산
        start_time_of_current_tick = current_tick_index * tick_interval
        time_in_tick = current_time_offset - start_time_of_current_tick
        movement_ratio_between_ticks = time_in_tick / tick_interval
        
        rok_ew_start_pos = ROK_EW[current_tick_index]
        rok_ew_next_pos_tick = ROK_EW[current_tick_index + 1] # 다음 틱은 반드시 존재
        rok_scouts_start_pos = ROK_SCOUTS[current_tick_index]
        rok_scouts_next_pos_tick = ROK_SCOUTS[current_tick_index + 1]
        rok_main_start_pos = ROK_MAIN[current_tick_index]
        rok_main_next_pos_tick = ROK_MAIN[current_tick_index + 1]
        kpa_ew_start_pos = KPA_EW[current_tick_index]
        kpa_ew_next_pos_tick = KPA_EW[current_tick_index + 1]
        kpa_sof_start_pos = KPA_SOF[current_tick_index]
        kpa_sof_next_pos_tick = KPA_SOF[current_tick_index + 1]
        kpa_fs_start_pos = KPA_FS[current_tick_index]
        kpa_fs_next_pos_tick = KPA_FS[current_tick_index + 1]
        
        rok_ew_pos = rok_ew_start_pos + (rok_ew_next_pos_tick - rok_ew_start_pos) * movement_ratio_between_ticks
        rok_scouts_pos = rok_scouts_start_pos + (rok_scouts_next_pos_tick - rok_scouts_start_pos) * movement_ratio_between_ticks
        rok_main_pos = rok_main_start_pos + (rok_main_next_pos_tick - rok_main_start_pos) * movement_ratio_between_ticks
        kpa_ew_pos = kpa_ew_start_pos + (kpa_ew_next_pos_tick - kpa_ew_start_pos) * movement_ratio_between_ticks
        kpa_sof_pos = kpa_sof_start_pos + (kpa_sof_next_pos_tick - kpa_sof_start_pos) * movement_ratio_between_ticks
        kpa_fs_pos = kpa_fs_start_pos + (kpa_fs_next_pos_tick - kpa_fs_start_pos) * movement_ratio_between_ticks
        
        # 다음 틱의 위치를 화살표의 목표 지점으로 설정
        rok_ew_next_pos = rok_ew_next_pos_tick
        rok_scouts_next_pos = rok_scouts_next_pos_tick
        rok_main_next_pos = rok_main_next_pos_tick
        kpa_ew_next_pos = kpa_ew_next_pos_tick
        kpa_sof_next_pos = kpa_sof_next_pos_tick
        kpa_fs_next_pos = kpa_fs_next_pos_tick

    if current_time_offset >= 180:
        rok_scouts_pos = np.array([0,0])
        rok_scouts_next_pos = rok_scouts_pos
        end_tick_index = int(180 // tick_interval)
        rok_scouts_path_to_current = ROK_SCOUTS[:end_tick_index + 1]
        rok_scouts_history = rok_scouts_path_to_current
    else:
        rok_scouts_path_to_current = ROK_SCOUTS[:current_tick_index + 1]
        rok_scouts_history = np.vstack([rok_scouts_path_to_current, rok_scouts_pos])

    # 현재까지 지나온 경로 포인트를 추출 및 현재 위치 추가
    rok_ew_path_to_current = ROK_EW[:current_tick_index + 1]
    # rok_scouts_path_to_current = ROK_SCOUTS[:current_tick_index + 1]
    rok_main_path_to_current = ROK_MAIN[:current_tick_index + 1]
    kpa_ew_path_to_current = KPA_EW[:current_tick_index + 1]
    kpa_sof_path_to_current = KPA_SOF[:current_tick_index + 1]
    kpa_fs_path_to_current = KPA_FS[:current_tick_index + 1]

    rok_ew_history = np.vstack([rok_ew_path_to_current, rok_ew_pos])
    # rok_scouts_history = np.vstack([rok_scouts_path_to_current, rok_scouts_pos])
    rok_main_history = np.vstack([rok_main_path_to_current, rok_main_pos])
    kpa_ew_history = np.vstack([kpa_ew_path_to_current, kpa_ew_pos])
    kpa_sof_history = np.vstack([kpa_sof_path_to_current, kpa_sof_pos])
    kpa_fs_history = np.vstack([kpa_fs_path_to_current, kpa_fs_pos])


    # =========================================================
    # 4. 화살표 벡터 계산 (이전 코드와 동일)
    # =========================================================

    def calculate_direction_vector(current, target, length):
        direction_vector = target - current
        if np.linalg.norm(direction_vector) == 0:
            return np.array([0, 0])
        
        unit_vector = direction_vector / np.linalg.norm(direction_vector)
        return unit_vector * length
    
    def calculate_clockwise_angle(current, target):
        """
        현재 위치에서 목표 위치로 향하는 방향을 시계 방향 각도(0~360도)로 계산합니다.
        0도는 위쪽(북쪽), 시계 방향으로 증가합니다.
        """
        delta_x = target[0] - current[0]
        delta_y = target[1] - current[1]
        
        # 두 점이 같으면 각도 계산 불가
        if delta_x == 0 and delta_y == 0:
            return None # 또는 0 등 예외 값 반환
        
        # 1. 표준 반시계 방향 각도 (라디안) 계산. np.arctan2(delta_y, delta_x) 사용.
        # 결과 범위는 [-pi, pi]
        angle_rad = np.arctan2(delta_y, delta_x)
        
        # 2. 각도를 도(Degree)로 변환
        angle_deg = np.degrees(angle_rad)
        
        # 3. 표준 각도 (0~360)로 정규화 (반시계 방향)
        # 0도는 양의 X축(오른쪽) 기준
        standard_angle = (angle_deg + 360) % 360
        
        # 4. 시계 방향 각도로 변환
        # 0도를 북쪽(90도)으로 기준을 잡고 시계 방향으로 증가
        # (360 - standard_angle)는 표준 각도를 시계 방향으로 바꾼 것이며, 
        # 여기에 90을 더하고 360으로 나눈 나머지를 취하여 북쪽을 0도로 정규화합니다.
        
        # 더 간단한 방법: 표준 각도를 90도만큼 반시계로 돌리고 360에서 뺌
        # 90도 (위) -> 0도
        # 0도 (오른쪽) -> 90도
        # 270도 (아래) -> 180도
        # 180도 (왼쪽) -> 270도
        
        clockwise_angle = (360 - standard_angle + 90) % 360
        
        return clockwise_angle

    rok_ew_direction_vector = calculate_direction_vector(rok_ew_pos, rok_ew_next_pos, ARROW_LENGTH)
    rok_scouts_direction_vector = calculate_direction_vector(rok_scouts_pos, rok_scouts_next_pos, ARROW_LENGTH)
    rok_main_direction_vector = calculate_direction_vector(rok_main_pos, rok_main_next_pos, ARROW_LENGTH)
    kpa_ew_direction_vector = calculate_direction_vector(kpa_ew_pos, kpa_ew_next_pos, ARROW_LENGTH)
    kpa_sof_direction_vector = calculate_direction_vector(kpa_sof_pos, kpa_sof_next_pos, ARROW_LENGTH)
    # kpa_fs_direction_vector = calculate_direction_vector(kpa_fs_pos, kpa_fs_next_pos, ARROW_LENGTH)
    
    # =========================================================
    # 5. 시각화 (배경 이미지 적용 및 요소 표시)
    # =========================================================
    fig, ax = plt.subplots(figsize=(8, 8))
    
    # --- 배경 이미지 로드 및 적용 ---
    try:
        background_img = Image.open("map.png") 
        ax.imshow(background_img, extent=[0, 296.6, 0, 166.5], zorder=0, aspect='auto')
    except FileNotFoundError:
        st.warning("경고: 'map.png' 파일을 찾을 수 없습니다. 배경 이미지 없이 시각화를 진행합니다.")
        ax.set_facecolor('lightgrey') 
    except Exception as e:
        st.warning(f"경고: 배경 이미지 로드 중 오류 발생: {e}. 배경 이미지 없이 시각화를 진행합니다.")
        ax.set_facecolor('lightgrey')

    # --- 영향권 원 추가 ---
    rok_ew_circle = Circle((rok_ew_pos[0], rok_ew_pos[1]), radius=rok_ew_radius, edgecolor='red', facecolor='none', linestyle='-', linewidth=1.5, alpha=1)
    # rok_scouts_circle = Circle((rok_scouts_pos[0], rok_scouts_pos[1]), radius=rok_scouts_radius, edgecolor='purple', facecolor='none', linestyle='-', linewidth=1.5, alpha=0.4)
    kpa_ew_circle = Circle((kpa_ew_pos[0], kpa_ew_pos[1]), radius=kpa_ew_radius, edgecolor='black', facecolor='none', linestyle='-', linewidth=1.5, alpha=1)

    ax.add_patch(rok_ew_circle)
    # ax.add_patch(rok_scouts_circle)
    ax.add_patch(kpa_ew_circle)

    # --- 방향 화살표 추가 (축소된 크기) ---
    ARROW_WIDTH = 0.005
    HEAD_WIDTH = 3
    HEAD_LENGTH = 4
    
    if np.linalg.norm(rok_ew_direction_vector) > 0:
        ax.quiver(
            rok_ew_pos[0], rok_ew_pos[1], 
            rok_ew_direction_vector[0], rok_ew_direction_vector[1], 
            color='magenta', scale=1, scale_units='xy', angles='xy', 
            width=ARROW_WIDTH, headwidth=HEAD_WIDTH, headlength=HEAD_LENGTH, zorder=6, label='아군 다음 이동 방향'
        )
    
    if current_time_offset < 180 and np.linalg.norm(rok_scouts_direction_vector) > 0:
        ax.quiver(
            rok_scouts_pos[0], rok_scouts_pos[1], 
            rok_scouts_direction_vector[0], rok_scouts_direction_vector[1], 
            color='magenta', scale=1, scale_units='xy', angles='xy', 
            width=ARROW_WIDTH, headwidth=HEAD_WIDTH, headlength=HEAD_LENGTH, zorder=6, label='적군 다음 이동 방향'
        )
    
    if np.linalg.norm(rok_main_direction_vector) > 0:
        ax.quiver(
            rok_main_pos[0], rok_main_pos[1], 
            rok_main_direction_vector[0], rok_main_direction_vector[1], 
            color='magenta', scale=1, scale_units='xy', angles='xy', 
            width=ARROW_WIDTH, headwidth=HEAD_WIDTH, headlength=HEAD_LENGTH, zorder=6, label='적군 다음 이동 방향'
        )

    if np.linalg.norm(kpa_ew_direction_vector) > 0:
        ax.quiver(
            kpa_ew_pos[0], kpa_ew_pos[1], 
            kpa_ew_direction_vector[0], kpa_ew_direction_vector[1], 
            color='cyan', scale=1, scale_units='xy', angles='xy', 
            width=ARROW_WIDTH, headwidth=HEAD_WIDTH, headlength=HEAD_LENGTH, zorder=6, label='적군 다음 이동 방향'
        )

    if np.linalg.norm(kpa_sof_direction_vector) > 0:
        ax.quiver(
            kpa_sof_pos[0], kpa_sof_pos[1], 
            kpa_sof_direction_vector[0], kpa_sof_direction_vector[1], 
            color='cyan', scale=1, scale_units='xy', angles='xy', 
            width=ARROW_WIDTH, headwidth=HEAD_WIDTH, headlength=HEAD_LENGTH, zorder=6, label='적군 다음 이동 방향'
        )

    # print(calculate_clockwise_angle(rok_ew_pos, rok_ew_next_pos))
    # print(calculate_clockwise_angle(rok_scouts_pos, rok_scouts_next_pos))
    # print(calculate_clockwise_angle(rok_main_pos, rok_main_next_pos))
    # print(calculate_clockwise_angle(kpa_ew_pos, kpa_ew_next_pos))
    # print(calculate_clockwise_angle(kpa_sof_pos, kpa_sof_next_pos))

    # if np.linalg.norm(kpa_fs_direction_vector) > 0:
    #     ax.quiver(
    #         kpa_fs_pos[0], kpa_fs_pos[1], 
    #         kpa_fs_direction_vector[0], kpa_fs_direction_vector[1], 
    #         color='cyan', scale=1, scale_units='xy', angles='xy', 
    #         width=ARROW_WIDTH, headwidth=HEAD_WIDTH, headlength=HEAD_LENGTH, zorder=6, label='적군 다음 이동 방향'
    #     )

    # --- 경로 및 위치 시각화 ---
    # ax.plot(ALLY_PATH[:, 0], ALLY_PATH[:, 1], 'b:', alpha=0.2, label='전체 아군 경로', zorder=1)
    # ax.plot(ENEMY_PATH[:, 0], ENEMY_PATH[:, 1], 'r:', alpha=0.2, label='전체 적군 경로', zorder=1)

    # 현재까지 이동한 경로를 실선으로 표시
    ax.plot(rok_ew_history[:, 0], rok_ew_history[:, 1], 'r-', alpha=0.7, zorder=2) 
    if current_time_offset < 180:
        ax.plot(rok_scouts_history[:, 0], rok_scouts_history[:, 1], 'r-', alpha=0.7, zorder=2)
    ax.plot(rok_main_history[:, 0], rok_main_history[:, 1], 'r-', alpha=0.7, zorder=2)
    ax.plot(kpa_ew_history[:, 0], kpa_ew_history[:, 1], 'b-', alpha=0.7, zorder=2)
    ax.plot(kpa_sof_history[:, 0], kpa_sof_history[:, 1], 'b-', alpha=0.7, zorder=2)
    ax.plot(kpa_fs_history[:, 0], kpa_fs_history[:, 1], 'b-', alpha=0.7, zorder=2)
        
    # 현재 위치 시각화 (더 크게)
    ax.scatter(rok_ew_pos[0], rok_ew_pos[1], marker='^', color='red', s=250, label='rok_ew 현재위치', zorder=5)
    if current_time_offset < 180:
        ax.scatter(rok_scouts_pos[0], rok_scouts_pos[1], marker='X', color='red', s=250, label='rok_scouts 현재위치', zorder=5)
    ax.scatter(rok_main_pos[0], rok_main_pos[1], marker='s', color='red', s=250, label='rok_main 현재위치', zorder=5)
    ax.scatter(kpa_ew_pos[0], kpa_ew_pos[1], marker='o', color='blue', s=250, label='kpa_ew 현재위치', zorder=5)
    ax.scatter(kpa_sof_pos[0], kpa_sof_pos[1], marker='d', color='blue', s=250, label='kpa_sof 현재위치', zorder=5)
    ax.scatter(kpa_fs_pos[0], kpa_fs_pos[1], marker='*', color='blue', s=250, label='kpa_fs 현재위치', zorder=5)
    
    # 하드코딩된 틱 포인트를 작은 점으로 표시
    # ax.scatter(ALLY_PATH[:, 0], ALLY_PATH[:, 1], marker='.', color='blue', s=50, alpha=0.5, zorder=3)
    # ax.scatter(ENEMY_PATH[:, 0], ENEMY_PATH[:, 1], marker='.', color='red', s=50, alpha=0.5, zorder=3)
    
    # 축 및 제목 설정
    ax.set_xlim(0, 296.6)
    ax.set_ylim(0, 166.5)
    ax.set_xticks(np.arange(0, 296.7, 10))
    ax.set_yticks(np.arange(0, 166.6, 10))
    ax.set_xlabel("X 좌표")
    ax.set_ylabel("Y 좌표")
    ax.set_title(f"적/아군 위치: 배경 맵 적용 ({current_time_offset:.1f}초 경과)")
    ax.grid(True, linestyle=':', alpha=0.7)
    ax.set_aspect('equal', adjustable='box')
    
    # 범례 설정
    handles, labels = ax.get_legend_handles_labels()
    custom_handles = [
        plt.Line2D([], [], color='blue', linestyle='--', alpha=0.7, label='아군 영향권'),
        plt.Line2D([], [], color='green', linestyle='--', alpha=0.7, label='적군 영향권'),
        plt.Line2D([], [], color='cyan', marker='>', linestyle='None', label='아군 방향'),
        plt.Line2D([], [], color='magenta', marker='>', linestyle='None', label='적군 방향')
    ]
    by_label = dict(zip(labels, handles))
    by_label.update(dict(zip([h.get_label() for h in custom_handles], custom_handles)))
    
    ax.legend(by_label.values(), by_label.keys(), loc='lower left', fontsize=9)
    
    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)
    
    st.info(f"현재 시간: **{current_time_offset:.1f}초** | 아군 위치: **({rok_ew_pos[0]:.1f}, {rok_ew_pos[1]:.1f})** | 적군 위치: **({rok_scouts_pos[0]:.1f}, {rok_scouts_pos[1]:.1f})**")


# --- 3. Streamlit UI 및 시뮬레이션 로직 ---

st.title("🛡️ SHORAD 작전 시뮬레이터 (시나리오 3)")
st.caption(f"기준 시간: {BASE_TIME.strftime('%Y-%m-%d %H:%M:%S')} | 시나리오: 복합 통합 공격 대응")

# 슬라이더 설정
max_time = df_events['time_offset'].max()
slider_time = st.slider(
    "시간 진행 (초)",
    min_value=0,
    max_value=max_time,
    value=0,
    step=30,
    format="%d초"
)

# 현재 시각 계산
current_time = BASE_TIME + datetime.timedelta(seconds=slider_time)
st.markdown(f"## ⏱️ 현재 시각: **{current_time.strftime('%H:%M:%S')}**")

# --- A. 시각화 플롯 표시 ---
# plot_defense_status(slider_time)
plot_hardcoded_movement_at_time(slider_time)

st.divider()

# --- B. 실시간 로그 표시 ---
st.subheader("작전 상황 로그")

current_events = df_events[df_events['time_offset'] <= slider_time]

if current_events.empty:
    st.info("아직 이벤트가 발생하지 않았습니다. 시간을 진행해 주세요.")
else:
    # 가장 최근 이벤트를 중심으로 보여주기 위해 역순 정렬
    current_events_sorted = current_events.sort_values(by='time_offset', ascending=False)
    
    # 로그를 테이블로 표시
    st.dataframe(
        current_events_sorted[['time_stamp', 'category', 'event', 'details']],
        hide_index=True,
        column_config={
            "time_stamp": st.column_config.DatetimeColumn("시간", format="HH:mm:ss", width="small"),
            "category": "분류",
            "event": "주요 이벤트",
            "details": "상세 설명 및 교리 적용"
        }
    )

# --- C. 교범/방책 검색 Context 예시 ---
st.divider()
st.subheader("💡 RAG(방책 검색) 필요 시점 분석 (10:03:30)")

if slider_time >= 270:
    st.success("🚨 **CM 요격 실패! 긴급 방책 검색 필요.**")
    st.write("Avenger의 CM 요격 실패로 목표 자산에 대한 위험도가 증가했습니다. 교범 기반의 즉각적인 방책 도출이 필요합니다.")
    
    st.markdown("""
    **✅ RAG 검색 Context Keywords (DB 기반 추출):**
    - `CM 최종 방어 실패`
    - `UAS 근접 침투`
    - `센서 저하`
    - `SHORAD 상호 지원 재배치`
    """)

    st.info("**(LLM/RAG의 방책 생성 예시):** '교범의 [회복 탄력성] 교리에 따라, EW 공격의 영향을 받지 않은 인접 Avenger 포대 2의 사격 구역을 항만 핵심 시설로 긴급 재할당(상호 지원)하고, Sentinel의 수동 보고 체계를 활성화합니다.'")
elif slider_time >= 90:
     st.warning("⚠️ **복합 공격 및 EW 공격 감지.**")
     st.write("Patriot가 고고도 위협에 집중하는 동안, 저고도 위협(CM, UAS)에 대한 SHORAD의 방어 임무 준비가 중요합니다. 교범의 **방어 심층화**가 작동 중입니다.")
else:
    st.info("작전 초기 단계입니다. 모든 시스템이 정상 대기 상태입니다.")