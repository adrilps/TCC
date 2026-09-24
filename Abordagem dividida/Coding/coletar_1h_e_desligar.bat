@echo off
cd /d "%~dp0"
echo ==========================================================
echo  Coleta de 60 minutos e desligamento automatico
echo  Pode minimizar esta janela. NAO selecione texto nela.
echo ==========================================================
echo.
powercfg /change standby-timeout-ac 0
echo Iniciando... acompanhe por collect_log.txt
py -u collect.py 40000 60 >> collect_log.txt 2>&1
if errorlevel 2 goto badkey
echo.
echo Coleta encerrada e dados salvos. O PC desliga em 2 minutos.
echo (Para cancelar: abra o Executar com Win+R e digite  shutdown /a )
shutdown /s /t 120 /c "Coleta do TCC encerrada - desligando"
goto end
:badkey
echo.
echo  CHAVE DA API INVALIDA - o PC NAO sera desligado.
echo.
pause
:end
