from PyQt6.QtWidgets import QButtonGroup
from PyQt6.QtCore import QObject
from my_battlefield_crew.RAG.rag_config import (
    RAGConfig, IndexingConfig, PostProcessingConfig,
    QuestionTransformType, IndexingType
)
from my_battlefield_crew.ui.mainwindow import Ui_MainWindow

class RAGSettingManager(QObject):
    def __init__(self, ui: Ui_MainWindow, parent=None):
        super().__init__(parent)
        self.ui = ui
        self._init_button_groups()
        self._init_signals()

    def _init_button_groups(self):
        """1. 라디오 버튼들을 QButtonGroup으로 묶어 배타적 선택 보장 및 관리 단순화"""
        # Question Transformations 그룹
        self.qt_group = QButtonGroup(self)
        self.qt_group.addButton(self.ui.radio_qt_default, 0)
        self.qt_group.addButton(self.ui.radio_qt_rewrite, 1)
        self.qt_group.addButton(self.ui.radio_qt_multi, 2)
        self.qt_group.addButton(self.ui.radio_qt_stepback, 3)

        # Advanced Indexing 그룹
        self.idx_group = QButtonGroup(self)
        self.idx_group.addButton(self.ui.radio_idx_default, 0)
        self.idx_group.addButton(self.ui.radio_idx_parent, 1)
        self.idx_group.addButton(self.ui.radio_idx_summary, 2)
        self.idx_group.addButton(self.ui.radio_idx_hypo, 3)
        self.idx_group.addButton(self.ui.radio_idx_granular, 4)
        self.idx_group.addButton(self.ui.radio_idx_k_parent, 5)

    def _init_signals(self):
        """2. 라디오 버튼 / 체크박스 상태에 따라 하위 입력창(SpinBox/Edit) 활성화/비활성화 연동"""
        self.qt_group.idToggled.connect(self._on_transformation_changed)
        self.idx_group.idToggled.connect(self._on_indexing_changed)        
        
        # Post-Processing 체크박스 활성화 연동
        self.ui.chk_similarity.toggled.connect(self.ui.slider_similarity.setEnabled)
        self.ui.chk_similarity.toggled.connect(self.ui.spin_similarity.setEnabled)
        self.ui.chk_keywords.toggled.connect(self.ui.edit_keywords.setEnabled)

        # 슬라이더(0~100 정수)와 더블스핀박스(0.0~1.0 소수) 상호 연동
        self.ui.slider_similarity.valueChanged.connect(lambda v: self.ui.spin_similarity.setValue(v / 100.0))
        self.ui.spin_similarity.valueChanged.connect(lambda v: self.ui.slider_similarity.setValue(int(v * 100)))

        # 1. 슬라이더 변경 시 -> 두 스핀박스 동시 갱신 (int 제거, 소수점 보정)
        self.ui.slider_weight.valueChanged.connect(
            lambda v: self.ui.spin_key_weight_5.setValue(v / 100.0)
        )
        self.ui.slider_weight.valueChanged.connect(
            lambda v: self.ui.spin_similarity_weight_5.setValue((100 - v) / 100.0)
        )
        # 2. 키워드 스핀박스 변경 시 -> 슬라이더만 갱신 (round 필수)
        self.ui.spin_key_weight_5.valueChanged.connect(
            lambda v: self.ui.slider_weight.setValue(round(v * 100))
        )
        # 3. 유사도 스핀박스 변경 시 -> 슬라이더만 갱신 (round 필수)
        self.ui.spin_similarity_weight_5.valueChanged.connect(
            lambda v: self.ui.slider_weight.setValue(round((1.0 - v) * 100))
        )

        # 💡 시작 시 초기 기본값 선택 및 UI 상태 수동 동기화 (1회 강제 실행)
        self.ui.radio_qt_default.setChecked(True)
        self.ui.radio_idx_default.setChecked(True)
        self.ui.chk_similarity.setChecked(True)
        self.ui.chk_similarity.setChecked(False)
        self.ui.chk_keywords.setChecked(True)
        self.ui.chk_keywords.setChecked(False)
        self._on_transformation_changed()
        self._on_indexing_changed()

    def _set_checkbox_state(self, checkbox, enabled: bool):
        """💡 핵심 헬퍼: 활성화 상태를 변경하고, 비활성화(False)될 때 체크가 되어있다면 해제"""
        checkbox.setEnabled(enabled)
        if not enabled and checkbox.isChecked():
            checkbox.setChecked(False)

    def _on_transformation_changed(self):
        qt_id = self.qt_group.checkedId()
        idx_id = self.idx_group.checkedId()

        # 1. K-Parent 라디오 버튼: Multi-Query(2)일 때만 활성화
        is_k_parent_allowed = (qt_id == 2)
        self.ui.radio_idx_k_parent.setEnabled(is_k_parent_allowed)
        
        # 라디오 버튼은 체크를 끄기만 하면 그룹 상태가 깨지므로 Default로 전환
        if not is_k_parent_allowed and self.ui.radio_idx_k_parent.isChecked():
            self.ui.radio_idx_default.setChecked(True)

        # 2. Similarity & Keywords: Multi-Query(2)가 아닐 때만 활성화 (비활성화 시 체크 해제)
        self._set_checkbox_state(self.ui.chk_similarity, qt_id != 2)
        self._set_checkbox_state(self.ui.chk_keywords, qt_id != 2)

        # 3. RRF: Multi-Query(2)이면서 동시에 K-Parent(5)가 아닐 때만 활성화 (비활성화 시 체크 해제)
        can_use_rrf = (qt_id == 2 and idx_id != 5)
        self._set_checkbox_state(self.ui.chk_rrf, can_use_rrf)

    def _on_indexing_changed(self):
        """라디오 버튼 선택에 따라 필요한 하위 입력 박스만 활성화"""
        qt_id  = self.qt_group.checkedId()
        idx_id = self.idx_group.checkedId()

        # ParentRetriever (id: 1)
        self.ui.spin_parent_chunk_1.setEnabled(idx_id == 1)
        self.ui.spin_child_chunk_1.setEnabled(idx_id == 1)
        # Summary (id: 2)
        self.ui.spin_parent_chunk_2.setEnabled(idx_id == 2)
        # Hypothetical (id: 3)
        self.ui.spin_parent_chunk_3.setEnabled(idx_id == 3)
        # Granular (id: 4)
        self.ui.spin_chunk_4.setEnabled(idx_id == 4)
        # ParentKeyword (id: 5)
        self.ui.spin_k_5.setEnabled(idx_id == 5)
        self.ui.spin_key_weight_5.setEnabled(idx_id == 5)
        self.ui.slider_weight.setEnabled(idx_id == 5)
        self.ui.spin_similarity_weight_5.setEnabled(idx_id == 5)

        # RRF 조건 갱신: K-Parent(5)가 아니면서 Multi-Query(2)여야 함
        can_use_rrf = (qt_id == 2 and idx_id != 5)
        self._set_checkbox_state(self.ui.chk_rrf, can_use_rrf)

    # =========================================================================
    # 💡 핵심: 수십 개의 Getter/Setter 대신 '일괄 추출'과 '일괄 주입' 메서드만 정의
    # =========================================================================

    def get_config(self) -> RAGConfig:
        """UI 현재 상태를 즉시 Pydantic RAGConfig 객체로 빌드"""
        qt_map = {
            0: QuestionTransformType.DEFAULT,
            1: QuestionTransformType.REWRITE_RETRIEVE_READ,
            2: QuestionTransformType.MULTIPLE_QUESTIONS,
            3: QuestionTransformType.STEP_BACK,
        }
        idx_map = {
            0: IndexingType.DEFAULT,
            1: IndexingType.PARENT_RETRIEVER,
            2: IndexingType.SUMMARY,
            3: IndexingType.HYPOTHETICAL,
            4: IndexingType.GRANULAR,
            5: IndexingType.PARENT_KEYWORD,
        }

        # 1. Indexing 세부 파라미터 수집
        curr_idx = idx_map.get(self.idx_group.checkedId(), IndexingType.DEFAULT)
        idx_config = IndexingConfig(strategy=curr_idx)
        if curr_idx == IndexingType.PARENT_RETRIEVER:
            idx_config.parent_chunk_size = self.ui.spin_parent_chunk_1.value()
            idx_config.child_chunk_size = self.ui.spin_child_chunk_1.value()
        elif curr_idx == IndexingType.SUMMARY:
            idx_config.parent_chunk_size = self.ui.spin_parent_chunk_2.value()
        elif curr_idx == IndexingType.HYPOTHETICAL:
            idx_config.parent_chunk_size = self.ui.spin_parent_chunk_3.value()
        elif curr_idx == IndexingType.GRANULAR:
            idx_config.chunk_size = self.ui.spin_chunk_4.value()
        elif curr_idx == IndexingType.PARENT_KEYWORD:
            idx_config.k = self.ui.spin_k_5.value()
            idx_config.weight = self.ui.spin_key_weight_5.value()

        # 2. Post Processing 수집 (💡 isEnabled() 검증을 추가하여 비활성화된 항목이 True로 수집되는 현상 차단)
        is_sim_active = self.ui.chk_similarity.isChecked() and self.ui.chk_similarity.isEnabled()
        is_kw_active = self.ui.chk_keywords.isChecked() and self.ui.chk_keywords.isEnabled()
        is_rrf_active = self.ui.chk_rrf.isChecked() and self.ui.chk_rrf.isEnabled()

        post_config = PostProcessingConfig(
            use_similarity=is_sim_active,
            similarity_threshold=self.ui.spin_similarity.value() if is_sim_active else 0.0,
            use_keywords=is_kw_active,
            keywords=self.ui.edit_keywords.text().strip() if is_kw_active else "",
            use_rrf=is_rrf_active,
        )

        return RAGConfig(
            question_transform=qt_map.get(self.qt_group.checkedId(), QuestionTransformType.DEFAULT),
            indexing=idx_config,
            post_processing=post_config,
            source_path=self.ui.edit_path.text().strip()
        )

    def set_config(self, config: RAGConfig):
        """저장된 RAGConfig 모델을 받아 UI 위젯에 한 번에 덮어쓰기"""
        # Question Transform
        qt_btn_map = {
            QuestionTransformType.DEFAULT: self.ui.radio_qt_default,
            QuestionTransformType.REWRITE_RETRIEVE_READ: self.ui.radio_qt_rewrite,
            QuestionTransformType.MULTIPLE_QUESTIONS: self.ui.radio_qt_multi,
            QuestionTransformType.STEP_BACK: self.ui.radio_qt_stepback,
        }
        qt_btn_map.get(config.question_transform, self.ui.radio_qt_default).setChecked(True)

        # Indexing
        idx_btn_map = {
            IndexingType.DEFAULT: self.ui.radio_idx_default,
            IndexingType.PARENT_RETRIEVER: self.ui.radio_idx_parent,
            IndexingType.SUMMARY: self.ui.radio_idx_summary,
            IndexingType.HYPOTHETICAL: self.ui.radio_idx_hypo,
            IndexingType.GRANULAR: self.ui.radio_idx_granular,
            IndexingType.PARENT_KEYWORD: self.ui.radio_idx_k_parent,
        }
        idx_btn_map.get(config.indexing.strategy, self.ui.radio_idx_default).setChecked(True)

        # 💡 3. 핵심: 양쪽 라디오 버튼이 모두 세팅된 후, 상호 연동 규칙을 실행하여 활성화/비활성화 상태를 먼저 확정
        self._on_transformation_changed()
        self._on_indexing_changed()

        # 4. Indexing 세부 수치 주입 (spinbox 값 설정 시 연결된 slider도 valueChanged로 자동 동기화됨)
        self.ui.spin_parent_chunk_1.setValue(config.indexing.parent_chunk_size)
        self.ui.spin_child_chunk_1.setValue(config.indexing.child_chunk_size)
        self.ui.spin_parent_chunk_2.setValue(config.indexing.parent_chunk_size)
        self.ui.spin_parent_chunk_3.setValue(config.indexing.parent_chunk_size)
        self.ui.spin_chunk_4.setValue(config.indexing.chunk_size)
        self.ui.spin_k_5.setValue(config.indexing.k)
        self.ui.spin_key_weight_5.setValue(config.indexing.weight)

        # 5. Post Processing 복원 (활성화되어 있는 경우에만 체크를 반영하도록 안전 처리)
        if self.ui.chk_similarity.isEnabled():
            self.ui.chk_similarity.setChecked(config.post_processing.use_similarity)
        self.ui.spin_similarity.setValue(config.post_processing.similarity_threshold)

        if self.ui.chk_keywords.isEnabled():
            self.ui.chk_keywords.setChecked(config.post_processing.use_keywords)
        self.ui.edit_keywords.setText(config.post_processing.keywords)

        if self.ui.chk_rrf.isEnabled():
            self.ui.chk_rrf.setChecked(config.post_processing.use_rrf)

        # 6. Path 복원
        self.ui.edit_path.setText(config.source_path)