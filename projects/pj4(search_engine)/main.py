import sys, markdown
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QRadioButton, QMessageBox
)
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QDoubleValidator, QIntValidator

from langchain.schema.runnable import RunnablePassthrough
from langchain.schema.output_parser import StrOutputParser
from langchain.schema.runnable import RunnableLambda, RunnableParallel

from langchain_openai import ChatOpenAI
from mainwindow import Ui_MainWindow
from prompts import TRANSLATE_ASSISTANT_PROMPT_TEMPLATE
from prompts import ASSISTANT_SELECTION_PROMPT_TEMPLATE
from prompts import WEB_SEARCH_PROMPT_TEMPLATE
from prompts import SUMMARY_PROMPT_TEMPLATE
from prompts import RESEARCH_REPORT_PROMPT_TEMPLATE
from utilities import to_obj
from llm_models import llm_model
from web_searching import search_engine
from web_scraping import web_scrape
from config import IniConfigure


class Window(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        validator = QDoubleValidator()
        validator.setRange(0.00, 1.00)
        validator.setDecimals(2)
        validator.setNotation(QDoubleValidator.StandardNotation)
        self.ui.temp_val.setValidator(validator)

        validator2 = QDoubleValidator()
        validator2.setRange(2, 10)
        validator2.setNotation(QDoubleValidator.StandardNotation)
        self.ui.query_val.setValidator(validator2)

        validator3 = QDoubleValidator()
        validator3.setRange(1, 10)
        validator3.setNotation(QDoubleValidator.StandardNotation)
        self.ui.url_val.setValidator(validator3)

        self.llm = llm_model()
        self.connectionSlots()
        self.search_eng_name = ""
        self.temp_num = "0"
        self.query_num = 0
        self.url_num = 0
        self.appending_res = ""         # 최종research 결과를 추가할 str변수

        self.ui.temp_val.setText("0")
        self.ui.query_val.setText("2")
        self.ui.url_val.setText("1")

        self.ui.duckduckgo_eng.setChecked(True)

        self.config = IniConfigure()

    def connectionSlots(self):
        self.ui.send_btn.clicked.connect(self.apply)
        self.ui.api_key_txt.textChanged.connect(self.apply_api_key)
        self.ui.duckduckgo_eng.toggled.connect(self.apply_search_engine)
        self.ui.tavily_eng.toggled.connect(self.apply_search_engine)
        self.ui.serp_eng.toggled.connect(self.apply_search_engine)
        self.ui.serper_eng.toggled.connect(self.apply_search_engine)

        self.ui.temp_slider.valueChanged.connect(self.slider_temp)
        self.ui.temp_val.textChanged.connect(self.text_temp)
        self.ui.query_num_slider.valueChanged.connect(self.slider_query_num)
        self.ui.query_val.textChanged.connect(self.text_query_num)
        self.ui.url_num_slider.valueChanged.connect(self.slider_url_num)
        self.ui.url_val.textChanged.connect(self.text_url_num)
    
    def apply(self):
        if not self.llm.api_key:
            QMessageBox.about(
            self,
            "Error",
            "<p>Please enter your api key</p>",
            )
            return
        self.llm.set_temp(self.temp_num)
        self.build_chain()
        msg = self.ui.input_txt.toPlainText().strip()
        self.ui.input_txt.clear()
                
        #search_engine develop==============
        # print(self.query_num)
        # chain2 = (
        #     self.assistant_instruction_chain
        #     | self.web_searches_chain
        # )
        # res2 = chain2.invoke(msg)
        # print(res2)

        # chain = (
        #     chain2
        #     | self.search_result_urls_chain.map()
        # )        
        # res = chain.invoke(msg)
        # print("res")
        # print(res)
        #===================================

        #search_engine develop2==============
        # json = [[{'result_url': 'https://aws.amazon.com/what-is/retrieval-augmented-generation/', 'search_query': 'What is Retrieval-Augmented Generation (RAG) model?', 'user_question': 'What is RAG?'}, {'result_url': 'https://cloud.google.com/use-cases/retrieval-augmented-generation', 'search_query': 'What is Retrieval-Augmented Generation (RAG) model?', 'user_question': 'What is RAG?'}, {'result_url': 'https://blogs.nvidia.com/blog/what-is-retrieval-augmented-generation/', 'search_query': 'What is Retrieval-Augmented Generation (RAG) model?', 'user_question': 'What is RAG?'}], [{'result_url': 'https://learn.microsoft.com/en-us/azure/search/retrieval-augmented-generation-overview', 'search_query': 'RAG architecture and how it integrates retrieval with generative models', 'user_question': 'What is RAG?'}, {'result_url': 'https://humanloop.com/blog/rag-architectures', 'search_query': 'RAG architecture and how it integrates retrieval with generative models', 'user_question': 'What is RAG?'}, {'result_url': 'https://www.k2view.com/blog/rag-architecture/', 'search_query': 'RAG architecture and how it integrates retrieval with generative models', 'user_question': 'What is RAG?'}], [{'result_url': 'https://www.microsoft.com/en-us/microsoft-cloud/blog/2025/02/13/5-key-features-and-benefits-of-retrieval-augmented-generation-rag/', 'search_query': 'Applications and advantages of Retrieval-Augmented Generation', 'user_question': 'What is RAG?'}, {'result_url': 'https://hyperight.com/7-practical-applications-of-rag-models-and-their-impact-on-society/', 'search_query': 'Applications and advantages of Retrieval-Augmented Generation', 'user_question': 'What is RAG?'}, {'result_url': 'https://en.wikipedia.org/wiki/Retrieval-augmented_generation', 'search_query': 'Applications and advantages of Retrieval-Augmented Generation', 'user_question': 'What is RAG?'}], [{'result_url': 'https://www.chitika.com/retrieval-augmented-generation-rag-the-definitive-guide-2025/', 'search_query': 'Recent advancements in Retrieval-Augmented Generation models', 'user_question': 'What is RAG?'}, {'result_url': 'https://arxiv.org/html/2407.13193v1', 'search_query': 'Recent advancements in Retrieval-Augmented Generation models', 'user_question': 'What is RAG?'}, {'result_url': 'https://arxiv.org/abs/2410.12837', 'search_query': 'Recent advancements in Retrieval-Augmented Generation models', 'user_question': 'What is RAG?'}], [{'result_url': 'https://aws.amazon.com/what-is/retrieval-augmented-generation/', 'search_query': 'RAG model examples and use cases in AI', 'user_question': 'What is RAG?'}, {'result_url': 'https://www.superannotate.com/blog/rag-explained', 'search_query': 'RAG model examples and use cases in AI', 'user_question': 'What is RAG?'}, {'result_url': 'https://hyperight.com/7-practical-applications-of-rag-models-and-their-impact-on-society/', 'search_query': 'RAG model examples and use cases in AI', 'user_question': 'What is RAG?'}]]

        # summary_chain = (
        #     self.serach_result_text_and_summary_chain.map()
        #     | RunnableLambda(lambda x:
        #         {
        #             'summary': '\n'.join([i['summary'] for i in x]),
        #             'user_question': x[0]['user_question'] if len(x) > 0 else ''
        #         }
        #     )
        # )
        # result_chain = (
        #     summary_chain.map()
        #     | RunnableLambda(
        #         lambda x:
        #         {
        #             'research_summary': '\n\n'.join([i['summary'] for i in x]),
        #             'user_question': x[0]['user_question'] if len(x) > 0 else ''
        #         }
        #     )
        #     | RESEARCH_REPORT_PROMPT_TEMPLATE | self.llm.get_llm() | StrOutputParser()
        # )

        # res = result_chain.invoke(json)
        # print(res)
        # self.ui.research_txt.append(str(res))
        #=====================================================


        llm_res =  self.web_research_chain.invoke(msg)
        print(llm_res)
        self.appending_res += "\n\n\n"
        self.appending_res += llm_res
        html_out = markdown.markdown(self.appending_res)
        self.ui.research_txt.setHtml(html_out)        

    def build_chain(self):
        self.assistant_instruction_chain = (
            {'user_question': RunnablePassthrough()}
            | ASSISTANT_SELECTION_PROMPT_TEMPLATE | self.llm.get_llm() | StrOutputParser() | to_obj
        )

        self.web_searches_chain = (
            RunnableLambda(lambda x:{
                'assistant_instructions': x['assistant_instructions'],
                'num_search_queries': self.query_num,
                'user_question': x['user_question']
            }
            )
            | WEB_SEARCH_PROMPT_TEMPLATE | self.llm.get_llm() | StrOutputParser() | to_obj
        )
        engine_dict = {
            'duckduckgo': search_engine.duckduckgo_web_search,
            'serper': search_engine.serper_web_search,
            'tavily': search_engine.tavily_web_search,
            'serp': search_engine.serp_web_search
        }
        self.search_result_urls_chain = (
            RunnableLambda(lambda x:
                [
                    {
                        'result_url': url,
                        'search_query': x['search_query'],
                        'user_question': x['user_question']
                    }
                    for url in engine_dict[self.search_eng_name](query=x['search_query'], max_results=self.url_num)
                ]
            )
        )
 
        self.search_result_text_and_summary_chain = (
            RunnableLambda(
                lambda x:
                {
                    'search_result_text': web_scrape(url=x['result_url'])[:10000],
                    'result_url': x['result_url'],
                    'search_query': x['search_query'],
                    'user_question': x['user_question']
                }
            )
            | RunnableParallel(
                {
                    'text_summary': SUMMARY_PROMPT_TEMPLATE | self.llm.get_llm() | StrOutputParser(),
                    'result_url': lambda x: x['result_url'],
                    'user_question': lambda x: x['user_question']
                }
            )
            | RunnableLambda(
                lambda x:
                {
                    'summary': f"Source Url:{x['result_url']}\nSummary: {x['text_summary']}",
                    'user_question': x['user_question']
                }
            )
        )

        self.search_and_summarization_chain = (
            self.search_result_urls_chain
            | self.search_result_text_and_summary_chain.map()
            | RunnableLambda(lambda x:
                {
                    'summary': '\n'.join([i['summary'] for i in x]),
                    'user_question': x[0]['user_question'] if len(x) > 0 else ''
                }
            )
        )

        self.web_research_chain = (
            self.assistant_instruction_chain
            | self.web_searches_chain
            | self.search_and_summarization_chain.map()
            | RunnableLambda(
                lambda x:
                {
                    'research_summary': '\n\n'.join([i['summary'] for i in x]),
                    'user_question': x[0]['user_question'] if len(x) > 0 else ''
                }
            )
            | RESEARCH_REPORT_PROMPT_TEMPLATE | self.llm.get_llm() | StrOutputParser()
        )
    
    def apply_api_key(self):
        key = self.ui.api_key_txt.text().strip()
        if(key):
            self.llm.set_llm(key)
            self.config.set_api(key)

    def slider_temp(self):
        val = self.ui.temp_slider.value() / 100
        if val == float(self.temp_num):
            return
        self.temp_num = str(val)
        self.apply_temp()

    def text_temp(self):
        val = self.ui.temp_val.text().strip()
        if val == self.temp_num or val == "":
            return
        self.temp_num = val
        self.config.set_temp
        self.apply_temp()
        
    def apply_temp(self):
        val = self.temp_num
        if self.ui.temp_slider.value() * 0.01 != float(val):
            self.ui.temp_slider.setValue(int(float(val) * 100))
        if self.ui.temp_val.text().strip() != val:
            self.ui.temp_val.setText(val)

    def slider_query_num(self):
        val = self.ui.query_num_slider.value()
        if val == str(self.query_num):
            return
        self.query_num = val
        self.apply_query_num()

    def text_query_num(self):
        val = self.ui.query_val.text().strip()
        if val == str(self.query_num) or val == 0:
            return
        self.query_num = int(val)
        self.apply_query_num()
        
    def apply_query_num(self):
        val = self.query_num
        if self.ui.query_num_slider.value() != str(val):
            self.ui.query_num_slider.setValue(val)
        if self.ui.query_val.text().strip() != str(val):
            self.ui.query_val.setText(str(val))

    def slider_url_num(self):
        val = self.ui.url_num_slider.value()
        if val == self.url_num:
            return
        self.url_num = str(val)
        self.apply_url_num()

    def text_url_num(self):
        val = self.ui.url_val.text().strip()
        if val == self.url_num or val == "":
            return
        self.url_num = val
        self.apply_url_num()

    def apply_url_num(self):
        val = self.url_num
        if self.ui.url_num_slider.value() != val:
            self.ui.url_num_slider.setValue(int(val))
        if self.ui.url_val.text().strip() != val:
            self.ui.url_val.setText(val)

    def apply_search_engine(self):
        radio_btn = self.sender()
        if radio_btn.isChecked():
            self.search_eng_name = radio_btn.text()
            self.ui.selected_engine.setText(f'{radio_btn.text()}')


if __name__ == "__main__":

    app = QApplication(sys.argv)
    win = Window()
    win.show()
    sys.exit(app.exec())