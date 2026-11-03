@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo  论文库 · 生成手机离线阅读版
echo ============================================
echo.

if not "%~1"=="" (
  python tools\make_mobile_reader.py --vault "%~1" --out "%~dp0cache\mobile"
) else (
  python tools\make_mobile_reader.py --out "%~dp0cache\mobile"
)

if errorlevel 1 (
  echo.
  echo 生成失败，请查看上面的报错。
  pause
  exit /b 1
)

echo.
echo 输出目录：%~dp0cache\mobile
echo 把这个目录里的 epub / docx / pdf 复制到「华为云盘」，手机下载后打开即可。
echo.
start "" "%~dp0cache\mobile"
pause
