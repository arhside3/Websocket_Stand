local os = require("os")

-- Функция для безопасного выполнения команды
local function safe_execute(cmd)
    print("Выполнение команды:", cmd)
    local handle = io.popen(cmd .. " 2>&1")
    if not handle then
        print("Ошибка: Не удалось выполнить команду")
        return nil, "Failed to execute command"
    end
    
    local output = handle:read("*a")
    local success, reason, code = handle:close()
    
    if not success then
        print("Ошибка выполнения команды:", reason or "Unknown error")
        return nil, reason or "Command failed"
    end
    
    print("Результат выполнения команды:", output)
    return output, nil
end

local function run_multimeter_test(params)
    print("Начало выполнения теста мультиметра")
    
    -- Проверяем наличие Python и необходимых модулей
    print("Проверка Python и необходимых модулей...")
    local python_check, python_error = safe_execute("python3 -c 'import hid, serial, websockets' 2>&1")
    
    if python_error then
        print("Ошибка: Не установлены необходимые Python модули")
        print("Установите их командой: pip3 install pyhidapi pyserial websockets")
        return false
    end
    
    -- Проверяем, запущен ли WebSocket сервер
    print("Проверка WebSocket сервера...")
    local server_check, server_error = safe_execute("ps aux | grep 'python3 main.py' | grep -v grep > /dev/null 2>&1")
    
    if server_error then
        print("Ошибка: WebSocket сервер не запущен")
        print("Запустите сервер командой: python3 main.py")
        return false
    end
    
    -- Проверяем наличие скрипта ut803_linux.py
    print("Проверка наличия скрипта ut803_linux.py...")
    local file = io.open("ut803_linux.py", "r")
    if not file then
        print("Ошибка: Файл ut803_linux.py не найден")
        return false
    end
    file:close()
    
    -- Запускаем мультиметр с правильным путем к Python
    local cmd = string.format("python3 ut803_linux.py --measurement_time %d", params.measurement_time)
    print("\nЗапуск теста мультиметра на " .. params.measurement_time .. " секунд...")
    print("Команда:", cmd)
    
    -- Уменьшаем задержку перед запуском мультиметра
    print("Ожидание 1 секунды перед запуском...")
    os.execute("sleep 1")
    
    -- Запускаем процесс и получаем его вывод
    local output, error = safe_execute(cmd)
    
    if error then
        print("Ошибка выполнения команды:", error)
        return false
    end
    
    -- Выводим результат
    print("Результат выполнения теста:")
    print(output)
    return true
end

io.stdout:setvbuf('no')

local function run_test_scenario()
    print("\n=== START TEST SCENARIO ===")

    local cmd = "python test_rigol.py --samples 10 --interval 1.0 --force-save"
    print("\nSTART TEST OF OSCILLOSCOPE...")
    print(cmd)
    os.execute(cmd)
    
    local cmd = string.format("python3 -u ut803_linux.py --measurement_time %d", 10)
    print("\nSTART TEST OF MULTIMETER...")
    print(cmd)
    local handle = io.popen(cmd)
    if handle then
        for line in handle:lines() do
            print(line)
        end
        handle:close()
    end
    print("\nSTART TEST SCENARIO FINISHED")
end

-- Запускаем сценарий с обработкой ошибок
print("Запуск тестового сценария...")
local status, err = pcall(run_test_scenario)
if not status then
    print("Ошибка выполнения сценария:", err)
    os.exit(1)
end

print("Сценарий успешно завершен")
os.exit(0)