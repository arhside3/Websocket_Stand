local os = require("os")
local socket = require("socket")
local json = require("json")

local function show_menu()
    print("\n=== Выбор устройства ===")
    print("1. Осциллограф Rigol")
    print("2. Мультиметр UT803")
    print("3. Выход")
    io.write("Выберите устройство: ")
    return tonumber(io.read("*line"))
end

local function show_oscilloscope_menu()
    print("\n=== Управление осциллографом ===")
    print("1. Настроить параметры и запустить сбор данных")
    print("2. Остановить сбор данных")
    print("3. Назад")
    io.write("Выберите действие: ")
    return tonumber(io.read("*line"))
end

local function show_multimeter_menu()
    print("\n=== Управление мультиметром UT803 ===")
    print("1. Настроить время измерения и запустить")
    print("2. Остановить сбор данных")
    print("3. Назад")
    io.write("Выберите действие: ")
    return tonumber(io.read("*line"))
end

local function get_oscilloscope_params()
    print("\n=== Настройка параметров осциллографа ===")
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

local function get_multimeter_time()
    print("\n=== Настройка времени измерения ===")
    io.write("Время измерения (в секундах): ")
    local time = tonumber(io.read("*line")) or 10
    return time
end

local function start_oscilloscope(params)
    local cmd = string.format(
        "python3 test_rigol_linux.py --channel %d --volts_per_div %f --time_per_div %s --trigger_level %f",
        params.channel, params.volts_per_div, params.time_per_div, params.trigger_level
    )
    os.execute(cmd)
    print("\nЗапуск сбора данных с осциллографа...")
end

local function start_multimeter()
    local time = get_multimeter_time()
    local cmd = string.format("python3 ut803_linux.py --measurement_time %d", time)
    os.execute(cmd)
    print("\nЗапуск сбора данных с мультиметра...")
end

local function stop_oscilloscope()
    os.execute("pkill -f test_rigol_linux.py")
    print("\nСбор данных с осциллографа остановлен.")
end

local function stop_multimeter()
    os.execute("pkill -f ut803_linux.py")
    print("\nСбор данных с мультиметра остановлен.")
end

local function oscilloscope_loop()
    while true do
        local choice = show_oscilloscope_menu()
        
        if choice == 1 then
            local params = get_oscilloscope_params()
            start_oscilloscope(params)
        elseif choice == 2 then
            stop_oscilloscope()
        elseif choice == 3 then
            return
        else
            print("\nНеверный выбор! Попробуйте снова.")
        end
    end
end

local function multimeter_loop()
    while true do
        local choice = show_multimeter_menu()
        
        if choice == 1 then
            start_multimeter()
        elseif choice == 2 then
            stop_multimeter()
        elseif choice == 3 then
            return
        else
            print("\nНеверный выбор! Попробуйте снова.")
        end
    end
end

local function main_loop()
    while true do
        local choice = show_menu()
        
        if choice == 1 then
            oscilloscope_loop()
        elseif choice == 2 then
            multimeter_loop()
        elseif choice == 3 then
            print("\nВыход из программы...")
            os.exit()
        else
            print("\nНеверный выбор! Попробуйте снова.")
        end
    end
end

main_loop()