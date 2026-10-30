from pydantic import BaseModel, Field

class LLMConfig(BaseModel):
    api_key: str = Field(default="", description="OpenAI API 키")
    system_prompt: str = Field(default="", description="기본 시스템 프롬프트")
    temperature: float = Field(default=0.0, ge=0.0, le=1.0, description="생성 다양성 (0.0 ~ 1.0)")