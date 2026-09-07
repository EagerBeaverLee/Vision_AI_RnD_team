import requests

from langchain_community.utilities import SQLDatabase

# db = SQLDatabase.from_uri("sqlite:///Chinook.db")

# print(f"Dialect: {db.dialect}")
# print(f"Available tables: {db.get_usable_table_names()}")
# print(f'Sample output: {db.run("SELECT * FROM Artist LIMIT 5;")}')

db = SQLDatabase.from_uri("sqlite:///weather_db.db")
print({db.run("SELECT DISTINCT 지점명 from weather_data")})