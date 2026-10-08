from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Union, Any


#------------------------------------------------------
# battlefield_crew.py 에 해당되는 pydantic 데이터 모델
#------------------------------------------------------

class DenseZoneInfo(BaseModel):
    name: str = Field(description="정박 밀집도가 높은 해역의 명칭 (예: 부산-가덕 해역, 여수-통영 외해 등)")
    total_stay_index: float = Field(description="해당 구역의 선박 총 체류 지수 점수")
    military_implication: Optional[str] = Field(
        default="분석 내용 없음",
        description="이 해역이 밀집하게 된 원인 및 전술적 함의에 대한 분석")

class RouteFlowInfo(BaseModel):
    origin_zone: str = Field(description="출발 작전 해역 명칭")
    dest_zone: str = Field(description="도착 작전 해역 명칭")
    weight: float = Field(description="해당 해상 교통선 항로의 트래픽 이동 가중치(weight)")

class ZoneSpeedInfo(BaseModel):
    name: str = Field(description="구역별 해역 명칭")
    mean: float = Field(description="해당 구역 선박들의 평균 속도 (Knot)")
    max: float = Field(description="해당 구역 선박들의 최고 속도 (Knot)")
    count: int = Field(description="해당 구역 내 분석된 선박 데이터 수")
    # military_implication: str = Field(description="이 해역의 평균속도의 전술적 함의에 대한 분석")

class TrafficDirectionInfo(BaseModel):
    direction: str = Field(description="해당 구역 내 분석된 선박의 이동 방향")
    ship_count: int = Field(description="해당 구역 내 분석된 선박 데이터 수")
    average_speed_knot: float = Field(description="해당 구역 선박들의 평균 속도 (Knot)")
    vector_course_deg: float = Field(description="해당 구역 선박들의 이동 방향 (degree)")

class PortActivityInfo(BaseModel):
    port_name: str = Field(description="분석 대상 항만/항구 명칭 (예:  BUSAN HANG)")
    anchored_count: int = Field(description="현재 해당 항구반경 내 정박 대기 중인 선박의 총수")
    departure_count: int = Field(description="기준 시간 동안 출항한 선박 수")
    arrival_count: int = Field(description="기준 시간 동안 도착 및 입항한 선박 수")

    #입출항 관련 세부 리스트 저장
    anchored_ships_detail: List[str] = Field(default=[], description="정박 중인 선박 세부 정보 (예: 'MHC-565 김포(352403000): 2022-12-01 00:04:18부터 정박 중')")
    departures_detail: List[str] = Field(default=[], description="출발 선박 세부 정보 (예: 'ATS- 평택(215080000): 2022-12-01 12:12:05 에 출발')")
    arrivals_detail: List[str] = Field(default=[], description="도착 선박 세부 정보 (예: 'SS-061 장보고(371002000): 2022-12-02 12:00:56 에 도착')")

class ShipDetail(BaseModel):
    ShipName: str =Field(description="선박 명칭(예: 'AGS-신천지')")
    mmsi: int = Field(description="선박 식별 번호 (MMSI)")
    status: str = Field(description="선박의 현재 기동 상태(예: 우선회(49.0°) 이동/통과)")

class ShipVoyageStatusInfo(BaseModel):
    ship_types: Dict[str, int] = Field(default={}, description="전체 해역 내 식별된 선종별 선박 척수 통계 데이터") 
    moving_ships: List[ShipDetail] = Field(default=[], description ="현재 정상 기동 중인(움직이는) 선박 목록")
    stop_ships: List[ShipDetail] = Field(default=[], description ="현재 완전 정지 및 정박 상태인 선박 목록")
    slow_ships: List[ShipDetail] = Field(default=[], description ="낮은 속도로 서행 및 대기 이동 중인 선박 목록")

class UnusualShipsStatusInfo(BaseModel):
    ShipName: str = Field(description="선박 명칭(예: 'AGS-신천지')")
    turn_count: int = Field(description="식별된 선박의 총 선회 횟수")
    speed_change_count: int = Field(description="식별된 선박의 총 속도변화 횟수")
    # status_list: List[str] = Field(default=[], description="이상 기동 선박 세부 기동 정보 (예: 우선회(26.5°), 우선회(40.9°), 감속 이동/통과)")


#최종 결과 취합
class MaritimeSituationReport(BaseModel):
    final_answer: str = Field(description="사용자가 던진 구체적인 질문에 대해, 위 정량 데이터를 바탕으로 도출한 최종 답변 및 정밀 종합 의견")
    top_dense_zones: Optional[List[DenseZoneInfo]] = Field(default=None, description="체류 지수(total_stay_index) 기준 가장 밀집된 상위 해역 목록 및 분석")
    main_routes: Optional[List[RouteFlowInfo]] = Field(default=None, description="현재 이동량이 집중되고 있는 주요 항로 흐름 목록")
    main_directions: Optional[List[TrafficDirectionInfo]] = Field(default=None, description="현재 이동중인 선박들의 주요 이동 방향 목록")
    zone_speeds: Optional[List[ZoneSpeedInfo]] = Field(default=None, description="속도 분석 도구 결과 데이터 목록")
    port_activities: Optional[List[PortActivityInfo]] = Field(default=None, description="주요 항만별 선박 입출항 및 정박 상세 분석 데이터 목록")
    ship_voyage_status: Optional[Union[ShipVoyageStatusInfo,List[ShipVoyageStatusInfo]]] = Field(default=None, description="현재 분석에 포함된 선박들의 선박 유형별 요약 및 기동 상태별 데이터 목록")
    unusual_ships: Optional[List[UnusualShipsStatusInfo]] = Field(default=None, description="현재 식별된 특이 기동 선박 데이터 목록")
    # commander_recommendations: List[str] = Field(#default= [],
    #                                              description="밀집 급증이나 특이 동선 구역에 대한 작전 지휘관 권고사항 및 정찰 제언 목록")


