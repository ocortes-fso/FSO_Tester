# FSO_Tester: Copilot Instructions

## Project Overview
FSO_Tester is a Raspberry Pi-based hardware testing suite for validating various components and communication protocols on a vehicle testing platform. Tests are organized as modular subcode scripts in `Subcodes/` that independently verify different hardware interfaces.

## Architecture & Components

### Test Structure
- **Location**: `Subcodes/` directory
- **Pattern**: Each test is a standalone Python script targeting a specific hardware component
- **Current tests**: Rear plate LED/switch, arm loom continuity, Lidar, magnetometer, Ethernet, Serial, CAN, SBUS, PWM, analog voltage, USB
- **Future tests**: ARM processor (pending external PCB)

### Key Dependencies
- **RPi.GPIO**: Hardware GPIO control for Raspberry Pi
- **PyMavlink**: MAVLink message handling (listed in main README)
- Standard Python libraries: `time` for delays and synchronization

## Coding Patterns

### GPIO & PWM Control Pattern
Tests use PWM (Pulse Width Modulation) for hardware control. Example from `Rear_switch_plate_test.py`:

```python
# 1. Setup GPIO with BCM mode
GPIO.setmode(GPIO.BCM)
GPIO.setup([RED_PIN, GREEN_PIN, BLUE_PIN], GPIO.OUT)

# 2. Create PWM objects with frequency (Hz)
pwm = GPIO.PWM(pin, frequency)
pwm.start(initial_duty_cycle)

# 3. Modify output via ChangeDutyCycle()
pwm.ChangeDutyCycle(new_value)

# 4. Always cleanup in finally block
finally:
    pwm.stop()
    GPIO.cleanup()
```

### Resource Cleanup
Always wrap GPIO operations in try-except-finally blocks with cleanup in the finally block to prevent resource leaks and hung processes.

## Hardware Interfaces Tested
- **GPIO/PWM**: RGB LED control (pins 0, 1, 7 via BCM naming)
- **Serial**: Body communication link
- **CAN**: Vehicle bus protocol
- **SBUS**: RC protocol
- **Analog**: Voltage measurement via ADC
- **Network**: Ethernet port validation
- **Sensors**: Lidar and magnetometer integration

## Development Workflow

### Running Tests
Tests execute on Raspberry Pi hardware. Each script runs independently:
```bash
python Subcodes/<test_name>.py
```

### Adding New Tests
1. Create new `.py` file in `Subcodes/` directory
2. Import required hardware libraries (RPi.GPIO, etc.)
3. Follow GPIO cleanup pattern shown in existing tests
4. Update `Subcodes/README.md` to document the new test
5. Commit with clear test name in message

### External Dependencies
Ensure Raspberry Pi environment has:
- RPi.GPIO library installed
- PyMavlink library for MAVLink tests
- Appropriate permissions for GPIO access (may require `sudo`)

## Important Notes
- **Hardware-specific**: All code targets Raspberry Pi 4/5 with GPIO support
- **Real-time constraints**: Tests control physical hardware; timing and cleanup are critical
- **Testing context**: Tests are validation/qualification scripts, not application code
- **Incomplete**: Repository documents planned tests in README (several future tests not yet implemented)
