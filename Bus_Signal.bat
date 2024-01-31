@echo off

:writeNew

:noload
echo ================ NO LOAD ==================
set /P barcode=Enter barcode:
py Test.py --flag "0" --barcode "%barcode%"
if %errorlevel% equ 1 (goto noload)

:load
echo ================ LOAD ==================
set /P barcode=Enter barcode:
py Test.py --flag "1" --barcode "%barcode%"
if %errorlevel% equ 1 (goto load)

:overload
echo ================ OVER LOAD ==================
set /P barcode=Enter barcode:
py Test.py --flag "2" --barcode "%barcode%"
if %errorlevel% equ 1 (goto overload)

goto writeNew
