@echo off
cd /d "%~dp0"
title Coleta DIAMANTE
echo ==============================================================
echo  Coleta de partidas do elo DIAMANTE (comparacao entre elos)
echo  Pode minimizar. NAO selecione texto nesta janela.
echo  O PC NAO sera desligado ao final.
echo ==============================================================
echo.
powercfg /change standby-timeout-ac 0
echo Iniciando... acompanhe por collect_diamante_log.txt
py -u collect_elo.py DIAMOND 2500 240 >> collect_diamante_log.txt 2>&1
if errorlevel 2 goto badkey
echo.
echo Coleta encerrada. Dados em dataset\matches_DIAMOND.csv
timeout /t 20 >nul
goto end
:badkey
echo.
echo  CHAVE DA API INVALIDA - verifique lol_pipeline\.env
echo.
pause
:end
