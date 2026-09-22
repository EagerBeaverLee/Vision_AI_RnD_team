import os
import json
import sqlite3
from crewai.tools import tool

# 1. crew 폴더 경로 확보
db_name="buoy_weather.db"
tools_dir = os.path.dirname(os.path.abspath(__file__))

# 2. 상위 폴더로 올라간 뒤 data/weather_data 경로 조합
base_dir = os.path.dirname(tools_dir)
target_dir = os.path.join(base_dir, "data", "weather_data")
DB_PATH = os.path.join(target_dir, db_name)

@tool("Execute SQLite Query")
def execute_sql_query(sql_query: str) -> str:
    """SQLite 쿼리를 실행하고 조회된 필드만 정제하여 결과를 반환합니다."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(sql_query)
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        conn.close()
        if not rows:
            return "조회 결과가 없습니다."

        dict_rows = [dict(zip(columns, row)) for row in rows]

        return json.dumps(dict_rows, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"SQL Error: {str(e)}"