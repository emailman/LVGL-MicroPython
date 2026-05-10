import network
import urequests
import utime
from machine import SPI, Pin
import lvgl as lv
import ili9488
import ft6x36

# --- WiFi credentials ---
WIFI_SSID = "blinky"
WIFI_PASSWORD = "flim314flam159"

# --- Pin assignments (ThingPulse ePulse Feather Wing v2.0.1) ---
PIN_SPI_CLK = 5
PIN_SPI_MOSI = 18
PIN_SPI_MISO = 19
PIN_LCD_DC = 2
PIN_LCD_CS = 15
PIN_LCD_RST = 4
PIN_LCD_BL = 32
PIN_I2C_SDA = 23
PIN_I2C_SCL = 22

ALL_CURRENCIES = ["USD", "EUR", "GBP", "JPY",
                  "CAD", "AUD", "CHF", "CNY", "MXN"]
CURRENCY_NAMES = {
    "USD": "US Dollar",
    "EUR": "Euro",
    "GBP": "British Pound",
    "JPY": "Japanese Yen",
    "CAD": "Canadian Dollar",
    "AUD": "Australian Dollar",
    "CHF": "Swiss Franc",
    "CNY": "Chinese Yuan",
    "MXN": "Mexican Peso",
}


def get_targets(base):
    return [c for c in ALL_CURRENCIES if c != base]


def wifi_connect():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return True
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    for _ in range(40):
        if wlan.isconnected():
            return True
        utime.sleep_ms(500)
    return False


def fetch_rates(base):
    url = "http://www.floatrates.com/daily/{}.json".format(base.lower())
    r = urequests.get(url, timeout=15)
    data = r.json()
    r.close()
    rates = {}
    date = ""
    for code in get_targets(base):
        entry = data.get(code.lower())
        if entry:
            rates[code] = entry["rate"]
            if not date:
                parts = entry["date"].split()
                if len(parts) >= 4:
                    date = "{} {} {}".format(parts[1], parts[2], parts[3])
    return rates, date


def _add_commas(int_str):
    n = len(int_str)
    if n <= 3:
        return int_str
    parts = []
    start = n % 3
    if start:
        parts.append(int_str[:start])
    for i in range(start, n, 3):
        parts.append(int_str[i:i + 3])
    return ",".join(parts)


def _fmt(value):
    if value >= 10000:
        return _add_commas("{:.0f}".format(value))
    elif value >= 100:
        s = "{:.2f}".format(value)
        int_part, frac_part = s.split(".")
        return "{}.{}".format(_add_commas(int_part), frac_part)
    else:
        return "{:.4f}".format(value)


