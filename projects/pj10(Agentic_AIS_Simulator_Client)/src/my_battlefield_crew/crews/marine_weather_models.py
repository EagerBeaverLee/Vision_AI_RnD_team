from pydantic import BaseModel, Field
from typing import List, Dict, Any
from utils.mock_time_temp_tool import get_mock_current_time

#-----------------------------------------------------------
# weather_analysis_crew.py 에 해당되는 pydantic 데이터 모델
#-----------------------------------------------------------

class SqlFlowState(BaseModel):
    user_query: str = ""
    current_time: str = Field(default_factory=get_mock_current_time)
    generated_sql: str = ""
    execution_result: str = ""
    feedback: str = ""
    is_valid: bool = False
    retry_count: int = 0
    final_answer: str = ""

class SQLResultSchema(BaseModel):
    results: List[Dict[str, Any]] 