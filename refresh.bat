@echo off
REM High & Low: pull fresh prices, then publish to Vercel.
REM Run by hand, or hourly from Windows Task Scheduler (see README).
cd /d "%~dp0"
echo [%date% %time%] refresh started >> refresh.log
python scrape.py >> refresh.log 2>&1
if errorlevel 1 (
  echo [%date% %time%] scrape failed, NOT deploying >> refresh.log
  exit /b 1
)
call vercel deploy --prod --yes --cwd site >> refresh.log 2>&1
if errorlevel 1 (
  echo [%date% %time%] deploy failed >> refresh.log
  exit /b 1
)
echo [%date% %time%] refresh done >> refresh.log
