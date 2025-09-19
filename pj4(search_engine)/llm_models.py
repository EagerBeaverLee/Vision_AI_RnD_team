from langchain_openai import ChatOpenAI

class llm_model:
    api_key = None
    temp = 0.1
    def set_llm(self, key):
        self.api_key = key
    def set_temp(self, val):
        self.temp = float(val)
    def get_llm(self):
        return ChatOpenAI(openai_api_key=self.api_key,
                        model_name="gpt-4o-mini",
                        temperature=self.temp
                        )
