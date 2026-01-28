# app_writer.py (프로세스 A: Streamlit 기록자)
import streamlit as st

DATA_FILE = "data.txt"

st.title("프로세스 A: 값 누적 기록 (Streamlit)")

def append_value_to_file(value):
    try:
        with open(DATA_FILE, "a", encoding="utf-8") as f:
            f.write(str(value) + "\n")
        st.success(f"값 '{value}'가 파일에 기록되었습니다.")
    except IOError as e:
        st.error(f"파일 쓰기 오류: {e}")

number_input = st.number_input("1자리 정수를 입력하세요 (0-9)", min_value=0, max_value=9, step=1)

if st.button("파일에 값 추가"):
    if number_input is not None:
        append_value_to_file(int(number_input))
