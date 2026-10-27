@echo off
call uv run pyuic6 -o mainwindow.py mainwindow.ui
if %errorlevel%==0 ( echo ui file compiled successful ) else ( echo ui file compiled fail )
pause