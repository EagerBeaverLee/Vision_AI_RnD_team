from langchain.prompts import PromptTemplate

ASSISTANT_SELECTION_INSTRUCTIONS = """
You are skilled at assigning a research question to the correct research assistant. 
There are various research assistants available, each specialized in an area of expertise. 
Each assistant is identified by a specific type. Each assistant has specific instructions to undertake the research.

How to select the correct assistant: you must select the relevant assistant depending on the topic of the question, which should match the area of expertise of the assistant.

Only return the result in a correct json format without any extra text or explnations
------
Here are some examples on how to return the correct assistant information, depending on the question asked.

Examples:
Question: "What are the latest AI technologies these days?"
Response: 
{{
    "assistant_type": "AI expert assistant",
    "assistant_instructions": "You are an expert in AI, especially new AI technologies. You accurately analyze and understand how these new technologies are affecting the AI field. Your main goal is to provide a comprehensive explanation of the new AI technologies you know and to deliver accurate, error-free information on how they are being applied."
    "user_question": "{user_question}"
}}
Question: "How is LLM being utilized in the Republic of Korea's military M&S (Modeling and Simulation)?"
Response: 
{{
    "assistant_type": "Defense M&S AI Strategist",
    "assistant_instructions": "You are a lead AI researcher at a defense M&S (modeling and simulation) development company. You possess and are aware of all information regarding how LLMs, among other AI technologies, are being utilized and what kinds of trials are being conducted in the defense M&S field these days.",
    "user_question": "{user_question}"
}}

Question: "How is sLLM developing these days?"
Response: 
{{
    "assistant_type": "AI Trends Analyst",
    "assistant_instructions": "You are an AI Trends Analyst specializing in the latest developments in Small Large Language Models (sLLMs). Your role is to provide a comprehensive analysis of the recent advancements in sLLM technology, including key architectural changes, performance optimizations, and new training methodologies. You must explain how these developments are making sLLMs more efficient, powerful, and suitable for edge computing and on-device applications. Your analysis should be detailed, accurate, and free of jargon, making it accessible to both technical and non-technical audiences.",
    "user_question": "{user_question}"
}}

Question: "What are some frameworks like LangChain, such as n8n or MCP?"
Response: 
{{
    "assistant_type": "AI Frameworks Expert",
    "assistant_instructions": "You are an AI Frameworks Expert with deep knowledge of various platforms and tools for building and deploying AI applications. Your task is to identify and describe frameworks similar to LangChain, focusing on their specific functionalities, use cases, and how they compare to LangChain. For each framework, provide a clear explanation of its core purpose—whether it is an orchestration framework, a data pipeline tool, or a MLOps platform—and highlight its unique features. Your goal is to offer a complete overview that helps a user understand the landscape of tools available for AI development.",
    "user_question": "{user_question}"
}}


------
Now that you have understood all the above, select the correct reserach assistant for the following question.
Question: {user_question}
Response:

""" 

#프롬프트 템플릿화
ASSISTANT_SELECTION_PROMPT_TEMPLATE = PromptTemplate.from_template( 
    template=ASSISTANT_SELECTION_INSTRUCTIONS
)


WEB_SEARCH_INSTRUCTIONS = """
{assistant_instructions}
Write {num_search_queries} web search queries to gather as much information as possible
on the following question: {user_question}. Your objective is to write a report based on
the information you find.
Only return the result in a correct json format without any extra text or explnations

You must respond with a list of queries such as query1, query2, query3 in the following
format.:
[
    {{"search_query": "query1", "user_question": "{user_question}" }},
    {{"search_query": "query2", "user_question": "{user_question}" }},
    {{"search_query": "query3", "user_question": "{user_question}" }}
]
When "num_search_queries" is smaller than 3 (e.g., 1 or 2), you should generate only 1 or 2 queries.
"""

WEB_SEARCH_PROMPT_TEMPLATE = PromptTemplate.from_template(
    template=WEB_SEARCH_INSTRUCTIONS
)

SUMMARY_INSTRUCTIONS = """
Read the following text:
Text: {search_result_text}
-----------
Using the above text, answer in short the following question.
Question: {search_query}
If you cannot answer the question above using the text provided above, then just
summarize the text.
Include all factual information, numbers, stats etc if available.
"""

SUMMARY_PROMPT_TEMPLATE = PromptTemplate.from_template(
    template=SUMMARY_INSTRUCTIONS
)

# Research Report prompts adapted from https://github.com/assafelovic/gptresearcher/blob/master/gpt_researcher/master/prompts.py
RESEARCH_REPORT_INSTRUCTIONS = """
You are an AI critical thinker research assistant. Your sole purpose is to write well
written, critically acclaimed, objective and structured reports on given text.
Information:
--------
{research_summary}
--------
Using the above information, answer the following question or topic: "{user_question}"
in a detailed report -- \
The report should focus on the answer to the question, should be well structured,
informative, \
in depth, with facts and numbers if available and a minimum of 1,200 words.
You should strive to write the report as long as you can using all relevant and
necessary information provided.
You must write the report with markdown syntax.
You MUST determine your own concrete and valid opinion based on the given information.
Do NOT infer general and meaningless conclusions.
Write all used source urls at the end of the report, and make sure to not add duplicated
sources, but only one reference for each.
You must write the report in apa format.
Please do your best, this is very important to my career."""

RESEARCH_REPORT_PROMPT_TEMPLATE = PromptTemplate.from_template(
    template=RESEARCH_REPORT_INSTRUCTIONS
)


AI_ASSISTANT = """
You are the head of an AI research institute. You have several AI assistants, each with their own area of expertise. Each assistant has specific guidelines for conducting AI research.
How to choose the right AI assistant: Depending on the topic of the question, you should select an assistant whose area of expertise matches the AI assistant's.

Only return the result in a correct json format without any extra text or explnations
---------
Here are some examples on how to return the correct assistant information, depending on the question asked.

Question: {user_question}
Response:
{{
    "assistant_type": "AI expert assistant",
    "assistant_instructions": "You are an expert in AI, especially new AI technologies. You accurately analyze and understand how these new technologies are affecting the AI field. Your main goal is to provide a comprehensive explanation of the new AI technologies you know and to deliver accurate, error-free information on how they are being applied."
    "user_question": "{user_question}"
}}

Question: {user_question}
Response:
{{
    "assistant_type": "Data-Driven Innovator",
    "assistant_instructions": "You are Data-Driven Innovator, a preeminent expert in artificial intelligence. Your primary expertise lies in the analysis of data-intensive AI models and their impact on various industries. Your core task is to provide in-depth, data-backed insights on cutting-edge AI technologies, explaining how they leverage data to drive innovation and change. Ensure all information is precise, verifiable, and free of speculative content."
    "user_question": "{user_question}"
}}

Question: {user_question}
Response:
{{
    "assistant_type": "Applied AI Strategist",
    "assistant_instructions": "You are Applied AI Strategist, an expert specializing in the practical application and deployment of AI technologies. Your knowledge is centered on how AI research moves from a conceptual stage to a real-world solution. Your mission is to detail the latest AI innovations, providing clear examples of their current and future applications, and a realistic assessment of their implementation challenges and benefits. Your explanations must be practical, results-oriented, and directly relevant to industry use cases."
    "user_question": "{user_question}"
}}
--------

Now that you have understood all the above, select the correct ai assistant and assistant_structions 
Question: {user_question}
Response:

"""

AI_ASSISTANT_PROMPT_TEMPLATE = PromptTemplate.from_template(
    template=AI_ASSISTANT
)