# 전체상황 요약 템플릿   

def format_maritime_report(report: MaritimeSituationReport) -> str:
    """Pydantic 모델(report)에서 데이터를 꺼내 제시된 템플릿 포맷 문자열로 변환합니다."""
    if not report:
        return "분석 결과 데이터가 존재하지 않습니다."

    # 2. 구역별 밀집 현황 (테이블 형태)
    clusters_table = "| 해역명 | 총 정박 지수 | 비고 |\n|---|---|---|\n"
    if report.top_dense_zones:
        for z in report.top_dense_zones[:3]: # 상위 3개
            mil = getattr(z, 'military_implication', '주요 해역')
            clusters_table += f"| {z.name} | {z.total_stay_index} | {mil} |\n"
    else:
        clusters_table = "집계된 밀집 구역 데이터 없음"

    # 3. 구역별 이동 속도 현황
    speed_text = ""
    if report.zone_speeds:
        speed_text = "\n".join([f"- {s.name}: 평균 {s.mean:.2f} Knot (최대 {s.max:.2f} Knot)" for s in report.zone_speeds])
    else:
        speed_text = "속도 분석 데이터 없음"

    # 4. 주요 교통 흐름
    direction_text = ""
    if report.main_directions:
        direction_text = "\n".join([f"- {d.direction} 방향: {d.ship_count}척 (평균 속도 {d.average_speed_knot} Knot)" for d in report.main_directions])
    else:
        direction_text = "교통 흐름 데이터 없음"

    # 5. 구역 간 주요 항로(OD Flow)
    routes_text = ""
    if report.main_routes:
        routes_text = "\n".join([f"- {r.origin_zone} -> {r.dest_zone} (가중치: {r.weight})" for r in report.main_routes[:5]])
    else:
        routes_text = "주요 항로 데이터 없음"

    # 6. 선박 유형별 통계 (Markdown 테이블)
    shiptype_table = "| 선박 유형 | 수량 |\n|---|---|\n"
    if report.ship_voyage_status and getattr(report.ship_voyage_status, 'ship_types', None):
        for stype, count in report.ship_voyage_status.ship_types.items():
            shiptype_table += f"| {stype} | {count} |\n"
    else:
        shiptype_table = "선박 유형 통계 데이터 없음"

    # 7. 주요 항만별 입출항 현황
    ports_text = ""
    if report.port_activities:
        for p in report.port_activities:
            ports_text += f"▶ {p.port_name}\n"
            if getattr(p, 'anchored_ships_detail', None):
                ports_text += f"  ▶ 정박/대기 중인 선박: 총 {p.anchored_count}척\n" + "\n".join([f"    - {s}" for s in p.anchored_ships_detail]) + "\n"
            if getattr(p, 'departures_detail', None):
                ports_text += f"  ▶ 출발/기동 선박: 총 {p.departure_count}척\n" + "\n".join([f"    - {s}" for s in p.departures_detail]) + "\n"
            if getattr(p, 'arrivals_detail', None):
                ports_text += f"  ▶ 도착/진입 선박: 총 {p.arrival_count}척\n" + "\n".join([f"    - {s}" for s in p.arrivals_detail]) + "\n"
    else:
        ports_text = "항만 활동 데이터 없음"

    # 8. 선박 상태별 현황 요약 (리스트 형식)
    moving_str = "없음"
    stopping_str = "없음"
    slow_str = "없음"
    if report.ship_voyage_status:
        v = report.ship_voyage_status
        if getattr(v, 'moving_ships', None):
            moving_str = "\n" + "\n".join([f"    - {s.ShipName}({s.mmsi})" for s in v.moving_ships])
        if getattr(v, 'stop_ships', None):
            stopping_str = "\n" + "\n".join([f"    - {s.ShipName}({s.mmsi})" for s in v.stop_ships])
        if getattr(v, 'slow_ships', None):
            slow_str = "\n" + "\n".join([f"    - {s.ShipName}({s.mmsi})" for s in v.slow_ships])

    # 9. 특이 기동 선박
    unusual_text = ""
    if report.unusual_ships:
        for u in report.unusual_ships:
            unusual_text += f"  - [{u.ShipName}]: {u.turn_count}회의 변침과 {u.speed_change_count}회의 속도 변화 포착.\n"
    else:
        unusual_text = "식별된 특이 기동 선박 없음"

    # 최종 템플릿 완성
    return f"""1. [분석 대상 시간]:
        - 수집된 AIS 데이터 기반 집계 결과입니다.

        2. [구역별 밀집 현황]:
        {clusters_table}

        3. [구역별 선박 이동 속도 현황]:
        {speed_text}

        4. [주요 교통 흐름 요약]:
        {direction_text}

        5. [구역 간 주요 항로(OD Flow) 현황]:
        {routes_text}

        6. [선박 유형별 통계]:
        {shiptype_table}

        7. [주요 항만별 선박 입출항 현황]:
        {ports_text}
        8. [선박 상태별 현황 요약]:
            ▶ 순항 중인 선박 리스트: {moving_str}
            ▶ 정박/대기 중인 선박 리스트: {stopping_str}
            ▶ 저속 운항 중인 선박 리스트: {slow_str}

        9. [주요 선박 특이 기동 상세 분석]:
        {unusual_text}
        10. [종합 결론]:
        {report.final_answer}
    """



