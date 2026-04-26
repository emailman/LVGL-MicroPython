# CLAUDE.md — Project context for Claude Code

## What this project is

A fully working MicroPython + LVGL 9.3.0 setup for the **ESP32-WROVER-E-N8R8** (8 MB flash, 8 MB PSRAM) with an ILI9488 SPI display (320×480) and FT6236 capacitive touch controller. The goal was to get LVGL rendering correctly with touch input.

## Hardware

- **MCU:** ESP32-WROVER-E-N8R8
- **Display:** ILI9488, 320×480, SPI (CLK=5, MOSI=18, MISO=19, DC=2, CS=15, RST=4, BL=32)
- **Touch:** FT6236 (FT6x36 family), I2C at 0x38 (SDA=23, SCL=22)

## File map

| File | Role |
|---|---|
| `main.py` | Entry point — inits display, touch, LVGL widgets, event loop |
| `ili9488.py` | ILI9488 driver (inherits from st77xx; overrides init, pixel format, flush) |
| `st77xx.py` | Base driver: hardware SPI layer (`St77xx_hw`) + LVGL integration (`St77xx_lvgl`) |
| `ft6x36.py` | FT6x36 touch driver from lv_micropython; registers with LVGL input system |
| `lv_utils.py` | LVGL event loop helper — patched: `lv.task_handler()` → `lv.timer_handler()` |
| `boot.py` | Default MicroPython boot (unchanged) |
| `firmware.bin` | Pre-built firmware (see build parameters below) |

## Development environment

- **WSL2** (Ubuntu 22.04) is used for building firmware and uploading files
- **Build tools in WSL2:** ESP-IDF v5.2.2 at `~/esp/esp-idf-v5.2.2/`; alias `get_idf` in `.bashrc`
- **lv_micropython source:** `~/projects/lv_micropython/` with all submodules
- **esptool and mpremote:** `~/.local/bin/`
- **Device ports:** `/dev/ttyACM0` for esptool flash, `/dev/ttyACM1` for mpremote REPL
- **usbipd-win:** `C:\Program Files\usbipd-win\usbipd.exe`, ESP32 is BUSID 1-9
- **Windows project path in WSL2:** `/mnt/c/Users/ericm/PycharmProjects/LVGL-MicroPython/`

## Firmware build parameters

```bash
source ~/esp/esp-idf-v5.2.2/export.sh   # or: get_idf
cd ~/projects/lv_micropython/ports/esp32
make BOARD=ESP32_GENERIC BOARD_VARIANT=SPIRAM LV_CFLAGS="-DLV_COLOR_DEPTH=16" -j$(nproc)
# Output: build-ESP32_GENERIC-SPIRAM/firmware.bin
```

## File upload workflow

```bash
# Copy a file — interrupts main.py cleanly, device stays in REPL
mpremote connect /dev/ttyACM1 cp /mnt/c/Users/ericm/PycharmProjects/LVGL-MicroPython/<file>.py :<file>.py

# After uploading: ALWAYS hard reset with EN button, not Ctrl+D
# Ctrl+D (soft reset) leaves hardware Timers alive → stale timer callback → IllegalInstruction crash
```

## Class hierarchy in the driver

```
St77xx_hw        — SPI bus, pin control, write_register(), blit(), set_window(), _run_seq()
  └─ Ili9488_hw  — ILI9488-specific: config_hw(), apply_rotation(), set_window(), clear()

St77xx_lvgl      — LVGL display_create(), draw buffers, event_loop, flush_cb registration
  └─ (mixed in)

Ili9488(Ili9488_hw, St77xx_lvgl)
  — overrides disp_drv_flush_cb() for 18-bit RGB666 conversion + BGR byte order
```

## Key technical issues resolved

### 1. LVGL 9.3.0 API rename
`lv.task_handler()` → `lv.timer_handler()` in LVGL 9.3.0. The old name silently throws
`AttributeError` which is caught by `lv_utils.py`'s exception handler, so LVGL never
gets its timer called and nothing renders. Fixed in `lv_utils.py` (2 places) and `main.py`.

### 2. ILI9488 16-bit SPI does not work
COLMOD=0x55 (16-bit) is accepted without error but the display RAM write is ignored.
Must use COLMOD=0x66 (18-bit RGB666, 3 bytes per pixel). The `disp_drv_flush_cb` override
in `Ili9488` handles RGB565→RGB666 expansion via a `@micropython.viper` native function.

### 3. ILI9488 panel has BGR stripe order
Without correction, red and blue are swapped (dark blue appears brown). Fixed by sending
pixels in BGR byte order (B first, R last) in both `disp_drv_flush_cb` and `clear()`.
No MADCTL change needed — the byte reordering in software is sufficient.

### 4. Soft-reset crash
Soft reboot (Ctrl+C / Ctrl+D) leaves hardware Timers running. On next `lv_utils.event_loop()`
init, the stale Timer callback fires → `IllegalInstruction` at garbage PC. Always hard reset
with the EN button between runs. After a crash the board auto-reboots and runs `main.py` cleanly.

### 5. Performance: viper pixel conversion
The RGB565→RGB666 conversion is done per-pixel. The `@micropython.viper` decorator compiles
`_rgb565_to_rgb666()` to native Xtensa machine code, giving ~10-50× speedup over a Python loop.
The function converts directly from LVGL's little-endian RGB565 format, skipping the
`rgb565_swap_func` pass entirely.

## LVGL 9.3.0 API notes

| Old (LVGL 8.x) | New (LVGL 9.3.0) |
|---|---|
| `lv.scr_act()` | `lv.screen_active()` |
| `lv.task_handler()` | `lv.timer_handler()` |
| `lv.btn()` | `lv.button()` |

Color depth confirmation: `lv.COLOR_FORMAT.NATIVE` should equal 18 (`LV_COLOR_FORMAT_RGB565`)
when firmware is built with `LV_COLOR_DEPTH=16`.
