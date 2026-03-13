@echo off
call ..\env\env_pj7\Scripts\activate
call pyuic6 -o mainwindow.py .\ui\mainwindow.ui
if %errorlevel%==0 ( echo ui file compiled successful ) else ( echo ui file compiled fail )
pause