local os = require("os")
                    
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
    
    print("Проверка Python и необходимых модулей...")
    local python_check, python_error = safe_execute("python3 -c 'import hid, serial, websockets' 2>&1")
    
    if python_error then
        print("Ошибка: Не установлены необходимые Python модули")
        print("Установите их командой: pip3 install pyhidapi pyserial websockets")
        return false
    end
    
    print("Проверка WebSocket сервера...")
    local server_check, server_error = safe_execute("ps aux | grep 'python3 main.py' | grep -v grep > /dev/null 2>&1")
    
    if server_error then
        print("Ошибка: WebSocket сервер не запущен")
        print("Запустите сервер командой: python3 main.py")
        return false
    end
    
    print("Проверка наличия скрипта ut803.py...")
    local file = io.open("bin/ut803.py", "r")
    if not file then
        print("Ошибка: Файл ut803.py не найден")
        return false
    end
    file:close()

    local cmd = string.format("python3 ut803.py --measurement_time %d --force-save", params.measurement_time)
    print("\nЗапуск теста мультиметра на " .. params.measurement_time .. " секунд...")
    print("Команда:", cmd)
    
    print("Ожидание 1 секунды перед запуском...")
    os.execute("sleep 1")
    
    local output, error = safe_execute(cmd)
    
    if error then
        print("Ошибка выполнения команды:", error)
        return false
    end

    print("Результат выполнения теста:")
    print(output)
    return true
end

io.stdout:setvbuf('no')

local function run_parallel_tests()
    print("\n=== START PARALLEL TEST SCENARIO ===")

    require "contrib/scenario"

    local osc_cmd = string.format("python3 -u bin/rigol_reader.py --samples %d --interval %.2f --force-save", global_osc_samples, global_osc_interval_sec)
    local osc_handle = io.popen(osc_cmd)

    local mult_cmd = string.format("python3 -u bin/ut803.py --measurement_time %d --force-save", global_mult_time_sec)
    local mult_handle = io.popen(mult_cmd)

    local osc_count = 0
    local mult_count = 0
    local osc_total = global_osc_samples
    local mult_total = global_mult_time_sec
    local last_progress = 0

    while true do
        local osc_line = osc_handle:read("*l")
        local mult_line = mult_handle:read("*l")
        if osc_line then
            print("[OSC] " .. osc_line)
            if osc_line:find("Получение выборки") then
                osc_count = osc_count + 1
            end
        end
        if mult_line then
            print("[MULT] " .. mult_line)
            if mult_line:find("Измерение") or mult_line:find("Measurement") then
                mult_count = mult_count + 1
            end
        end
        local progress = math.floor((math.max(osc_count / osc_total, mult_count / mult_total)) * 100)
        if progress > last_progress and progress <= 100 then
            print(string.format("[PROGRESS] %d%%", progress))
            last_progress = progress
        end
        if not osc_line and not mult_line then break end
    end

    osc_handle:close()
    mult_handle:close()
    print("\n=== PARALLEL TEST SCENARIO FINISHED ===")
end

print("Запуск тестового сценария...")
local status, err = pcall(run_parallel_tests)
if not status then
    print("Ошибка выполнения сценария:", err)
    os.exit(1)
end

print("Сценарий успешно завершен")
os.exit(0)

return {
    firt = safe_execute(),
}
