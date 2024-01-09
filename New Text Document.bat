@echo off

set /P channel=Enter channel:
set /P port=Enter port:
:writeNew
set /P barcode=Enter barcode:
py Test.py --channel "%channel%" --port "%port%"
goto writeNew