from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from my_battlefield_crew.tools.sql_db_execution import execute_sql_query
from my_battlefield_crew.crews.marine_weather_models import SQLResultSchema
from my_battlefield_crew.setting.LLM_model_set import lms_llm

import sys
from pathlib import Path
from my_battlefield_crew.chainlit_app.chainlit_handler import ChainlitCrewHandler

@CrewBase
class MarineWeatherCrew:
    """해상 날씨 분석을 위한 CrewBase 정의"""

    agents_config = 'config/marine_weather_agents.yaml'
    tasks_config = 'config/marine_weather_tasks.yaml'

    def __init__(self, handler: ChainlitCrewHandler=None):
        self.handler = handler
        self.active_tool = [execute_sql_query(self.handler)]

    @agent
    def sql_generator_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['sql_generator_agent'],
            allow_delegation=False,
            llm=lms_llm,
            verbose=True
        )

    @agent
    def sql_executor_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['sql_executor_agent'],
            tools=self.active_tool,
            llm=lms_llm,
            verbose=True
        )

    @agent
    def data_analyst_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['data_analyst_agent'],
            llm=lms_llm,
            verbose=True
        )

    @task
    def generate_sql_task(self) -> Task:
        return Task(
            config=self.tasks_config['generate_sql_task'],
            agent=self.sql_generator_agent()
        )

    @task
    def validate_and_execute_sql_task(self) -> Task:
        return Task(
            config=self.tasks_config['validate_and_execute_sql_task'],
            output_pydantic=SQLResultSchema,
            agent=self.sql_executor_agent() 
        )

    @task
    def generate_final_answer_task(self) -> Task:
        return Task(
            config=self.tasks_config['generate_final_answer_task'],
            agent=self.data_analyst_agent()
        )