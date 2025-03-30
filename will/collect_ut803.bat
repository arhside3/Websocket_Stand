@echo off
REM Скрипт для сбора данных с мультиметра UT803

echo Запуск сбора данных с мультиметра UT803
echo Для остановки нажмите Ctrl+C

REM Получаем путь к TEMP директории
set TEMP_DIR=%TEMP%
if "%TEMP_DIR%"=="" set TEMP_DIR=%CD%

echo Данные будут сохранены в %TEMP_DIR%\ut803.txt

python ut803_data_reader.py -m plot -f "%TEMP_DIR%\ut803.txt"

echo Сбор данных завершен.
pause