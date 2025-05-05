local os = require("os")
local socket = require("socket")
local json = require("json")

local test_scenario = {
    {
        device = "oscilloscope",
        params = {
            channel = 1,
            volts_per_div = 0.5,
            time_per_div = "100us",
            trigger_level = 1.0
        },
        duration = 1
    },
    {
        device = "multimeter",
        params = {
            measurement_time = 10
        },
        duration = 1
    }
}

local function run_oscilloscope_test(params)
    local cmd = string.format(
        "python3 test_rigol_linux.py --channel %d --volts_per_div %f --time_per_div %s --trigger_level %f",
        params.channel, params.volts_per_div, params.time_per_div, params.trigger_level
    )
    print("\nЗапуск теста осциллографа...")
    print(cmd)  -- Явно выводим команду
    os.execute(cmd)
end

local function run_multimeter_test(params)
    local cmd = string.format("python3 ut803_linux.py --measurement_time %d", params.measurement_time)
    print("\nЗапуск теста мультиметра...")
    print(cmd)  -- Явно выводим команду
    os.execute(cmd)
end

local function run_test_scenario()
    print("\n=== Запуск автоматического тестового сценария ===")
    
    for _, test in ipairs(test_scenario) do
        if test.device == "oscilloscope" then
            run_oscilloscope_test(test.params)
            os.execute("sleep " .. test.duration)
        elseif test.device == "multimeter" then
            run_multimeter_test(test.params)
            os.execute("sleep " .. test.duration)
        end
    end
    
    print("\nТестовый сценарий завершен!")
end

-- Немедленно запускаем тестовый сценарий без ожидания ввода
run_test_scenario()