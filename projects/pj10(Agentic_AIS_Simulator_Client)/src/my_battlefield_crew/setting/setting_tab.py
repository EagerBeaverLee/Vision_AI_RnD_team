from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from my_battlefield_crew.setting.llm_config import LLMConfig
from my_battlefield_crew.ui.mainwindow import Ui_MainWindow

class SettingTabManager(QObject):
    config_changed = pyqtSignal(LLMConfig)

    """'setting' 탭 전담 매니저 (API Key, Prompt, Temperature 조작)"""
    def __init__(self, ui: Ui_MainWindow, parent=None):
        super().__init__(parent)
        self.ui = ui

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._emit_config_changed)
        
        self._init_signals()

    def _init_signals(self):
        # 💡 Temperature: 슬라이더(0~200) <-> 더블스핀박스(0.00~2.00) 동기화
        # (온도 범위를 0.0~1.0으로 사용하신다면 / 100.0 으로 맞추시면 됩니다)
        self.ui.slider_temp.valueChanged.connect(
            lambda v: self.ui.spin_temp.setValue(v / 100.0)
        )
        self.ui.spin_temp.valueChanged.connect(
            lambda v: self.ui.slider_temp.setValue(round(v * 100))
        )

    def _connect_change_events(self):
        """UI 값 변경 시 타이머를 트리거하여 시그널 발생 대기"""
        self.ui.edit_api_key.textChanged.connect(self._notify_change)
        self.ui.edit_prompt.textChanged.connect(self._notify_change)
        self.ui.spin_temp.valueChanged.connect(self._notify_change)

    def _notify_change(self, *args):
        """사용자가 입력을 멈춘 후 300ms 뒤에 한 번만 시그널 방출"""
        self._debounce_timer.start(300)

    def _emit_config_changed(self):
        """최신 Pydantic 객체를 생성하여 외부에 시그널 방출"""
        current_config = self.get_config()
        self.config_changed.emit(current_config)

    def get_config(self) -> LLMConfig:
        """UI에 입력된 LLM 설정 추출"""
        return LLMConfig(
            api_key=self.ui.edit_api_key.text().strip(),
            system_prompt=self.ui.edit_prompt.toPlainText().strip(),
            temperature=self.ui.spin_temp.value()
        )

    def set_config(self, config: LLMConfig):
        """저장된 LLM 설정을 UI에 주입"""
        self.ui.edit_api_key.setText(config.api_key)
        self.ui.edit_prompt.setPlainText(config.system_prompt)
        self.ui.spin_temp.setValue(config.temperature)