@echo off
REM Otel Foto Sistemi - backend sunucusunu baslatir.
REM Bu dosyaya cift tiklayarak VEYA terminalde "basla.bat" yazarak calistirabilirsin.
REM Nerede oldugundan bagimsiz calisir (kendi klasorunu bulur).

cd /d "%~dp0"
echo ============================================
echo  Otel Foto Sistemi - backend baslatiliyor...
echo  Tarayicidan ac: http://localhost:8000/docs
echo  Durdurmak icin: Ctrl + C
echo ============================================
echo.
"%~dp0..\venv\Scripts\python.exe" -m uvicorn app.main:app --reload
pause