class CurrencyUI:
    DARK_BG = 0x0d1117
    ACCENT = 0x58a6ff
    TEXT_WHITE = 0xe6edf3
    TEXT_DIM = 0x8b949e
    TEXT_RED = 0xff4444
    ROW_ALT = 0x161b22

    def __init__(self, scr, _app: "CurrencyApp", initial_base: str):
        self._app = _app
        self._row_codes = get_targets(initial_base)
        scr.set_style_bg_color(lv.color_hex(self.DARK_BG), lv.PART.MAIN)
        scr.set_style_pad_all(0, lv.PART.MAIN)

        def mfont(*sizes):
            for s in sizes:
                f = getattr(lv, "font_montserrat_{}".format(s), None)
                if f is not None:
                    return f
            return None

        f20 = mfont(20, 18, 16)
        f16 = mfont(16, 14)
        f14 = mfont(14, 12)

        # Title
        title = lv.label(scr)
        title.set_text("Currency Converter")
        if f20:
            title.set_style_text_font(f20, lv.PART.MAIN)
        title.set_style_text_color(lv.color_hex(self.ACCENT), lv.PART.MAIN)
        title.align(lv.ALIGN.TOP_MID, 0, 8)

        # Base currency label (display only)
        self.base_lbl = lv.label(scr)
        self.base_lbl.set_text("Base: {} ({})"
                               .format(initial_base,
                                       CURRENCY_NAMES.get(initial_base, "")))
        if f16:
            self.base_lbl.set_style_text_font(f16, lv.PART.MAIN)
        self.base_lbl.set_style_text_color(lv.color_hex(self.TEXT_WHITE), lv.PART.MAIN)
        self.base_lbl.align(lv.ALIGN.TOP_LEFT, 10, 38)

        # Amount textarea
        self.amount_ta = lv.textarea(scr)
        self.amount_ta.set_size(300, 34)
        self.amount_ta.align(lv.ALIGN.TOP_MID, 0, 75)
        self.amount_ta.set_text("1")
        self.amount_ta.set_one_line(True)
        self.amount_ta.set_accepted_chars("0123456789.")
        if f16:
            self.amount_ta.set_style_text_font(f16, lv.PART.MAIN)
        self.amount_ta.add_event_cb(self._on_amount_change, lv.EVENT.VALUE_CHANGED, None)
        self.amount_ta.add_event_cb(self._on_ta_focus, lv.EVENT.FOCUSED, None)
        self.amount_ta.add_event_cb(self._on_ta_defocus, lv.EVENT.DEFOCUSED, None)

        # Separator
        sep = lv.line(scr)
        sep.set_points([{"x": 0, "y": 0}, {"x": 310, "y": 0}], 2)
        sep.set_style_line_color(lv.color_hex(0x30363d), lv.PART.MAIN)
        sep.set_style_line_width(1, lv.PART.MAIN)
        sep.align(lv.ALIGN.TOP_LEFT, 5, 113)

        # 8 rate rows
        self._code_labels = []
        self._val_labels = []
        for i, code in enumerate(self._row_codes):
            y = 118 + i * 40
            if i % 2 == 1:
                row_bg = lv.obj(scr)
                row_bg.set_size(320, 38)
                row_bg.set_pos(0, y)
                row_bg.set_style_bg_color(lv.color_hex(self.ROW_ALT), lv.PART.MAIN)
                row_bg.set_style_bg_opa(lv.OPA.COVER, lv.PART.MAIN)
                row_bg.set_style_border_width(0, lv.PART.MAIN)
                row_bg.set_style_pad_all(0, lv.PART.MAIN)
                row_bg.remove_flag(lv.obj.FLAG.SCROLLABLE)

            code_lbl = lv.label(scr)
            code_lbl.set_text("{} ({})"
                              .format(code,
                                      CURRENCY_NAMES.get(code, "")))
            if f16:
                code_lbl.set_style_text_font(f16, lv.PART.MAIN)
            code_lbl.set_style_text_color(lv.color_hex(self.TEXT_WHITE),
                                          lv.PART.MAIN)
            code_lbl.align(lv.ALIGN.TOP_LEFT, 12, y + 10)
            self._code_labels.append(code_lbl)

            val_lbl = lv.label(scr)
            val_lbl.set_text("--")
            if f16:
                val_lbl.set_style_text_font(f16, lv.PART.MAIN)
            val_lbl.set_style_text_color(lv.color_hex(self.TEXT_WHITE), lv.PART.MAIN)
            val_lbl.align(lv.ALIGN.TOP_RIGHT, -12, y + 10)
            self._val_labels.append(val_lbl)

            # Transparent full-width overlay created last so it's on top -
            # captures row taps
            row_touch = lv.obj(scr)
            row_touch.set_size(320, 38)
            row_touch.set_pos(0, y)
            row_touch.set_style_bg_opa(lv.OPA.TRANSP, lv.PART.MAIN)
            row_touch.set_style_border_width(0, lv.PART.MAIN)
            row_touch.remove_flag(lv.obj.FLAG.SCROLLABLE)
            row_touch.add_event_cb(lambda evt, idx=i: self._on_row_tap(idx),
                                   lv.EVENT.CLICKED, None)

        # ECB date footer
        self.footer_lbl = lv.label(scr)
        self.footer_lbl.set_text("floatrates.com")
        if f14:
            self.footer_lbl.set_style_text_font(f14, lv.PART.MAIN)
        self.footer_lbl.set_style_text_color(lv.color_hex(self.TEXT_DIM),
                                             lv.PART.MAIN)
        self.footer_lbl.align(lv.ALIGN.TOP_MID, 0, 442)

        # Status / error label
        self.status_lbl = lv.label(scr)
        self.status_lbl.set_text("")
        if f14:
            self.status_lbl.set_style_text_font(f14, lv.PART.MAIN)
        self.status_lbl.set_style_text_color(lv.color_hex(self.TEXT_RED),
                                             lv.PART.MAIN)
        self.status_lbl.align(lv.ALIGN.TOP_MID, 0, 462)

        # Keyboard created last so it renders on top of all other elements
        self.kb = lv.keyboard(scr)
        self.kb.set_mode(lv.keyboard.MODE.NUMBER)
        self.kb.add_flag(lv.obj.FLAG.HIDDEN)

    def set_base(self, base):
        self.base_lbl.set_text("Base: {} ({})"
                               .format(base,
                                       CURRENCY_NAMES.get(base, "")))

    def show_status(self, msg: str, color: int = TEXT_RED):
        self.status_lbl.set_style_text_color(lv.color_hex(color),
                                             lv.PART.MAIN)
        self.status_lbl.set_text(msg)

    def update_row_codes(self, targets):
        self._row_codes = list(targets)
        for i, code in enumerate(self._row_codes):
            self._code_labels[i].set_text("{} ({})"
                                          .format(code,
                                                  CURRENCY_NAMES.get(code, "")))
            self._val_labels[i].set_text("--")

    def update_rows(self, rates, amount):
        for i, code in enumerate(self._row_codes):
            lbl = self._val_labels[i]
            if code in rates:
                lbl.set_text(_fmt(rates[code] * amount))
            else:
                lbl.set_text("--")

    def _on_row_tap(self, idx):
        self._app.on_row_tap(self._row_codes[idx])

    def _on_amount_change(self, _evt):
        try:
            amount = float(self.amount_ta.get_text() or "0")
        except (ValueError, TypeError):
            return
        self._app.update_display(amount)

    def _on_ta_focus(self, _evt):
        self.kb.set_textarea(self.amount_ta)
        self.kb.remove_flag(lv.obj.FLAG.HIDDEN)

    def _on_ta_defocus(self, _evt):
        self.kb.add_flag(lv.obj.FLAG.HIDDEN)


