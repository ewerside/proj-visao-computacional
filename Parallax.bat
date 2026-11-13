@echo off
rem Parallax: abre o menu do projeto. Dois cliques neste arquivo.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Ambiente nao encontrado. Rode antes, nesta pasta:
  echo     py -m venv .venv
  echo     .venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)
".venv\Scripts\python.exe" head_coupled\parallax.py
if errorlevel 1 pause
