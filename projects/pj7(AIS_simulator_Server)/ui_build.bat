@echo off
call ..\env\env_pj7\Scripts\activate
call pyuic6 -o Server_UI.py .\ui\Server.ui
if %errorlevel%==0 ( echo ui file compiled successful ) else ( echo ui file compiled fail )
pause