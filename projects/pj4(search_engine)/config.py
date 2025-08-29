import configparser

class IniConfigure:
    def __init__(self):
        self.config = configparser.ConfigParser()
        self.api_key = ""
        self.temp_val = ""
        self.query_val = ""
        self.url_val = ""
        self.search_eng_name = ""
    def load_iniconfig(self):
        self.config.read('setting.ini')

    def set_api(self, key):
        self.api_key = key

    def set_temp(self, val):
        self.temp_val = val

    def set_query(self, val):
        self.temp_val = val

    def set_url(self, val):
        self.url_val = val
    
    def set_search_eng(self, val):
        self.search_eng_name = val