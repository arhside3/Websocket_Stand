local os = require("os")

local function show_menu()
    print("\n=== Управление осциллографом ===")
    print("1. Настроить параметры и запустить сбор данных")
    print("2. Остановить сбор данных")
    print("3. Выход")
    io.write("Выберите действие: ")
    return tonumber(io.read("*line"))
end

local function get_params()
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
    
    return params
end

local function start_acquisition(params)
    local cmd = string.format(
        "python3 test_rigol_linux.py --channel %d --volts_per_div %f --time_per_div %s --trigger_level %f",
        params.channel, params.volts_per_div, params.time_per_div, params.trigger_level
    )
    os.execute(cmd)
    print("\nЗапуск сбора данных...")
end

local function stop_acquisition()
    os.execute("pkill -f test_rigol_linux.py")
    print("\nСбор данных остановлен.")
end

local function main_loop()
    while true do
        local choice = show_menu()
        
        if choice == 1 then
            local params = get_params()
            start_acquisition(params)
        elseif choice == 2 then
            stop_acquisition()
        elseif choice == 3 then
            print("\nВыход из программы...")
            os.exit()
        else
            print("\nНеверный выбор! Попробуйте снова.")
        end
    end
end

main_loop()