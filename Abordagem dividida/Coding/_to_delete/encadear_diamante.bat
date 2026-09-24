@echo off
cd /d "%~dp0"
title Encadeamento Ouro -> Diamante
echo ==============================================================
echo  Aguardando a coleta de OURO terminar para iniciar DIAMANTE.
echo  Esta janela pode ficar minimizada. Nao selecione texto nela.
echo ==============================================================
echo.
powercfg /change standby-timeout-ac 0
:wait
timeout /t 10 /nobreak >nul
tasklist /fi "imagename eq python.exe" 2>nul | find /i "python.exe" >nul
if not errorlevel 1 goto wait
echo Coleta de Ouro encerrada. Cancelando o desligamento agendado...
for /l %%i in (1,1,8) do (
  shutdown /a >nul 2>&1
  timeout /t 5 /nobreak >nul
)
echo Iniciando coleta de DIAMANTE... acompanhe por collect_diamante_log.txt
py -u collect_elo.py DIAMOND 2500 180 >> collect_diamante_log.txt 2>&1
if errorlevel 2 goto badkey
echo.
echo Coleta de Diamante encerrada. Dados em dataset\matches_DIAMOND.csv
echo O PC desliga em 2 minutos. Para cancelar, execute cancelar_desligamento.bat
shutdown /s /t 120 /c "Coletas do TCC encerradas - desligando"
goto end
:badkey
echo.
echo  CHAVE DA API INVALIDA - o PC NAO sera desligado.
echo.
pause
:end
