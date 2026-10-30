from pydantic import BaseModel, Field
from typing import List, Dict, Any

#-----------------------------------------------------------
# weather_analysis_crew.py 에 해당되는 pydantic 데이터 모델
#-----------------------------------------------------------

class SqlFlowState(BaseModel):
    user_query: str = ""
    current_time: str = ""
    generated_sql: str = ""
    execution_result: str = ""
    feedback: str = ""
    is_valid: bool = False
    retry_count: int = 0
    final_answer: str = ""

class SQLResultSchema(BaseModel):
    results: List[Dict[str, Any]] 