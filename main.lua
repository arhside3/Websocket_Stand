local json = require("dkjson")
local os = require("os")

local config_file = "osc_config.json"
local pid_file = "python_process.pid"

local function show_menu()
    print("\n=== Управление осциллографом ===")
    print("1. Настроить параметры измерения")
    print("2. Запустить сбор данных")
    print("3. Остановить сбор данных")
    print("4. Просмотреть текущие настройки")
    print("5. Выход")
    io.write("Выберите действие: ")
    return tonumber(io.read("*line"))
end

local function configure_params()
    print("\n=== Настройка параметров ===")
    local params = {}
    
    io.write("Номер канала (1-4): ")
    params.channel = tonumber(io.read("*line")) or 1
    
    io.write("Вольт/деление (например 0.5): ")
    params.volts_per_div = tonumber(io.read("*line")) or 1.0
    
    io.write("Время/деление (например 100us): ")
    params.time_per_div = io.read("*line") or "100us"
    
    io.write("Уровень триггера (В): ")
    params.trigger_level = tonumber(io.read("*line")) or 1.0
    
    io.write("Интервал измерений (сек): ")
    params.interval = tonumber(io.read("*line")) or 2.0
    
    local file = io.open(config_file, "w")
    if file then
        file:write(json.encode(params, {indent = true}))
        file:close()
        print("\nНастройки сохранены в "..config_file)
    else
        print("Ошибка сохранения настроек!")
    end
end

local function is_process_running()
    return os.execute("pgrep -f test_rigol_linux.py > /dev/null") == 0
end

local function start_acquisition()
    if is_process_running() then
        print("\nСбор данных уже запущен!")
        return
    end
    
    -- Удаление старого файла pid, если он существует
    os.execute("rm -f " .. pid_file)

    local cmd = "python3 test_rigol_linux.py & echo $! > " .. pid_file
    local status = os.execute(cmd)
    if status == 0 then
        print("\nЗапуск сбора данных...")
    else
        print("\nОшибка запуска сбора данных!")
    end
end

local function stop_acquisition()
    local file = io.open(pid_file, "r")
    if file then
        local pid = file:read("*a")
        file:close()
        
        -- Принудительное завершение процесса
        local status = os.execute("kill -9 " .. pid)
        if status == 0 then
            os.remove(pid_file)
            print("\nСбор данных остановлен.")
        else
            print("\nОшибка остановки сбора данных!")
        end
    else
        print("\nНет активного процесса сбора данных")
    end
end

local function view_config()
    print("\nТекущие настройки:")
    local file = io.open(config_file, "r")
    if file then
        print(file:read("*a"))
        file:close()
    else
        print("Настройки не найдены")
    end
end

local function main_loop()
    while true do
        local choice = show_menu()
        
        if choice == 1 then
            configure_params()
        elseif choice == 2 then
            start_acquisition()
        elseif choice == 3 then
            stop_acquisition()
        elseif choice == 4 then
            view_config()
        elseif choice == 5 then
            -- Остановка сбора данных перед выходом
            stop_acquisition()
            print("\nВыход из программы...")
            os.exit()
        else
            print("\nНеверный выбор! Попробуйте снова.")
        end
    end
end

main_loop()