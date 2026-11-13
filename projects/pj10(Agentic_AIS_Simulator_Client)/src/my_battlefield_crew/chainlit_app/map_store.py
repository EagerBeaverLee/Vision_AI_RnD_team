import uuid
from typing import Optional

# 프로세스 내 모든 모듈이 공유하는 인메모리 저장소
INMEMORY_MAP_STORE: dict[str, str] = {}
MAX_STORED_MAPS = 50  # 메모리 누수 방지용 상한


def save_map_html(html_content: str) -> str:
    """HTML 문자열을 메모리에 저장하고 접근 가능한 상대 URL을 반환"""
    if len(INMEMORY_MAP_STORE) >= MAX_STORED_MAPS:
        oldest_key = next(iter(INMEMORY_MAP_STORE))
        INMEMORY_MAP_STORE.pop(oldest_key, None)

    map_id = str(uuid.uuid4())
    INMEMORY_MAP_STORE[map_id] = html_content
    return f"/api/inmemory-map/{map_id}"


def get_map_html(map_id: str) -> Optional[str]:
    """map_id로 저장된 HTML 조회"""
    return INMEMORY_MAP_STORE.get(map_id)