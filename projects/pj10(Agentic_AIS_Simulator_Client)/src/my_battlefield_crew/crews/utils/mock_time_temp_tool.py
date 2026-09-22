from datetime import datetime, timedelta
import random

def get_mock_current_time() -> str:
    """2022-12-01 00:00 ~ 2022-12-31 23:00 사이의 시간 단위 랜덤 일시 생성"""
    start_date = datetime(2022, 12, 1, 0, 0)
    random_hours = random.randint(0, 31 *24 -1)
    mock_time = start_date + timedelta(hours=random_hours)
    return mock_time.strftime('%Y-%m-%d %H:00')