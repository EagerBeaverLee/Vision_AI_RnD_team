from langchain_openai import ChatOpenAI

class llm_model:
    api_key = ""
    def set_llm(self, key):
        self.api_key = key
    def get_llm(self):
        return ChatOpenAI(openai_api_key=self.api_key,
                        model_name="gpt-4o-mini")
