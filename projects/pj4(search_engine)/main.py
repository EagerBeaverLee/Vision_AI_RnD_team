import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QRadioButton
)
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QDoubleValidator

from langchain.schema.runnable import RunnablePassthrough
from langchain.schema.output_parser import StrOutputParser
from langchain.schema.runnable import RunnableLambda, RunnableParallel

from langchain_openai import ChatOpenAI
from mainwindow import Ui_MainWindow
from prompts import ASSISTANT_SELECTION_PROMPT_TEMPLATE
from prompts import WEB_SEARCH_PROMPT_TEMPLATE
from prompts import SUMMARY_PROMPT_TEMPLATE
from prompts import RESEARCH_REPORT_PROMPT_TEMPLATE
from utilities import to_obj
from llm_models import llm_model
from web_searching import web_search
from web_scraping import web_scrape

class Window(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        validator = QDoubleValidator()
        validator.setRange(1, 100)
        validator.setNotation(QDoubleValidator.StandardNotation)
        self.ui.query_val.setValidator(validator)

        self.llm = llm_model()
        self.connectionSlots()
        self.current_eng = ""
        self.query_num = ""
        self.url_num = ""

        self.ui.query_val.setText("1")
        self.ui.url_val.setText("1")

        self.ui.google_btn.setChecked(True)

    def connectionSlots(self):
        self.ui.send_btn.clicked.connect(self.apply)
        self.ui.api_key_txt.textChanged.connect(self.apply_api_key)
        self.ui.google_btn.toggled.connect(self.apply_search_engine)
        self.ui.naver_btn.toggled.connect(self.apply_search_engine)
        self.ui.query_num_slider.valueChanged.connect(self.slider_query_num)
        self.ui.query_val.textChanged.connect(self.text_query_num)
        self.ui.url_num_slider.valueChanged.connect(self.slider_url_num)
        self.ui.url_val.textChanged.connect(self.text_url_num)
    
    def apply(self):
        self.build_chain()
        msg = self.ui.input_txt.toPlainText().strip()
        chain =(
            self.assistant_instruction_chain
            | self.web_searches_chain
        )
        llm_res =  chain.invoke(msg)
        self.ui.research_txt.append(str(llm_res))
        self.ui.research_txt.append("")
        

    def build_chain(self):
        self.assistant_instruction_chain = (
            {'user_question': RunnablePassthrough()}
            | ASSISTANT_SELECTION_PROMPT_TEMPLATE | self.llm.get_llm() | StrOutputParser() | to_obj
        )

        self.web_searches_chain = (
            RunnableLambda(lambda x:{
                'assistant_instructions': x['assistant_instructions'],
                'num_search_queries': int(self.query_num),
                'user_question': x['user_question']
            }
            )
            | WEB_SEARCH_PROMPT_TEMPLATE | self.llm.get_llm() | StrOutputParser() | to_obj
        )
    
    def apply_api_key(self):
        if(self.ui.api_key_txt.text().strip()):
            self.llm.set_llm(self.ui.api_key_txt.text().strip())

    def slider_query_num(self):
        val = self.ui.query_num_slider.value()
        if val == self.query_num:
            return
        self.query_num = str(val)
        self.apply_query_num()

    def text_query_num(self):
        val = self.ui.query_val.text().strip()
        if val == self.query_num or val == "":
            return
        self.query_num = val
        self.apply_query_num()
        
    def apply_query_num(self):
        val = self.query_num
        if self.ui.query_num_slider.value() != val:
            self.ui.query_num_slider.setValue(int(val))
        if self.ui.query_val.text().strip() != val:
            self.ui.query_val.setText(val)

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
            self.current_eng = radio_btn.text()
            self.ui.selected_engine.setText(f'{radio_btn.text()}')



if __name__ == "__main__":

    app = QApplication(sys.argv)
    win = Window()
    win.show()
    sys.exit(app.exec())