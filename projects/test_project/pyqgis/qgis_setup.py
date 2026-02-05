import os
import sys

def init_qgis_env():
    # [1] QGIS 설치 절대 경로 (사용자 환경 확인)
    QGIS_BASE = r"C:\Program Files\QGISQT6 3.44.6"

    # [2] DLL 경로 등록 (가장 먼저 실행하여 DLL 충돌 방지)
    dll_folders = [
        os.path.join(QGIS_BASE, "bin"),
        os.path.join(QGIS_BASE, "apps", "qgis-qt6", "bin"),
        os.path.join(QGIS_BASE, "apps", "Qt6", "bin")
    ]
    for folder in dll_folders:
        if os.path.exists(folder):
            os.add_dll_directory(folder)

    # [3] 라이브러리 경로 우선순위 설정 (QGIS 내장 패키지 참조)
    sys.path.insert(0, os.path.join(QGIS_BASE, "apps", "qgis-qt6", "python"))
    sys.path.insert(0, os.path.join(QGIS_BASE, "apps", "Python312", "Lib", "site-packages"))
 
    return QGIS_BASE