# LVGL + MicroPython on ESP32-WROVER with ILI9488 and FT6236

A working MicroPython + LVGL setup for the **ESP32-WROVER-E-N8R8** with an ILI9488 SPI display and FT6236 capacitive touch controller. Includes a pre-built firmware image and all required Python driver files.

## Hardware

| Component | Details |
|---|---|
| MCU | ESP32-WROVER-E-N8R8 (240 MHz, 8 MB flash, 8 MB PSRAM) |
| Display | ILI9488, 320×480, SPI |
| Touch | FT6236 (FT6x36 family), I2C, address 0x38 |

### Wiring

| Signal | GPIO |
|---|---|
| SPI CLK | 5 |
| SPI MOSI | 18 |
| SPI MISO | 19 |
| LCD DC | 2 |
| LCD CS | 15 |
| LCD RST | 4 |
| Backlight | 32 |
| I2C SDA | 23 |
| I2C SCL | 22 |

## Repository contents

| File | Description |
|---|---|
| `firmware.bin` | Pre-built MicroPython + LVGL firmware |
| `main.py` | Demo: dark blue screen, label, and touchable button |
| `ili9488.py` | ILI9488 display driver (18-bit SPI, BGR panel correction, viper-optimized) |
| `st77xx.py` | ST77xx base driver (from lv_micropython) |
| `ft6x36.py` | FT6x36 touch driver (from lv_micropython) |
| `lv_utils.py` | LVGL event loop helper (from lv_micropython, patched for LVGL 9.x) |
| `boot.py` | Default MicroPython boot file |

## Flashing the firmware

Install [esptool](https://github.com/espressif/esptool) if you don't have it:

```bash
pip install esptool
```

Erase flash, then write the firmware (adjust the port as needed):

```bash
esptool.py --chip esp32 --port /dev/ttyUSB0 erase_flash

esptool.py --chip esp32 --port /dev/ttyUSB0 --baud 460800 \
  write_flash -z 0x1000 firmware.bin
```

On Windows, replace `/dev/ttyUSB0` with `COM3` (or whichever COM port your board appears on).

## Uploading the Python files

Install [mpremote](https://docs.micropython.org/en/latest/reference/mpremote.html):

```bash
pip install mpremote
```

Upload all files:

```bash
mpremote connect <port> cp main.py ft6x36.py ili9488.py lv_utils.py st77xx.py boot.py :
```

Then **hard reset** the board using the EN button. Do not use Ctrl+D (soft reset) — it leaves hardware timers running and causes a crash on the next init.

## Firmware build parameters

Built from [lv_micropython](https://github.com/lvgl/lv_micropython) with:

```
BOARD=ESP32_GENERIC
BOARD_VARIANT=SPIRAM
LV_CFLAGS="-DLV_COLOR_DEPTH=16"
```

LVGL version: 9.x. MicroPython version: see `uos.uname()` on the device.

## ILI9488 quirks (hard-won)

If you are adapting this for a similar project, be aware of three non-obvious issues with the ILI9488 over SPI:

**1. 16-bit mode (COLMOD=0x55) does not work over SPI.**  
The ILI9488 silently accepts COLMOD=0x55 but the display RAM write does not render. You must use 18-bit mode (COLMOD=0x66, 3 bytes per pixel). This driver handles the RGB565→RGB666 expansion automatically.

**2. Physical BGR panel stripe order.**  
Most ILI9488 breakout modules have a BGR-ordered color panel. Without correction, red and blue are swapped (dark blue backgrounds appear brown). This driver sends pixels in BGR byte order to compensate.

**3. LVGL 9.x API change.**  
`lv.task_handler()` was renamed to `lv.timer_handler()` in LVGL 9.x. The stock `lv_utils.py` from lv_micropython still uses the old name, causing a silent failure (exception is caught and swallowed) where LVGL never renders. The `lv_utils.py` in this repo is patched.

## License

Driver files (`st77xx.py`, `ft6x36.py`, `lv_utils.py`) are from the [lv_micropython](https://github.com/lvgl/lv_micropython) project and retain their original MIT licenses. All other files in this repository are MIT licensed.
