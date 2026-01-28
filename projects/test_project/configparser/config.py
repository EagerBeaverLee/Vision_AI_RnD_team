import configparser
import os

# 1. ConfigParser 객체 생성
config = configparser.ConfigParser()

# 2. INI 파일 경로 설정
file_path = 'config.ini'

# 3. 파일이 있으면 읽고, 없으면 무시
# read() 메서드는 파일이 없어도 오류를 발생시키지 않음
config.read(file_path)

# 4. 'settings' 섹션에 값 설정
# 파일이 새로 생성되었거나 'settings' 섹션이 없으면 새로 추가됨
if 'settings' not in config:
    config['settings'] = {}

# 5. 값 추가 및 수정
# 'language' 키가 없으면 추가하고, 있으면 덮어씀
config['settings']['language'] = 'ko'
config['settings']['theme'] = 'dark'

# 6. 변경 내용을 파일에 다시 저장
# 파일이 없으면 새로 생성됨
with open(file_path, 'w') as configfile:
    config.write(configfile)

print(f"'{file_path}' 파일이 성공적으로 처리되었습니다.")