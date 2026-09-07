import sqlite3
import pandas as pd

conn = sqlite3.connect('d:/LEE/AI_team/github/Vision_AI_RnD_team/projects/test_project/ais_weather/korea_weather.db', check_same_thread=False)
weather_cursor = conn.cursor()

query = """
    SELECT 
        b.지점명,
        b.latitude, 
        b.longitude, 
        w.*
    FROM 
        weather_buoy AS w
    JOIN 
        buoy_position AS b ON w.지점 = b.지점
"""
# 3. 쿼리 실행
# search_param = f"{current_hour_str}:%"
weather_cursor.execute(query)
rows = weather_cursor.fetchall()

col_names = [desc[0] for desc in weather_cursor.description]
df = pd.DataFrame(rows, columns=col_names)

target_cols = [0, 1, 2] + list(range(4, len(df.columns)))
final_df = df.iloc[:, target_cols]

new_columns = ["지점명",
"latitude",
"longitude",
"일시",
"풍속",
"풍향",
"GUST풍속",
"현지기압",
"습도",
"기온",
"수온",
"최대파고",
"유의파고",
"평균파고",
"파주기",
"파향"
]

final_df.columns = new_columns

new_conn = sqlite3.connect('d:/LEE/AI_team/github/Vision_AI_RnD_team/projects/test_project/ais_weather/weather_db.db')

final_df.to_sql(
    name='weather_data',  # 새 DB 안에 생성될 테이블 이름
    con=new_conn,                  # DB 연결 객체
    if_exists='replace',           # 이미 파일/테이블이 존재하면 덮어쓰기 ('append'로 변경 시 누적)
    index=False                    # Pandas 인덱스(0, 1, 2...)는 컬럼으로 저장하지 않음
)

new_conn.close()