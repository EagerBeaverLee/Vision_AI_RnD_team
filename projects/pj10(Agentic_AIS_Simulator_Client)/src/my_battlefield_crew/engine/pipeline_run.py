# engine/pipeline_run.py
from engine.loader import load_and_filter_ais
from engine.analyzer import run_cluster_analysis
from engine.build_weather_db import create_buoy_database

def build_data_cache():
    """데이터 전처리 및 분석 파이프라인의 전체 공정을 오케스트레이션합니다."""
    print("=== 🌊 전장 데이터 인텔리전스 파이프라인 가동 ===")
    load_and_filter_ais()
    run_cluster_analysis()
    create_buoy_database()
    print("=== 🎉 전처리 및 분석 데이터 캐시 구축 성공 ===")

if __name__ == "__main__":
    build_data_cache()


