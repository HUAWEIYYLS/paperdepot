@echo off
chcp 65001 >nul
cd /d "%~dp0"
if "%~1"=="" (
  echo 把一个或多个 PDF 拖到这个 .cmd 上即可导入。
  echo 库路径由 config\paperdepot.local.json 或 PAPERDEPOT_VAULT 决定。
  echo.
  pause
  exit /b 1
)
python "%~dp0tools\ingest.py" %*
if errorlevel 1 pause
echo.
echo 重建索引...
python "%~dp0tools\make_index.py"
echo.
echo 完成，按任意键关闭。
pause >nul
