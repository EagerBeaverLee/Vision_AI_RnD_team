import os
import sqlite3
import pandas as pd


def read_csv_safely(csv_path):
  """EUC-KR, CP949, UTF-8 인코딩을 순차적으로 시도하여 CSV를 읽어오는 함수"""
  encodings = ['cp949', 'euc-kr', 'utf-8-sig', 'utf-8']
  for enc in encodings:
    try:
      return pd.read_csv(csv_path, encoding=enc)
    except (UnicodeDecodeError, UnicodeError):
      continue
  raise ValueError(f"파일 {csv_path}의 인코딩을 판별할 수 없습니다.")


def create_buoy_database(
    db_name="buoy_weather.db",
    meta_csv="buoy_metadata.csv",
    obs_csv="buoy_observations.csv",
):
  # 1. 엔진 폴더 경로 확보
  engine_dir = os.path.dirname(os.path.abspath(__file__))

  # 2. 상위 폴더로 올라간 뒤 data/weather_data 경로 조합
  base_dir = os.path.dirname(engine_dir)
  target_dir = os.path.join(base_dir, "data", "weather_data")

  db_path = os.path.join(target_dir, db_name)
  meta_csv_path = os.path.join(target_dir, meta_csv)
  obs_csv_path = os.path.join(target_dir, obs_csv) 


  # base_dir = os.path.dirname(os.path.abspath(__file__))
  # db_path = os.path.join(base_dir, db_name)
  # meta_csv_path = os.path.join(base_dir, meta_csv)
  # obs_csv_path = os.path.join(base_dir, obs_csv)

  # 기존 DB 파일 삭제 후 재생성
  if os.path.exists(db_path):
    os.remove(db_path)
    print(f"🗑️ 기존 데이터베이스 파일('{db_name}')을 삭제했습니다.")

  conn = sqlite3.connect(db_path)
  cursor = conn.cursor()

  cursor.execute("""
      CREATE TABLE IF NOT EXISTS buoy_master (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          spot_id INTEGER NOT NULL,
          observed_at TEXT NOT NULL,
          wind_speed REAL,
          wind_direction REAL,
          gust_wind_speed REAL,
          pressure REAL,
          humidity REAL,
          air_temp REAL,
          water_temp REAL,
          max_wave_height REAL,
          significant_wave_height REAL,
          mean_wave_height REAL,
          wave_period REAL,
          wave_direction REAL,
          start_date TEXT,
          end_date TEXT,
          spot_name TEXT NOT NULL,
          address TEXT,
          office TEXT,
          latitude REAL,
          longitude REAL
      );
      """)

  # 3. 검색 performance 향상을 위한 인덱스 생성
  cursor.execute(
      'CREATE INDEX IF NOT EXISTS idx_master_spot_time ON'
      ' buoy_master(spot_id, observed_at);'
  )
  cursor.execute(
      'CREATE INDEX IF NOT EXISTS idx_master_name ON'
      ' buoy_master(spot_name);'
  )
  cursor.execute(
      'CREATE INDEX IF NOT EXISTS idx_master_office ON buoy_master(office);'
  )

  # 4. CSV 파일 데이터 적재
  if os.path.exists(meta_csv_path):
    meta_df = read_csv_safely(meta_csv_path)
    meta_col_map = {
        "지점": "spot_id",
        "시작일": "start_date",
        "종료일": "end_date",
        "지점명": "spot_name",
        "지점주소": "address",
        "관리관서": "office",
        "위도": "latitude",
        "경도": "longitude",
    }
    meta_df.rename(columns=meta_col_map, inplace=True)
    meta_df.drop_duplicates(
        subset=["spot_id"], keep="last", inplace=True)

  if os.path.exists(obs_csv_path):
    obs_df = read_csv_safely(obs_csv_path)
    obs_col_map = {
        "지점": "spot_id",
        "일시": "observed_at",
        "풍속(m/s)": "wind_speed",
        "풍향(deg)": "wind_direction",
        "GUST풍속(m/s)": "gust_wind_speed",
        "현지기압(hPa)": "pressure",
        "습도(%)": "humidity",
        "기온(°C)": "air_temp",
        "수온(°C)": "water_temp",
        "최대파고(m)": "max_wave_height",
        "유의파고(m)": "significant_wave_height",
        "평균파고(m)": "mean_wave_height",
        "파주기(sec)": "wave_period",
        "파향(deg)": "wave_direction",
    }
    obs_df.columns = obs_df.columns.str.strip()
    obs_df.rename(columns=obs_col_map, inplace=True)

    obs_df['observed_at'] = obs_df['observed_at'].astype(str).str.replace('2025', '2022')

    master_df = pd.merge(obs_df, meta_df, on='spot_id', how='left')

    master_df.to_sql("buoy_master", conn, if_exists="append", index=False)

  conn.commit()

  total_rows = cursor.execute(
    'SELECT COUNT(*) FROM buoy_master;'
  ).fetchone()[0]
  conn.close()

  print(f"🎉 Database 총'{total_rows}건' DB적재 최종 완료!")


if __name__ == "__main__":
  create_buoy_database()