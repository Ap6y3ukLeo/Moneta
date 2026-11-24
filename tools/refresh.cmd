@echo off
chcp 65001 >nul
cd /d "%~dp0.."
python tools\realty_refresh.py --yandex %*
