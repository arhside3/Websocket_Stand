@echo off
REM Скрипт для построения графика напряжения с мультиметра UT803

echo Запуск построения графика напряжения...

REM Получаем путь к TEMP директории
set TEMP_DIR=%TEMP%
if "%TEMP_DIR%"=="" set TEMP_DIR=%CD%

REM Создаём временный gnuplot скрипт
echo system("type %TEMP_DIR%\ut803.txt | findstr напряжение | findstr /v перегрузка > %TEMP_DIR%\voltage.txt") > %TEMP_DIR%\voltage_plot.gp
echo set title "Мультиметр UT803 - Измерение напряжения" >> %TEMP_DIR%\voltage_plot.gp
echo set xlabel "Время (точки измерения)" >> %TEMP_DIR%\voltage_plot.gp
echo set ylabel "Напряжение (В)" >> %TEMP_DIR%\voltage_plot.gp
echo set grid >> %TEMP_DIR%\voltage_plot.gp
echo plot "%TEMP_DIR%\voltage.txt" using 0:2 with lines title "Напряжение" >> %TEMP_DIR%\voltage_plot.gp
echo pause -1 "Нажмите Enter для закрытия графика" >> %TEMP_DIR%\voltage_plot.gp

REM Запускаем gnuplot
gnuplot %TEMP_DIR%\voltage_plot.gp

echo График закрыт.