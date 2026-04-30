import time
import random
from machine import SPI, Pin
import lvgl as lv
import ili9488
import ft6x36

# --- Hardware ---
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
    spi=spi, cs=PIN_LCD_CS, dc=PIN_LCD_DC, rst=PIN_LCD_RST,
    bl=PIN_LCD_BL, rot=ili9488.ILI9488_PORTRAIT, factor=8,
)
display.set_backlight(100)

touch = ft6x36.ft6x36(i2c_dev=0, sda=PIN_I2C_SDA, scl=PIN_I2C_SCL, freq=400_000)

# --- Simon colors: dim / bright for Red, Green, Blue, Yellow ---
DIM    = [0x882222, 0x228822, 0x222288, 0x888822]
BRIGHT = [0xFF4444, 0x44FF44, 0x4444FF, 0xFFFF44]

# --- Game state ---
state      = "IDLE"   # IDLE | SHOWING | WAITING | GAME OVER
sequence   = []
player_idx = 0
show_idx   = 0
lit_phase  = True     # True = button is lit, False = inter-flash gap
high_score = 0

# --- Layout constants ---
MARGIN = 10
TOP    = 74
BTN_W  = (320 - 3 * MARGIN) // 2   # 145
BTN_H  = (480 - TOP - 3 * MARGIN) // 2  # 189

# --- UI ---
scr = lv.screen_active()
scr.set_style_bg_color(lv.color_hex(0x111111), lv.PART.MAIN)

status = lv.label(scr)
status.set_size(310, 68)
status.align(lv.ALIGN.TOP_MID, 0, 4)
status.set_style_text_color(lv.color_hex(0xFFFFFF), lv.PART.MAIN)
status.set_style_text_align(lv.TEXT_ALIGN.CENTER, lv.PART.MAIN)
status.set_text("Simon\nTap any button to start")

buttons = []
for i in range(4):
    row, col = divmod(i, 2)
    btn = lv.button(scr)
    btn.set_size(BTN_W, BTN_H)
    btn.set_pos(MARGIN + col * (BTN_W + MARGIN), TOP + MARGIN + row * (BTN_H + MARGIN))
    btn.set_style_bg_color(lv.color_hex(DIM[i]), lv.PART.MAIN)
    btn.set_style_bg_color(lv.color_hex(DIM[i]), lv.STATE.PRESSED)
    btn.set_style_radius(20, lv.PART.MAIN)
    btn.set_style_border_width(0, lv.PART.MAIN)
    btn.set_style_shadow_width(0, lv.PART.MAIN)
    buttons.append(btn)

# --- Helpers ---
def _light(idx):
    buttons[idx].set_style_bg_color(lv.color_hex(BRIGHT[idx]), lv.PART.MAIN)

def _dim(idx):
    buttons[idx].set_style_bg_color(lv.color_hex(DIM[idx]), lv.PART.MAIN)

def _dim_all():
    for _i in range(4):
        _dim(_i)

def _make_dim_cb(idx):
    def cb(timer):
        timer.delete()
        _dim(idx)
    return cb

# --- Sequence playback ---
def _show_step(timer):
    global show_idx, lit_phase, state, player_idx
    timer.delete()
    if lit_phase:
        _light(sequence[show_idx])
        lit_phase = False
        lv.timer_create(_show_step, 500, None)
    else:
        _dim(sequence[show_idx])
        show_idx += 1
        if show_idx >= len(sequence):
            state = "WAITING"
            player_idx = 0
            status.set_text("Round %d  —  Your turn!" % len(sequence))
        else:
            lit_phase = True
            lv.timer_create(_show_step, 350, None)

def _begin_show():
    global show_idx, lit_phase
    show_idx = 0
    lit_phase = True
    lv.timer_create(_show_step, 700, None)

def _next_round(timer):
    global sequence
    timer.delete()
    sequence.append(random.randint(0, 3))
    status.set_text("Round %d" % len(sequence))
    _begin_show()

# --- Game flow ---
def start_game():
    global sequence, player_idx, state
    _dim_all()
    sequence = [random.randint(0, 3)]
    player_idx = 0
    state = "SHOWING"
    status.set_text("Round 1")
    _begin_show()

def _game_over():
    global state, high_score
    state = "GAME OVER"
    score = len(sequence) - 1
    if score > high_score:
        high_score = score
    for _ in range(4):
        buttons[i].set_style_bg_color(lv.color_hex(0xFF2222), lv.PART.MAIN)
    status.set_text("Game Over!  Score: %d\nBest: %d   Tap to play again" % (score, high_score))

# --- Touch handler ---
def on_click(e):
    global player_idx, state
    if state in ("IDLE", "GAME OVER"):
        start_game()
        return
    if state != "WAITING":
        return

    _btn = e.get_target_obj()
    idx = buttons.index(_btn)

    _light(idx)
    lv.timer_create(_make_dim_cb(idx), 250, None)

    if idx == sequence[player_idx]:
        player_idx += 1
        if player_idx >= len(sequence):
            state = "SHOWING"   # block further input while transitioning
            lv.timer_create(_next_round, 900, None)
    else:
        _game_over()

for btn in buttons:
    btn.add_event_cb(on_click, lv.EVENT.CLICKED, None)

# --- Event loop ---
while True:
    time.sleep_ms(lv.timer_handler())