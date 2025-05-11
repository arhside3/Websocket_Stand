local os = require("os")


local function run_test_scenario()
    print("\n=== START TEST SCENARIO ===")

    local cmd = "python test_rigol.py --samples 10 --interval 1.0 --force-save"
    print(cmd)
    os.execute(cmd)
    print("Oscilloscope data collection completed")

    local cmd = string.format("python ut803_linux.py --measurement_time %d", 10)
    print("\nSTART TEST OF MULTIMETER...")
    print(cmd)
    os.execute(cmd)

    print("\nSTART TEST SCENARIO FINISHED")
end

run_test_scenario()