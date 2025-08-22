import copy
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from langchain_community.utilities import GoogleSerperAPIWrapper
from langchain_community.utilities import SerpAPIWrapper
from langchain_community.utilities.tavily_search import TavilySearchAPIWrapper
from typing import List

class search_engine:
    def duckduckgo_web_search(query: str, max_results: str) -> List[str]:
        return[r["link"] for r in DuckDuckGoSearchAPIWrapper().results(query, int(max_results))]

    def tavily_web_search(query: str, max_results: int) -> List[str]:
        if not query:
            return
        tavily_search_engine = TavilySearchAPIWrapper(
            tavily_api_key="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"
        )
        return[r["url"] for r in tavily_search_engine.results(query=query,max_results=max_results,search_depth="advanced")]

    def serp_web_search(query: str, max_results: str) -> List[str]:
        if not query:
            return
        serp_search_engine = SerpAPIWrapper(
            serpapi_api_key="8d73dfbfe66cb9c11254c04d6aef3932a6f501fdea81867fbea45ed6e0e8eb28"
        )
        answer_api = serp_search_engine.results(query=query)
        res = [copy.deepcopy(answer_api['organic_results'])]
        return [j["link"] for i in res for j in i if j["position"] <= int(max_results)]

    def serper_web_search(query: str, max_results: str) -> List[str]:
        if not query:
            return
        serper_search_engine = GoogleSerperAPIWrapper(
            serper_api_key="af1f4df11e53cf75f5decf12d6e5987f2ec35a31"
        )
        res = [serper_search_engine.results(query=query)['organic']]
        return [j["link"] for i in res for j in i if j["position"] <= int(max_results)]
