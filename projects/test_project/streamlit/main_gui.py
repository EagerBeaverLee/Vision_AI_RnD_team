# main_gui_processor.py (프로세스 B: 독립 실행형 GUI)
import tkinter as tk
from tkinter import messagebox
import os
import time

DATA_FILE = "data.txt"

def process_latest_value():
    """파일에서 가장 마지막에 기록된 값만 가져와 처리하는 함수"""
    if not os.path.exists(DATA_FILE):
        return "파일이 존재하지 않습니다."

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            if lines:
                # 마지막 줄의 공백/줄바꿈 제거
                latest_value_str = lines[-1].strip() 
                latest_value = int(latest_value_str)
                
                result = f"[{time.strftime('%H:%M:%S')}] 최신 값: {latest_value}"
                # 실제 B 프로세서의 처리 로직은 여기에 위치
                # 예: run_my_function(latest_value)
                return result
            else:
                return "파일에 기록된 값이 없습니다."
    except (IOError, ValueError) as e:
        return f"오류 발생: {e}"

def on_confirm_button_click():
    """GUI 버튼 클릭 시 실행될 핸들러"""
    result_message = process_latest_value()
    # 결과를 메시지 박스로 표시
    messagebox.showinfo("처리 결과", result_message)
    # 텍스트 라벨 업데이트
    status_label.config(text=f"마지막 확인 시각: {time.strftime('%H:%M:%S')}")


# --- Tkinter GUI 설정 ---
root = tk.Tk()
root.title("프로세스 B: Python GUI 처리기")
root.geometry("400x150")

label = tk.Label(root, text=".txt 파일의 최신 내용을 확인합니다.")
label.pack(pady=10)

confirm_button = tk.Button(root, text="확인 버튼 (최신 값 읽기)", command=on_confirm_button_click)
confirm_button.pack(pady=20)

status_label = tk.Label(root, text="대기 중...", fg="blue")
status_label.pack(pady=10)

# GUI 이벤트 루프 시작
if __name__ == "__main__":
    root.mainloop()