class CurrencyApp:
    def __init__(self):
        lv.init()

        spi = SPI(2, baudrate=20_000_000,
                  sck=Pin(PIN_SPI_CLK),
                  mosi=Pin(PIN_SPI_MOSI),
                  miso=Pin(PIN_SPI_MISO))
        self.display = ili9488.Ili9488(
            spi=spi,
            cs=PIN_LCD_CS, dc=PIN_LCD_DC, rst=PIN_LCD_RST,
            bl=PIN_LCD_BL,
            rot=ili9488.ILI9488_PORTRAIT,
            factor=8,
        )
        self.display.set_backlight(100)
        self.touch = ft6x36.ft6x36(i2c_dev=0,
                                   sda=PIN_I2C_SDA,
                                   scl=PIN_I2C_SCL,
                                   freq=400_000)

        self._base = "USD"
        self._rates = {}

        self.ui = CurrencyUI(lv.screen_active(), self, self._base)
        lv.timer_handler()

        self._fetch()

    def on_row_tap(self, code):
        self._base = code
        self.ui.set_base(code)
        self.ui.update_row_codes(get_targets(code))
        self._fetch()

    def _fetch(self):
        base = self._base
        self.ui.show_status("Fetching rates...", 0x58a6ff)
        lv.timer_handler()
        try:
            if not wifi_connect():
                self.ui.show_status("WiFi failed")
                return
            self._rates, date = fetch_rates(base)
            self.ui.footer_lbl.set_text("floatrates.com - {}".format(date))
            try:
                amount = float(self.ui.amount_ta.get_text() or "1")
            except (ValueError, TypeError):
                amount = 1.0
            self.ui.update_rows(self._rates, amount)
            self.ui.show_status("")
        except Exception as e:
            self.ui.show_status("Error: {}".format(str(e))[:40])

    def update_display(self, amount):
        self.ui.update_rows(self._rates, amount)


def run():
    while True:
        utime.sleep_ms(lv.timer_handler())


app = CurrencyApp()
run()
