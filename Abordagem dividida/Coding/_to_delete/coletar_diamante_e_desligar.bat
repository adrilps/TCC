@echo off
cd /d "%~dp0"
echo ==========================================================
echo  Coleta de partidas do elo DIAMANTE (comparacao entre elos)
echo  Pode minimizar. NAO selecione texto nesta janela.
echo ==========================================================
echo.
powercfg /change standby-timeout-ac 0
echo Iniciando... acompanhe por collect_diamante_log.txt
py -u collect_elo.py DIAMOND 2500 180 >> collect_diamante_log.txt 2>&1
if errorlevel 2 goto badkey
echo.
echo Coleta encerrada e dados salvos em dataset\matches_DIAMOND.csv
echo O PC desliga em 2 minutos. Para cancelar: shutdown /a
shutdown /s /t 120 /c "Coleta Diamante encerrada - desligando"
goto end
:badkey
echo.
echo  CHAVE DA API INVALIDA - o PC NAO sera desligado.
echo.
pause
:end
