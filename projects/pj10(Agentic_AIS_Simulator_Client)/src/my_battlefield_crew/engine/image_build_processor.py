from my_battlefield_crew.crews.battlefield_models import MaritimeSituationReport
from my_battlefield_crew.chainlit_app.schemas import SimulationContext


def build_final_markdown(report: MaritimeSituationReport, context: SimulationContext) -> str:
    """Pydantic 리포트와 context.artifacts의 HTML 블록을 결합해 단일 Markdown 문서 생성"""
    sections = []
    step_num = 1

    # (artifact_key, 섹션 제목, 데이터 존재 여부, LLM 분석 텍스트)
    section_specs = [
        ("top_dense_zones", "[구역별 밀집 현황]", report.top_dense_zones, report.top_dense_zones_analysis),
        ("main_routes", "[주요 항로 흐름 분석]", report.main_routes, report.main_routes_analysis),
        ("main_directions", "[주요 이동 방향 분석]", report.main_directions, report.main_directions_analysis),
        ("zone_speeds", "[해역별 선박 속도 분석]", report.zone_speeds, report.zone_speeds_analysis),
        ("port_activities", "[주요 항만 입출항 및 정박 현황]", report.port_activities, report.port_activities_analysis),
        ("ship_voyage_status", "[선박 유형별 항해 및 기동 상태]", report.ship_voyage_status, report.ship_voyage_status_analysis),
        ("unusual_ships", "[주요 선박 특이 기동 상세 분석]", report.unusual_ships, report.unusual_ships_analysis),
    ]

    for key, title, data_obj, analysis_text in section_specs:
        # 해당 도구가 호출되지 않았으면 섹션 자체를 생략
        if not data_obj and not analysis_text:
            continue

        block_parts = [f"### {step_num}. {title}"]
        
        if analysis_text:
            block_parts.append(analysis_text.strip())

        # 해당 도구가 저장해 둔 HTML 블록(지도/이미지/테이블 위젯)이 있으면 바로 아래에 부착
        media_html = context.artifacts.get(key)
        if media_html:
            block_parts.append(media_html)

        sections.append("\n\n".join(block_parts))
        step_num += 1

    # 마지막에 교차 분석된 최종 종합 결론 추가
    if report.final_answer:
        sections.append(f"### {step_num}. [종합 결론]\n\n{report.final_answer.strip()}")

    return "\n\n---\n\n".join(sections)