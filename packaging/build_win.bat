@echo off
chcp 65001 >nul
REM 在 Windows 上构建 RewardHub.exe（onedir）。从仓库根目录运行：packaging\build_win.bat
REM chcp 65001：让 cmd 用 UTF-8 解释本文件里的中文（echo / 中文路径），否则默认代码页会乱码 / 复制失败。
setlocal enableextensions
cd /d "%~dp0\.."

python -m pip install --upgrade pip
python -m pip install pyinstaller playwright openpyxl
if errorlevel 1 exit /b 1

REM 不需要 chromium 内核（运行时驱动系统 Edge），故不执行 playwright install chromium。
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
python -m PyInstaller packaging\reward_hub.spec --noconfirm
if errorlevel 1 exit /b 1

echo Build done: dist\RewardHub\RewardHub.exe
REM 与 Mac 包结构一致：重命名输出目录为 RewardHub-win，放入随包说明，再 zip。
if exist "dist\RewardHub-win" rmdir /s /q "dist\RewardHub-win"
move "dist\RewardHub" "dist\RewardHub-win" >nul

REM 复制 packaging 下的说明 .txt（用通配符从目录取真实文件名，避免在批处理里硬写中文路径被代码页解错）。
for %%F in ("packaging\*.txt") do copy /Y "%%~fF" "dist\RewardHub-win\" >nul

REM 优先用 pwsh(PowerShell 7，UTF-8 正确处理 zip 内中文条目名)，无则回退 Windows PowerShell 5.1。
set "PS=powershell"
where pwsh >nul 2>nul && set "PS=pwsh"
%PS% -NoProfile -Command "Compress-Archive -Path 'dist\RewardHub-win' -DestinationPath 'dist\RewardHub-win.zip' -Force"
if errorlevel 1 exit /b 1
echo Package: dist\RewardHub-win.zip
endlocal
