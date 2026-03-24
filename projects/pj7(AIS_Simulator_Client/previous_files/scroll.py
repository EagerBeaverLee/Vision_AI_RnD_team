import streamlit as st
import streamlit.components.v1 as components

# 1. 자동 스크롤 함수 정의
def auto_scroll(px_value):
    # 세션 상태를 확인하여 이미 스크롤을 수행했는지 체크
    if "is_scrolled" not in st.session_state:
        st.session_state.is_scrolled = False

    if not st.session_state.is_scrolled:
        # JavaScript 주입: 부모 창(parent)을 px_value만큼 스크롤
        js_code = f"""
        <script>
            setTimeout(function() {{
                window.parent.scrollTo({{
                    top: {px_value},
                    behavior: 'auto' // 부드럽게 내려가고 싶으면 'smooth', 바로 가고 싶으면 'auto'
                }});
            }}, 5000); // 페이지 렌더링 시간을 고려해 0.5초 뒤에 실행
        </script>
        """
        components.html(js_code, height=0)
        st.session_state.is_scrolled = True # 실행 완료 표시

# --- 앱 레이아웃 ---
st.title("🚀 자동 스크롤 테스트")

# 상단에 긴 공간 (스크롤 효과 확인용)
for i in range(20):
    st.write(f"상단 콘텐츠 줄 {i+1}")

st.divider()
st.subheader("📍 여기가 자동 스크롤 목표 지점입니다!")

for i in range(30):
    st.write(f"하단 콘텐츠 줄 {i+1}")

# 2. 실행 (예: 500px만큼 자동으로 내리기)
auto_scroll(4000)