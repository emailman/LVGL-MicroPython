import time
from machine import SPI, Pin
import lvgl as lv
import ili9488
import ft6x36

PIN_SPI_CLK  = 5
PIN_SPI_MOSI = 18
PIN_SPI_MISO = 19
PIN_LCD_DC   = 2
PIN_LCD_CS   = 15
PIN_LCD_RST  = 4
PIN_LCD_BL   = 32
PIN_I2C_SDA  = 23
PIN_I2C_SCL  = 22

lv.init()

spi = SPI(2, baudrate=20_000_000,
          sck=Pin(PIN_SPI_CLK), mosi=Pin(PIN_SPI_MOSI), miso=Pin(PIN_SPI_MISO))

display = ili9488.Ili9488(
    spi=spi,
    cs=PIN_LCD_CS, dc=PIN_LCD_DC, rst=PIN_LCD_RST,
    bl=PIN_LCD_BL,
    rot=ili9488.ILI9488_PORTRAIT,
    factor=8,
)
display.set_backlight(100)

touch = ft6x36.ft6x36(i2c_dev=0, sda=PIN_I2C_SDA, scl=PIN_I2C_SCL, freq=400_000)

scr = lv.screen_active()
scr.set_style_bg_color(lv.color_hex(0x003080), lv.PART.MAIN)
lbl = lv.label(scr)
lbl.set_text('LVGL on ESP32\nILI9488 + FT6236')
lbl.set_style_text_color(lv.color_hex(0xFFFFFF), lv.PART.MAIN)
lbl.align(lv.ALIGN.CENTER, 0, -40)

btn = lv.button(scr)
btn.align(lv.ALIGN.CENTER, 0, 40)
btn.set_size(160, 50)
btn_lbl = lv.label(btn)
btn_lbl.set_text('Touch me!')
btn_lbl.center()
btn.add_event_cb(lambda e: btn_lbl.set_text('Touched!'), lv.EVENT.CLICKED, None)

while True:
    time.sleep_ms(lv.timer_handler())
