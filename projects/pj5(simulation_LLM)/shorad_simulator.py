import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Arrow
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from PIL import Image
import datetime
import numpy as np

# --- 한글 폰트 설정 (이 부분을 추가) ---
import matplotlib.font_manager as fm
# 시스템에 설치된 나눔고딕 폰트 경로를 찾아서 설정
font_path = 'C:/Windows/Fonts/malgun.ttf'  # Windows 기준
font_name = fm.FontProperties(fname=font_path, size=10).get_name()
plt.rc('font', family=font_name)
plt.rcParams['axes.unicode_minus'] = False # 마이너스 기호 깨짐 방지
# ----------------------------------------

st.markdown(
    """
    <style>
    /* 전체 메인 컨테이너의 최대 너비를 1200px로 설정 (원하는 크기로 조절) */
    .stApp .main .block-container {
        max-width: 1200px; 
        padding-left: 2rem;
        padding-right: 2rem;
    }
    /* 또는 더 최신 버전의 클래스명을 사용할 수 있습니다 (브라우저 개발자 도구로 확인 권장) */
    section[data-testid="stMain"] > div[data-testid="stMainBlockContainer"] {
        max-width: 1200px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# --- 1. 데이터베이스(DataFrame) 초기 설정 ---
# 시나리오 3 (복합 통합 공격 대응) 기반 데이터

# 기준 시간 설정 (T0)
BASE_TIME = datetime.datetime(2025, 10, 13, 15, 0, 0)

# 시뮬레이션 이벤트 목록 (시간 순서대로)
events = [
    # T0: 임무 시작
    (0, "SYSTEM", "작전 시작", "주요 항만 방어 임무 개시. 교리: 방어 심층화, 통합."),
    
    # T1: 1분 30초: 공격 개시 (SRBM, CM, UAS) 및 EW 영향
    (3, "THREAT", "복합 통합 공격 개시", "SRBM(고고도), CM(중고도), UAS(저고도) 동시 탐지."),
    (3, "THREAT", "EW 공격 감지", "CM, UAS 위협과 동반. Sentinel 레이더 부분 성능 저하."),
    (3, "DEFENSE", "Patriot", "SRBM에 대한 HIMAD(고고도 방어) 교전 준비 완료."),
    (3, "DEFENSE", "Avenger", "CM, UAS에 대한 SHORAD(최종 방어) 대기."),

    # T2: 2분 45초: Patriot SRBM 교전
    (6, "ENGAGEMENT", "Patriot SRBM 교전", "Patriot, SRBM 요격 성공. (방어 심층화 1단계 성공)"),
    (6, "THREAT", "CM, UAS 위협 유지", "CM이 방어 계층을 통과하여 최종 방어선 접근 중."),
    (6, "DEFENSE", "Patriot", "탄약 2발 소모, 재장전/대기 상태."),

    # T3: 3분 30초: Avenger CM/UAS 교전 시작
    (7, "ENGAGEMENT", "Avenger CM 교전 시작", "Avenger, CM 요격 시작. (SHORAD 임무 인계)"),
    (7, "ENGAGEMENT", "Avenger UAS 교전 시작", "Avenger, 근접 UAS 요격 시작. (복합 공격 대응)"),
    (7, "DEFENSE", "Avenger", "탄약 소모 시작. 상호 지원 및 회복 탄력성 점검 필요."),

    # T4: 4분 30초: UAS 1기 격파, CM 요격 실패 (가정)
    (9, "ENGAGEMENT", "UAS 격파 성공", "Avenger, UAS 1기 격파. CM 요격은 실패. (방책 조정 필요)"),
    (9, "THREAT", "CM 잔존", "CM이 목표에 근접, 피해 발생 위험 증가."),
    
    # T5: 5분 00초: 최종 방책 적용 및 상황 종료
    (15, "SYSTEM", "방책 적용/상황 종료", "교범 검색 기반 방책: 인접 SHORAD 자산의 상호 지원 재배치 완료.")
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
    # st.subheader("적/아군 2차원 위치 추이: 배경 맵 적용 시뮬레이션")
    
    # =========================================================
    # 1. 하드코딩된 경로 정의 (이전 코드와 동일)
    # =========================================================
    
    KPA_PLATOON1 = np.array([
        [46.0, 223.5],
        [46.0, 223.5],
        [46.0, 223.5],
        [46.0, 223.5],
        [46.0, 223.5],
        [46.0, 223.5],
        [46.0, 223.5],
        [46.0, 223.5],
        [46.0, 223.5],
        [46.0, 223.5],
        [46.0, 223.5],
        [60.0, 206.5],
        [90.0, 188.5],
        [100.4, 170.2],
        [110.0, 150.5],
        [120.0, 130.5]
    ])
    KPA_PLATOON2 = np.array([
        [51.6, 190.9],
        [63.7, 144.8],
        [94.4, 110.9],
        [134.0, 99.6],
        [162.2, 101.4],
        [162.2, 101.4],
        [162.2, 101.4],
        [162.2, 101.4],
        [190.2, 110.4],
        [218.2, 108.4],
        [230.2, 90.4],
        [250.1, 72.2],
        [260.2, 54.4],
        [275.0, 37.4],
        [290.2, 32.4],
        [295.2, 22.4]
    ])
    KPA_LEADER = np.array([
        [95.2, 194.9],
        [95.2, 194.9],
        [95.2, 194.9],
        [95.2, 194.9],
        [95.2, 194.9],
        [95.2, 194.9],
        [95.2, 194.9],
        [95.2, 194.9],
        [95.2, 194.9],
        [95.2, 194.9],
        [95.2, 194.9],
        [107.2, 175.4],
        [135.2, 165.9],
        [158.2, 145.9],
        [165.2, 130.9],
        [184.2, 120.9]
    ])
    KPA_ARTILLERY = np.array([
        [138.9, 239.7],
        [138.9, 239.7],
        [138.9, 239.7],
        [138.9, 239.7],
        [138.9, 239.7],
        [138.9, 239.7],
        [138.9, 239.7],
        [138.9, 239.7],
        [138.9, 239.7],
        [138.9, 239.7],
        [138.9, 239.7],
        [138.9, 239.7],
        [138.9, 239.7],
        [138.9, 239.7],
        [138.9, 239.7],
        [138.9, 239.7],
    ])
    KPA_SQUAD = np.array([
        [197.8, 181.9],
        [197.8, 181.9],
        [197.8, 181.9],
        [197.8, 181.9],
        [197.8, 181.9],
        [235.8, 192.9],
        [235.8, 192.9],        
        [235.8, 192.9],
        [228.8, 168.9],
        [220.8, 155.9],
        [225.8, 130.9],
        [210.4, 120.4],
        [220.8, 92.9],
        [218.8, 70.9],
        [230.8, 55.2],
        [243.8, 50.9]
    ])
    KPA_SECTION = np.array([
        [204.3, 254.3],
        [204.3, 254.3],
        [204.3, 254.3],
        [222.1, 245.8],
        [242.3, 230.3],
        [263.3, 212.3],
        [263.3, 212.3],
        [263.3, 212.3],
        [263.3, 185.0],
        [250.3, 170.3],
        [246.3, 140.3],
        [230.3, 125.3],
        [234.3, 100.3],
        [240.3, 85.3],
        [230.3, 75.3],
        [250.3, 68.3]
    ])
    KPA_SECTION2 = np.array([
        [449.1, 254.3],
        [428.9, 221.6],
        [442.6, 186.8],
        [420.0, 165.8],
        [420.0, 165.8],
        [420.0, 165.8],
        [420.0, 165.8],
        [420.0, 165.8],
        [420.0, 165.8],
        [420.0, 165.8],
        [410.1, 145.3],
        [423.1, 138.3],
        [433.1, 117.3],
        [460.1, 102.3],
        [460.1, 102.3],
        [460.1, 102.3]
    ])
    ROK_SQUAD = np.array([
        [350.4, 95.9],
        [336.1, 108.0],
        [332.4, 129.3],
        [322.4, 150.2],
        [310.4, 165.6],
        [310.4, 165.6],
        [310.4, 165.6],
        [310.4, 165.6],
        [310.4, 165.6],
        [310.4, 165.6],
        [310.4, 165.6],
        [310.4, 165.6],
        [310.4, 165.6],
        [310.4, 165.6],
        [310.4, 165.6],
        [310.4, 165.6]
    ])
    ROK_SQUAD2 = np.array([
        [295.1, 49.5],
        [288.5, 66.8],
        [276.2, 80.9],
        [256.1, 87.5],
        [253.1, 110.5],
        [253.1, 110.5],
        [253.1, 110.5],
        [253.1, 110.5],
        [253.1, 110.5],
        [253.1, 110.5],
        [253.1, 110.5],
        [253.1, 110.5],
        [253.1, 110.5],
        [253.1, 110.5],
        [253.1, 110.5],
        [253.1, 110.5]
    ])
    ROK_LEADER = np.array([
        [378.8, 55.2],
        [361.8, 62.2],
        [357.8, 77.2],
        [366.8, 85.2],
        [355.2, 110.1],
        [355.2, 110.1],
        [355.2, 110.1],
        [355.2, 110.1],
        [355.2, 110.1],
        [355.2, 110.1],
        [355.2, 110.1],
        [355.2, 110.1],
        [355.2, 110.1],
        [355.2, 110.1],
        [355.2, 110.1],
        [355.2, 110.1]
    ])
    
    total_time = 15
    tick_interval = 1
    ARROW_LENGTH = 15
    map_x_value = 494.3
    map_y_value = 278.3

    # 현재 시간을 300초 내로 제한
    if current_time_offset < 0:
        current_time_offset = 0
    if current_time_offset > total_time:
        current_time_offset = total_time

    kpa_platoon2_radius = 130
    kpa_section2_radius = 130

    # =========================================================
    # 3. 현재 위치 및 다음 목표 위치 계산 (오류 수정 지점)
    # =========================================================
    current_tick_index = int(current_time_offset // tick_interval)
    
    # 🚨 UnboundLocalError 수정 로직:
    if current_time_offset == total_time: # 10초일 경우
        current_tick_index = len(KPA_PLATOON1) - 1 # 마지막 인덱스 (10)
        kpa_platoon1_pos = KPA_PLATOON1[current_tick_index]
        kpa_platoon2_pos = KPA_PLATOON2[current_tick_index]
        kpa_leader_pos = KPA_LEADER[current_tick_index]
        kpa_artillery_pos = KPA_ARTILLERY[current_tick_index]
        kpa_squad_pos = KPA_SQUAD[current_tick_index]
        kpa_section_pos = KPA_SECTION[current_tick_index]
        kpa_section2_pos = KPA_SECTION2[current_tick_index]
        rok_squad_pos = ROK_SQUAD[current_tick_index]
        rok_squad2_pos = ROK_SQUAD2[current_tick_index]
        rok_leader_pos = ROK_LEADER[current_tick_index]

                
        # 다음 이동할 위치를 현재 위치와 동일하게 설정 (화살표 벡터 0)
        kpa_platoon1_next_pos = kpa_platoon1_pos
        kpa_platoon2_next_pos = kpa_platoon2_pos
        kpa_leader_next_pos = kpa_leader_pos
        kpa_artillery_next_pos = kpa_artillery_pos
        kpa_squad_next_pos = kpa_squad_pos
        kpa_section_next_pos = kpa_section_pos
        kpa_section2_next_pos = kpa_section2_pos
        rok_squad_next_pos = rok_squad_pos
        rok_squad2_next_pos = rok_squad2_pos
        rok_leader_next_pos = rok_leader_pos
        
        
    else: # 0초부터 299.9초 사이일 경우
        # 현재 위치 (선형 보간) 계산
        start_time_of_current_tick = current_tick_index * tick_interval
        time_in_tick = current_time_offset - start_time_of_current_tick
        movement_ratio_between_ticks = time_in_tick / tick_interval
        
        kpa_platoon1_start_pos = KPA_PLATOON1[current_tick_index]
        kpa_platoon1_next_pos_tick = KPA_PLATOON1[current_tick_index + 1]
        kpa_platoon2_start_pos = KPA_PLATOON2[current_tick_index]
        kpa_platoon2_next_pos_tick = KPA_PLATOON2[current_tick_index + 1]
        kpa_leader_start_pos = KPA_LEADER[current_tick_index]
        kpa_leader_next_pos_tick = KPA_LEADER[current_tick_index + 1]
        kpa_artillery_start_pos = KPA_ARTILLERY[current_tick_index]
        kpa_artillery_next_pos_tick = KPA_ARTILLERY[current_tick_index + 1]
        kpa_squad_start_pos = KPA_SQUAD[current_tick_index]
        kpa_squad_next_pos_tick = KPA_SQUAD[current_tick_index + 1]
        kpa_section_start_pos = KPA_SECTION[current_tick_index]
        kpa_section_next_pos_tick = KPA_SECTION[current_tick_index + 1]
        kpa_section2_start_pos = KPA_SECTION2[current_tick_index]
        kpa_section2_next_pos_tick = KPA_SECTION2[current_tick_index + 1]
        rok_squad_start_pos = ROK_SQUAD[current_tick_index]
        rok_squad_next_pos_tick = ROK_SQUAD[current_tick_index + 1]
        rok_squad2_start_pos = ROK_SQUAD2[current_tick_index]
        rok_squad2_next_pos_tick = ROK_SQUAD2[current_tick_index + 1]
        rok_leader_start_pos = ROK_LEADER[current_tick_index]
        rok_leader_next_pos_tick = ROK_LEADER[current_tick_index + 1]
        
        
        kpa_platoon1_pos = kpa_platoon1_start_pos + (kpa_platoon1_next_pos_tick - kpa_platoon1_start_pos) * movement_ratio_between_ticks
        kpa_platoon2_pos = kpa_platoon2_start_pos + (kpa_platoon2_next_pos_tick - kpa_platoon2_start_pos) * movement_ratio_between_ticks
        kpa_leader_pos = kpa_leader_start_pos + (kpa_leader_next_pos_tick - kpa_leader_start_pos) * movement_ratio_between_ticks
        kpa_artillery_pos = kpa_artillery_start_pos + (kpa_artillery_next_pos_tick - kpa_artillery_start_pos) * movement_ratio_between_ticks
        kpa_squad_pos = kpa_squad_start_pos + (kpa_squad_next_pos_tick - kpa_squad_start_pos) * movement_ratio_between_ticks
        kpa_section_pos = kpa_section_start_pos + (kpa_section_next_pos_tick - kpa_section_start_pos) * movement_ratio_between_ticks
        kpa_section2_pos = kpa_section2_start_pos + (kpa_section2_next_pos_tick - kpa_section2_start_pos) * movement_ratio_between_ticks
        rok_squad_pos = rok_squad_start_pos + (rok_squad_next_pos_tick - rok_squad_start_pos) * movement_ratio_between_ticks
        rok_squad2_pos = rok_squad2_start_pos + (rok_squad2_next_pos_tick - rok_squad2_start_pos) * movement_ratio_between_ticks
        rok_leader_pos = rok_leader_start_pos + (rok_leader_next_pos_tick - rok_leader_start_pos) * movement_ratio_between_ticks
        
        
        # 다음 틱의 위치를 화살표의 목표 지점으로 설정
        kpa_platoon1_next_pos = kpa_platoon1_next_pos_tick
        kpa_platoon2_next_pos = kpa_platoon2_next_pos_tick
        kpa_leader_next_pos = kpa_leader_next_pos_tick
        kpa_artillery_next_pos = kpa_artillery_next_pos_tick
        kpa_squad_next_pos = kpa_squad_next_pos_tick
        kpa_section_next_pos = kpa_section_next_pos_tick
        kpa_section2_next_pos = kpa_section2_next_pos_tick
        rok_squad_next_pos = rok_squad_next_pos_tick
        rok_squad2_next_pos = rok_squad2_next_pos_tick
        rok_leader_next_pos = rok_leader_next_pos_tick
        

    # 현재까지 지나온 경로 포인트를 추출 및 현재 위치 추가
    kpa_platoon1_path_to_current = KPA_PLATOON1[:current_tick_index + 1]
    kpa_platoon2_path_to_current = KPA_PLATOON2[:current_tick_index + 1]
    kpa_leader_path_to_current = KPA_LEADER[:current_tick_index + 1]
    kpa_artillery_path_to_current = KPA_ARTILLERY[:current_tick_index + 1]
    kpa_squad_path_to_current = KPA_SQUAD[:current_tick_index + 1]
    kpa_section_path_to_current = KPA_SECTION[:current_tick_index + 1]
    kpa_section2_path_to_current = KPA_SECTION2[:current_tick_index + 1]
    rok_squad_path_to_current = ROK_SQUAD[:current_tick_index + 1]
    rok_squad2_path_to_current = ROK_SQUAD2[:current_tick_index + 1]
    rok_leader_path_to_current = ROK_LEADER[:current_tick_index + 1]

    
    kpa_platoon1_history = np.vstack([kpa_platoon1_path_to_current, kpa_platoon1_pos])
    kpa_platoon2_history = np.vstack([kpa_platoon2_path_to_current, kpa_platoon2_pos])
    kpa_leader_history = np.vstack([kpa_leader_path_to_current, kpa_leader_pos])
    kpa_artillery_history = np.vstack([kpa_artillery_path_to_current, kpa_artillery_pos])
    kpa_squad_history = np.vstack([kpa_squad_path_to_current, kpa_squad_pos])
    kpa_section_history = np.vstack([kpa_section_path_to_current, kpa_section_pos])
    kpa_section2_history = np.vstack([kpa_section2_path_to_current, kpa_section2_pos])
    rok_squad_history = np.vstack([rok_squad_path_to_current, rok_squad_pos])
    rok_squad2_history = np.vstack([rok_squad2_path_to_current, rok_squad2_pos])
    rok_leader_history = np.vstack([rok_leader_path_to_current, rok_leader_pos])

    # =========================================================
    # 4. 화살표 벡터 계산 (이전 코드와 동일)
    # =========================================================

    # def calculate_direction_vector(current, target, length):
    #     direction_vector = target - current
    #     if np.linalg.norm(direction_vector) == 0:
    #         return np.array([0, 0])
        
    #     unit_vector = direction_vector / np.linalg.norm(direction_vector)
    #     return unit_vector * length
    
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
    
    # 이미지 마커를 추가하는 도우미 함수 정의
    def add_image_marker(ax, xy, image_path, zoom_scale=0.15, label=''):
        """주어진 좌표에 PNG 파일을 마커로 추가합니다."""
        try:
            # 1. 이미지 로드
            img = Image.open(image_path).convert("RGBA")
            
            # 2. OffsetImage 객체 생성 (zoom_scale로 크기 조절)
            image_offset = OffsetImage(img, zoom=zoom_scale, 
                                   # cmap='viridis'와 같은 기본 컬러맵이 적용되는 것을 방지
                                   # 이 부분이 핵심입니다.
                                   # 이미지가 RGBA이므로, cmap='gray'나 cmap=None 둘 다 잘 작동합니다.
                                   # 확실하게 원본 색상을 유지하려면 Image.open().convert("RGBA")가 가장 좋습니다.
                                   # 만약 convert("RGBA") 후에도 문제가 발생하면, imshow_kwargs={'cmap': None}을 시도해보세요.
                                   )
            image_offset.image.axes = ax
            
            # 3. AnnotationBbox 객체 생성 (이미지를 xy 좌표에 배치)
            ab = AnnotationBbox(
                image_offset, 
                xy, 
                xycoords='data', 
                frameon=False, # 이미지 주변의 테두리 제거
                pad=0.0,
                zorder=7 # 다른 요소들 위에 표시되도록 zorder 높게 설정
            )
            ax.add_artist(ab)
            
            # 4. 범례를 위해 투명한 스캐터 플롯 항목 추가 (선택 사항, 레이블 표시용)
            ax.scatter(xy[0], xy[1], marker='o', color='none', s=0, label=label, zorder=6)

        except FileNotFoundError:
            print(f"경고: {image_path} 파일을 찾을 수 없습니다. 기본 마커를 사용합니다.")
            # 파일이 없을 경우 기본 마커 (예: 파란색 별)를 표시
            ax.scatter(xy[0], xy[1], marker='*', color='blue', s=250, label=label, zorder=5)
        except Exception as e:
            print(f"경고: 이미지 처리 중 오류 발생: {e}. 기본 마커를 사용합니다.")
            ax.scatter(xy[0], xy[1], marker='*', color='blue', s=250, label=label, zorder=5)

    # kpa_platoon1_direction_vector = calculate_direction_vector(kpa_platoon1_pos, kpa_platoon1_next_pos, ARROW_LENGTH)
    # kpa_platoon2_direction_vector = calculate_direction_vector(kpa_platoon2_pos, kpa_platoon2_next_pos, ARROW_LENGTH)
    # kpa_leader_direction_vector = calculate_direction_vector(kpa_leader_pos, kpa_leader_next_pos, ARROW_LENGTH)
    # kpa_artillery_direction_vector = calculate_direction_vector(kpa_artillery_pos, kpa_artillery_next_pos, ARROW_LENGTH)
    # kpa_squad_direction_vector = calculate_direction_vector(kpa_squad_pos, kpa_squad_next_pos, ARROW_LENGTH)
    # kpa_section_direction_vector = calculate_direction_vector(kpa_section_pos, kpa_section_next_pos, ARROW_LENGTH)
    # kpa_section2_direction_vector = calculate_direction_vector(kpa_section2_pos, kpa_section2_next_pos, ARROW_LENGTH)
    # rok_squad_direction_vector = calculate_direction_vector(rok_squad_pos, rok_squad_next_pos, ARROW_LENGTH)
    # rok_squad2_direction_vector = calculate_direction_vector(rok_squad2_pos, rok_squad2_next_pos, ARROW_LENGTH)
    # rok_leader_direction_vector = calculate_direction_vector(rok_leader_pos, rok_leader_next_pos, ARROW_LENGTH)
    
    # kpa_fs_direction_vector = calculate_direction_vector(kpa_fs_pos, kpa_fs_next_pos, ARROW_LENGTH)
    
    # =========================================================
    # 5. 시각화 (배경 이미지 적용 및 요소 표시)
    # =========================================================
    fig, ax = plt.subplots(figsize=(8, 8))
    
    # --- 배경 이미지 로드 및 적용 ---
    try:
        background_img = Image.open("res/field.png") 
        ax.imshow(background_img, extent=[0, map_x_value, 0, map_y_value], zorder=0, aspect='auto')
    except FileNotFoundError:
        st.warning("경고: 'field.png' 파일을 찾을 수 없습니다. 배경 이미지 없이 시각화를 진행합니다.")
        ax.set_facecolor('lightgrey') 
    except Exception as e:
        st.warning(f"경고: 배경 이미지 로드 중 오류 발생: {e}. 배경 이미지 없이 시각화를 진행합니다.")
        ax.set_facecolor('lightgrey')

    # --- 영향권 원 추가 ---
    # kpa_platoon2_circle = Circle((kpa_platoon2_pos[0], kpa_platoon2_pos[1]), radius=kpa_platoon2_radius, edgecolor='red', facecolor='none', linestyle='-', linewidth=1.5, alpha=1)
    # kpa_section2_circle = Circle((kpa_section2_pos[0], kpa_section2_pos[1]), radius=kpa_section2_radius, edgecolor='red', facecolor='none', linestyle='-', linewidth=1.5, alpha=1)
    kpa_platoon2_circle = Circle((kpa_platoon2_pos[0], kpa_platoon2_pos[1]), radius=kpa_platoon2_radius, edgecolor='yellow', facecolor='none', linestyle='-', linewidth=1.5, alpha=1)
    kpa_section2_circle = Circle((kpa_section2_pos[0], kpa_section2_pos[1]), radius=kpa_section2_radius, edgecolor='yellow', facecolor='none', linestyle='-', linewidth=1.5, alpha=1)
    kpa_platoon2_circle_line = Circle((kpa_platoon2_pos[0], kpa_platoon2_pos[1]), radius=kpa_platoon2_radius, color='yellow', linestyle='-', linewidth=1.5, alpha=0.2)
    kpa_section2_circle_line = Circle((kpa_section2_pos[0], kpa_section2_pos[1]), radius=kpa_section2_radius, color='yellow', linestyle='-', linewidth=1.5, alpha=0.2)
    ax.add_patch(kpa_platoon2_circle)
    ax.add_patch(kpa_section2_circle)
    ax.add_patch(kpa_platoon2_circle_line)
    ax.add_patch(kpa_section2_circle_line)

    # --- 방향 화살표 추가 (축소된 크기) ---
    ARROW_WIDTH = 0.005
    HEAD_WIDTH = 3
    HEAD_LENGTH = 4
    
    # if np.linalg.norm(kpa_platoon1_direction_vector) > 0:
    #     ax.quiver(
    #         kpa_platoon1_pos[0], kpa_platoon1_pos[1], 
    #         kpa_platoon1_direction_vector[0], kpa_platoon1_direction_vector[1], 
    #         color='cyan', scale=1, scale_units='xy', angles='xy', 
    #         width=ARROW_WIDTH, headwidth=HEAD_WIDTH, headlength=HEAD_LENGTH, zorder=6, label='kpa_platoon1 다음방향'
    #     )
    # if np.linalg.norm(kpa_platoon2_direction_vector) > 0:
    #     ax.quiver(
    #         kpa_platoon2_pos[0], kpa_platoon2_pos[1], 
    #         kpa_platoon2_direction_vector[0], kpa_platoon2_direction_vector[1], 
    #         color='cyan', scale=1, scale_units='xy', angles='xy', 
    #         width=ARROW_WIDTH, headwidth=HEAD_WIDTH, headlength=HEAD_LENGTH, zorder=6, label='kpa_platoon1 다음방향'
    #     )
    # if np.linalg.norm(kpa_leader_direction_vector) > 0:
    #     ax.quiver(
    #         kpa_leader_pos[0], kpa_leader_pos[1], 
    #         kpa_leader_direction_vector[0], kpa_leader_direction_vector[1], 
    #         color='cyan', scale=1, scale_units='xy', angles='xy', 
    #         width=ARROW_WIDTH, headwidth=HEAD_WIDTH, headlength=HEAD_LENGTH, zorder=6, label='kpa_leader 다음방향'
    #     )
    # if np.linalg.norm(kpa_artillery_direction_vector) > 0:
    #     ax.quiver(
    #         kpa_artillery_pos[0], kpa_artillery_pos[1], 
    #         kpa_artillery_direction_vector[0], kpa_artillery_direction_vector[1], 
    #         color='cyan', scale=1, scale_units='xy', angles='xy', 
    #         width=ARROW_WIDTH, headwidth=HEAD_WIDTH, headlength=HEAD_LENGTH, zorder=6, label='kpa_leader 다음방향'
    #     )
    # if np.linalg.norm(kpa_squad_direction_vector) > 0:
    #     ax.quiver(
    #         kpa_squad_pos[0], kpa_squad_pos[1], 
    #         kpa_squad_direction_vector[0], kpa_squad_direction_vector[1], 
    #         color='cyan', scale=1, scale_units='xy', angles='xy', 
    #         width=ARROW_WIDTH, headwidth=HEAD_WIDTH, headlength=HEAD_LENGTH, zorder=6, label='kpa_leader 다음방향'
    #     )
    # if np.linalg.norm(kpa_section_direction_vector) > 0:
    #     ax.quiver(
    #         kpa_section_pos[0], kpa_section_pos[1], 
    #         kpa_section_direction_vector[0], kpa_section_direction_vector[1], 
    #         color='cyan', scale=1, scale_units='xy', angles='xy', 
    #         width=ARROW_WIDTH, headwidth=HEAD_WIDTH, headlength=HEAD_LENGTH, zorder=6, label='kpa_leader 다음방향'
    #     )
    # if np.linalg.norm(kpa_section2_direction_vector) > 0:
    #     ax.quiver(
    #         kpa_section2_pos[0], kpa_section2_pos[1], 
    #         kpa_section2_direction_vector[0], kpa_section2_direction_vector[1], 
    #         color='cyan', scale=1, scale_units='xy', angles='xy', 
    #         width=ARROW_WIDTH, headwidth=HEAD_WIDTH, headlength=HEAD_LENGTH, zorder=6, label='kpa_leader 다음방향'
    #     )
    # if np.linalg.norm(rok_squad_direction_vector) > 0:
    #     ax.quiver(
    #         rok_squad_pos[0], rok_squad_pos[1], 
    #         rok_squad_direction_vector[0], rok_squad_direction_vector[1], 
    #         color='cyan', scale=1, scale_units='xy', angles='xy', 
    #         width=ARROW_WIDTH, headwidth=HEAD_WIDTH, headlength=HEAD_LENGTH, zorder=6, label='kpa_leader 다음방향'
    #     )
    # if np.linalg.norm(rok_squad2_direction_vector) > 0:
    #     ax.quiver(
    #         rok_squad2_pos[0], rok_squad2_pos[1], 
    #         rok_squad2_direction_vector[0], rok_squad2_direction_vector[1], 
    #         color='cyan', scale=1, scale_units='xy', angles='xy', 
    #         width=ARROW_WIDTH, headwidth=HEAD_WIDTH, headlength=HEAD_LENGTH, zorder=6, label='kpa_leader 다음방향'
    #     )
    # if np.linalg.norm(rok_leader_direction_vector) > 0:
    #     ax.quiver(
    #         rok_leader_pos[0], rok_leader_pos[1], 
    #         rok_leader_direction_vector[0], rok_leader_direction_vector[1], 
    #         color='cyan', scale=1, scale_units='xy', angles='xy', 
    #         width=ARROW_WIDTH, headwidth=HEAD_WIDTH, headlength=HEAD_LENGTH, zorder=6, label='kpa_leader 다음방향'
    #     )

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
    ax.plot(kpa_platoon1_history[:, 0], kpa_platoon1_history[:, 1], 'r-', alpha=0.7, zorder=2)
    ax.plot(kpa_platoon2_history[:, 0], kpa_platoon2_history[:, 1], 'r-', alpha=0.7, zorder=2)
    ax.plot(kpa_leader_history[:, 0], kpa_leader_history[:, 1], 'r-', alpha=0.7, zorder=2)
    ax.plot(kpa_artillery_history[:, 0], kpa_artillery_history[:, 1], 'r-', alpha=0.7, zorder=2)
    ax.plot(kpa_squad_history[:, 0], kpa_squad_history[:, 1], 'r-', alpha=0.7, zorder=2)
    ax.plot(kpa_section_history[:, 0], kpa_section_history[:, 1], 'r-', alpha=0.7, zorder=2)
    ax.plot(kpa_section2_history[:, 0], kpa_section2_history[:, 1], 'r-', alpha=0.7, zorder=2)
    ax.plot(rok_squad_history[:, 0], rok_squad_history[:, 1], 'b-', alpha=0.7, zorder=2)
    ax.plot(rok_squad2_history[:, 0], rok_squad2_history[:, 1], 'b-', alpha=0.7, zorder=2)
    ax.plot(rok_leader_history[:, 0], rok_leader_history[:, 1], 'b-', alpha=0.7, zorder=2)
    
    rok_sq_src = "res/rok_sq_undetected.png"
    rok_sq2_src = "res/rok_sq_undetected.png"
    rok_le_src = "res/rok_lead_undetected.png"

    if current_time_offset > 2:
        rok_sq_src = "res/rok_sq_detected.png"
        rok_le_src = "res/rok_lead_detected.png"

    if current_time_offset > 3:
        rok_sq2_src = "res/rok_sq_detected.png"

    if current_time_offset > 6:
        rok_sq_src = "res/rok_sq_detected_destroy.png"
        rok_sq2_src = "res/rok_sq_detected_destroy.png"
    
    # 현재 위치 시각화 (png파일 표시)
    add_image_marker(
        ax,
        kpa_platoon1_pos,
        image_path="res/kpa_platoon.png",
        zoom_scale=0.10,        
    )
    add_image_marker(
        ax,
        kpa_platoon2_pos,
        image_path="res/kpa_platoon.png",
        zoom_scale=0.10,        
    )
    add_image_marker(
        ax,
        kpa_leader_pos,
        image_path="res/kpa_leader.png",
        zoom_scale=0.10,        
    )
    add_image_marker(
        ax,
        kpa_artillery_pos,
        image_path="res/kpa_artillery.png",
        zoom_scale=0.10,        
    )
    add_image_marker(
        ax,
        kpa_squad_pos,
        image_path="res/kpa_squad.png",
        zoom_scale=0.10,        
    )
    add_image_marker(
        ax,
        kpa_section_pos,
        image_path="res/kpa_section.png",
        zoom_scale=0.10,        
    )
    add_image_marker(
        ax,
        kpa_section2_pos,
        image_path="res/kpa_section.png",
        zoom_scale=0.10,        
    )
    add_image_marker(
        ax,
        rok_squad_pos,
        image_path=rok_sq_src,
        zoom_scale=0.10,
    )
    add_image_marker(
        ax,
        rok_squad2_pos,
        image_path=rok_sq2_src,
        zoom_scale=0.10,
    )
    add_image_marker(
        ax,
        rok_leader_pos,
        image_path=rok_le_src,
        zoom_scale=0.10,
    )
    if current_time_offset > 5 and current_time_offset < 8:
        ax.quiver(175, 105, 65, 10, angles='xy', scale_units='xy', scale=1, color='red', linestyle='-', width=0.003, headwidth=5, headlength=5)
        ax.quiver(175, 90, 70, -5, angles='xy', scale_units='xy', scale=1, color='red', linestyle='-', width=0.003, headwidth=5, headlength=5)
        ax.quiver(245, 120, -10, 50, angles='xy', scale_units='xy', scale=1, color='black', linestyle='-', width=0.003, headwidth=5, headlength=5)
        ax.quiver(260, 120, 3, 70, angles='xy', scale_units='xy', scale=1, color='black', linestyle='-', width=0.003, headwidth=5, headlength=5)
        ax.quiver(240, 175, 10, -54, angles='xy', scale_units='xy', scale=1, color='red', linestyle='-', width=0.003, headwidth=5, headlength=5)
        ax.quiver(250, 185, 30, -60, angles='xy', scale_units='xy', scale=1, color='red', linestyle='-', width=0.003, headwidth=5, headlength=5)
        ax.quiver(270, 195, 10, -50, angles='xy', scale_units='xy', scale=1, color='red', linestyle='-', width=0.003, headwidth=5, headlength=5)
        ax.quiver(280, 200, 50, -40, angles='xy', scale_units='xy', scale=1, color='red', linestyle='-', width=0.003, headwidth=5, headlength=5)
        
    if current_time_offset > 6:
        add_image_marker(
            ax,
            [305.0, 160.0],
            image_path="res/destroy_bomb.png",
            zoom_scale=0.10,            
        )
        add_image_marker(
            ax,
            [260.0, 110.0],
            image_path="res/destroy_bomb.png",
            zoom_scale=0.10,            
        )

    if current_time_offset > 8:
        
        indirect_fire = Circle(([320.0, 130.0]), radius=50, edgecolor='red', facecolor='none', linestyle='--', linewidth=1.5, alpha=1)
        arrow = Arrow(145, 230, 130, -75, width=50, linestyle='dashed', edgecolor='red', facecolor='none', linewidth=2.0, zorder=8, alpha=1)
        ax.add_patch(arrow)
        ax.add_patch(indirect_fire)
        # ax.quiver(145, 230, 100, 50,
        #           ec='red',
        #           fc='none',
        #           linestyle='dashed',
        #           width=0.01, scale=1,
        #           scale_units='xy',
        #           angles='xy',
        #           headwidth=5,
        #           headlength=8,
        #           zorder=8
        #           )
        # ax.quiver(145, 230, 130, -75, angles='xy', scale_units='xy', scale=1, edgecolor='red', facecolor='none', linestyle='--', width=0.02, label='Arrow')

    if current_time_offset > 9:
        add_image_marker(
            ax,
            [360.0, 110.0],
            image_path="res/neutralize_bomb.png",
            zoom_scale=0.10,            
        )
        add_image_marker(
            ax,
            [290.0, 130.0],
            image_path="res/bomb.png",
            zoom_scale=0.10,            
        )
        add_image_marker(
            ax,
            [310.0, 90.0],
            image_path="res/bomb.png",
            zoom_scale=0.10,            
        )

    # 하드코딩된 틱 포인트를 작은 점으로 표시
    # ax.scatter(ALLY_PATH[:, 0], ALLY_PATH[:, 1], marker='.', color='blue', s=50, alpha=0.5, zorder=3)
    # ax.scatter(ENEMY_PATH[:, 0], ENEMY_PATH[:, 1], marker='.', color='red', s=50, alpha=0.5, zorder=3)
    
    # 축 및 제목 설정
    ax.set_xlim(0, map_x_value)
    ax.set_ylim(0, map_y_value)
    ax.set_xticks(np.arange(0, map_x_value, 20))
    ax.set_yticks(np.arange(0, map_y_value, 20))
    # ax.set_xlabel("X 좌표")
    # ax.set_ylabel("Y 좌표")
    # ax.set_title(f"적/아군 위치: 배경 맵 적용 ({current_time_offset:.1f}초 경과)")
    ax.grid(True, linestyle=':', alpha=0.7)
    ax.set_aspect('equal', adjustable='box')
    
    # 범례 설정
    handles, labels = ax.get_legend_handles_labels()
    custom_handles = [
        plt.Line2D([], [], color='yellow', linestyle='-', alpha=0.7, label='탐지범위'),
        plt.Line2D([], [], color='red', linestyle='-', alpha=0.7, label='홍군 이동 경로'),
        plt.Line2D([], [], color='blue', linestyle='-', alpha=0.7, label='청군 이동 경로'),
        plt.Line2D([], [], color='red', linestyle='-', alpha=0.7, label='홍군 직접 사격선'),
        plt.Line2D([], [], color='black', linestyle='-', alpha=0.7, label='청군 직접 사격선'),
        plt.Line2D([], [], color='red', linestyle='--', alpha=0.7, label='홍군 간접 사격선'),
        # plt.Line2D([], [], color='green', linestyle='--', alpha=0.7, label='적군 영향권'),
    ]
    by_label = dict(zip(labels, handles))
    by_label.update(dict(zip([h.get_label() for h in custom_handles], custom_handles)))
    
    ax.legend(by_label.values(), by_label.keys(), loc='lower center', fontsize=7, ncol = 3)
    
    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)
    
    # st.info(f"현재 시간: **{current_time_offset:.1f}초** | 아군 위치: **({rok_ew_pos[0]:.1f}, {rok_ew_pos[1]:.1f})** | 적군 위치: **({kpa_platoon1[0]:.1f}, {kpa_platoon1[1]:.1f})**")

def hard_code_image(current_time_offset):
    st.cache_data.clear()
    st.cache_resource.clear()

    images = [
        "image/scene1/0.png",
        "image/scene1/1.png",
        "image/scene1/2.png",
        "image/scene1/3.png",
        "image/scene1/4.png",
        "image/scene1/5.png",
        "image/scene1/6.png",
        "image/scene1/7.png",
        "image/scene1/8.png",
        "image/scene1/9.png",
        "image/scene1/10.png",
        "image/scene1/11.png",
        "image/scene1/12.png",
        "image/scene1/13.png",
        "image/scene1/14.png",
        "image/scene1/15.png",
    ]
    # 세션 상태 초기화
    if "index" not in st.session_state:
        st.session_state.index = 0

    # 현재 프레임 표시
    st.image(images[st.session_state.index], width='stretch')

    # 슬라이더 값이 바뀌면 인덱스 업데이트
    if (current_time_offset - 9) != st.session_state.index:
        st.session_state.index = current_time_offset - 9
        try:
            with open("time_offset.txt", "a", encoding="utf-8") as f:
                f.write(str(current_time_offset) + "\n")
        except IOError as e:
            print(f"파일 쓰기 오류: {e}")
        st.rerun()  # 화면 즉시 갱신


# --- 3. Streamlit UI 및 시뮬레이션 로직 ---

# st.title("🛡️ SHORAD 작전 시뮬레이터 (시나리오 3)")
# st.caption(f"기준 시간: {BASE_TIME.strftime('%Y-%m-%d %H:%M:%S')} | 시나리오: 복합 통합 공격 대응")

# 슬라이더 설정
max_time = 24
slider_time = st.slider(
    "시간 진행 (시)",
    min_value=9,
    max_value=max_time,
    value=9,
    step=1,
    format="%d시"
)

# 현재 시각 계산
# current_time = BASE_TIME + datetime.timedelta(seconds=slider_time)
# st.markdown(f"## ⏱️ 현재 시각: **{current_time.strftime('%H:%M:%S')}**")

# --- A. 시각화 플롯 표시 ---
# plot_defense_status(slider_time)
# plot_hardcoded_movement_at_time(slider_time)
hard_code_image(slider_time)

st.divider()

# --- B. 실시간 로그 표시 ---
# st.subheader("작전 상황 로그")

# current_events = df_events[df_events['time_offset'] <= slider_time]

# if current_events.empty:
#     st.info("아직 이벤트가 발생하지 않았습니다. 시간을 진행해 주세요.")
# else:
#     # 가장 최근 이벤트를 중심으로 보여주기 위해 역순 정렬
#     current_events_sorted = current_events.sort_values(by='time_offset', ascending=False)
    
#     # 로그를 테이블로 표시
#     st.dataframe(
#         current_events_sorted[['time_stamp', 'category', 'event', 'details']],
#         hide_index=True,
#         column_config={
#             "time_stamp": st.column_config.DatetimeColumn("시간", format="HH:mm:ss", width="small"),
#             "category": "분류",
#             "event": "주요 이벤트",
#             "details": "상세 설명 및 교리 적용"
#         }
#     )

# st.divider()