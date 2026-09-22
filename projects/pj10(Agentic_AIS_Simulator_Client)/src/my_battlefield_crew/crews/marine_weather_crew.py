from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from tools.sql_db_execution import execute_sql_query
from crews.marine_weather_models import SQLResultSchema
# from marine_weather_models import SQLResultSchema

@CrewBase
class MarineWeatherCrew:
    """해상 날씨 분석을 위한 CrewBase 정의"""

    agents_config = 'config/marine_weather_agents.yaml'
    tasks_config = 'config/marine_weather_tasks.yaml'

    @agent
    def sql_generator_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['sql_generator_agent'],
            verbose=True, 
            allow_delegation=False
        )

    @agent
    def sql_executor_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['sql_executor_agent'],
            tools=[execute_sql_query],
            verbose=True
        )

    @agent
    def data_analyst_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['data_analyst_agent'],
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