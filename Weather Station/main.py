import utime
import math
import network
import urequests
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

UPDATE_INTERVAL_MS = 10 * 60 * 1000  # 10 minutes

# WMO weather interpretation codes from Open-Meteo
WMO_CODES = {
    0: "Clear Sky",
    1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",
    45: "Foggy", 48: "Icy Fog",
    51: "Light Drizzle", 53: "Drizzle", 55: "Dense Drizzle",
    61: "Light Rain", 63: "Rain", 65: "Heavy Rain",
    71: "Light Snow", 73: "Snow", 75: "Heavy Snow",
    77: "Snow Grains",
    80: "Light Showers", 81: "Showers", 82: "Heavy Showers",
    85: "Snow Showers", 86: "Heavy Snow Showers",
    95: "Thunderstorm",
    96: "Thunderstorm + Hail", 99: "Thunderstorm + Heavy Hail",
}


def _wmo_category(code):
    if code == 0:                                      return "clear"
    if code in (1, 2):                                 return "partly_cloudy"
    if code == 3:                                      return "cloudy"
    if code in (45, 48):                               return "fog"
    if 51 <= code <= 67 or code in (80, 81, 82):      return "rain"
    if code in (71, 73, 75, 77, 85, 86):              return "snow"
    if code in (95, 96, 99):                           return "thunder"
    return "clear"


class WeatherIcon:
    """Draws a simple iconic weather symbol inside a 64×64 lv.obj container."""
    SUN = 0xFFCC00
    CLOUD = 0xBBCCDD
    RAIN = 0x4488FF
    SNOW = 0xEEEEFF
    BOLT = 0xFFEE00
    FOG = 0x7788AA
    BG = 0x0d1117

    def __init__(self, parent, y=155):
        self.cont = lv.obj(parent)
        self.cont.set_size(64, 64)
        self.cont.set_style_bg_color(lv.color_hex(self.BG), lv.PART.MAIN)
        self.cont.set_style_bg_opa(lv.OPA.COVER, lv.PART.MAIN)
        self.cont.set_style_border_width(0, lv.PART.MAIN)
        self.cont.set_style_pad_all(0, lv.PART.MAIN)
        # Hide any scrollbar that might appear from child objects
        self.cont.set_style_opa(lv.OPA.TRANSP, lv.PART.SCROLLBAR)
        self.cont.align(lv.ALIGN.TOP_MID, 0, y)

    def _circ(self, color, x, y, sz):
        o = lv.obj(self.cont)
        o.set_size(sz, sz)
        o.set_style_radius(0x7FFF, lv.PART.MAIN)
        o.set_style_bg_color(lv.color_hex(color), lv.PART.MAIN)
        o.set_style_bg_opa(lv.OPA.COVER, lv.PART.MAIN)
        o.set_style_border_width(0, lv.PART.MAIN)
        o.set_style_pad_all(0, lv.PART.MAIN)
        o.set_pos(x, y)

    def _rect(self, color, x, y, w, h, r=7):
        o = lv.obj(self.cont)
        o.set_size(w, h)
        o.set_style_radius(r, lv.PART.MAIN)
        o.set_style_bg_color(lv.color_hex(color), lv.PART.MAIN)
        o.set_style_bg_opa(lv.OPA.COVER, lv.PART.MAIN)
        o.set_style_border_width(0, lv.PART.MAIN)
        o.set_style_pad_all(0, lv.PART.MAIN)
        o.set_pos(x, y)

    def _ln(self, color, x1, y1, x2, y2, w=3):
        ln = lv.line(self.cont)
        ln.set_points([{"x": x1, "y": y1}, {"x": x2, "y": y2}], 2)
        ln.set_style_line_color(lv.color_hex(color), lv.PART.MAIN)
        ln.set_style_line_width(w, lv.PART.MAIN)
        ln.set_style_line_rounded(True, lv.PART.MAIN)

    def _cloud(self, cx, cy):
        # noinspection PyTypeChecker
        self._rect(self.CLOUD, cx - 18, cy, 36, 14)  # wide base
        # noinspection PyTypeChecker
        self._circ(self.CLOUD, cx - 20, cy - 10, 20)  # left bump
        # noinspection PyTypeChecker
        self._circ(self.CLOUD, cx - 4, cy - 16, 24)  # larger right bump

    def _sun(self, cx, cy, rb, ri, ro):
        # noinspection PyTypeChecker
        self._circ(self.SUN, cx - rb, cy - rb, rb * 2)
        for i in range(8):
            a = math.radians(i * 45)
            # noinspection PyTypeChecker
            self._ln(self.SUN,
                     cx + int(ri * math.cos(a)), cy + int(ri * math.sin(a)),
                     cx + int(ro * math.cos(a)), cy + int(ro * math.sin(a)), 3)

    def draw(self, wmo_code):
        self.cont.clean()
        cat = _wmo_category(wmo_code)

        if cat == "clear":
            # Full sun centred in the 64×64 area
            self._sun(32, 32, 12, 17, 25)

        elif cat == "partly_cloudy":
            # Small sun upper-left, cloud lower-right
            self._sun(20, 20, 9, 13, 19)
            # noinspection PyTypeChecker
            self._cloud(42, 40)

        elif cat == "cloudy":
            # noinspection PyTypeChecker
            self._cloud(32, 24)

        elif cat == "fog":
            for y in (16, 30, 44):
                # noinspection PyTypeChecker
                self._ln(self.FOG, 8, y, 56, y, 5)

        elif cat == "rain":
            # noinspection PyTypeChecker
            self._cloud(32, 16)
            for x in (18, 30, 42):
                # noinspection PyTypeChecker
                self._ln(self.RAIN, x, 38, x - 5, 56, 3)

        elif cat == "snow":
            # noinspection PyTypeChecker
            self._cloud(32, 16)
            for x in (14, 28, 42):
                # noinspection PyTypeChecker
                self._circ(self.SNOW, x, 42, 8)
                # noinspection PyTypeChecker
                self._circ(self.SNOW, x, 54, 8)

        elif cat == "thunder":
            # noinspection PyTypeChecker
            self._cloud(32, 14)
            # noinspection PyTypeChecker
            self._ln(self.BOLT, 34, 36, 24, 50, 5)
            # noinspection PyTypeChecker
            self._ln(self.BOLT, 24, 50, 34, 50, 5)
            # noinspection PyTypeChecker
            self._ln(self.BOLT, 34, 50, 24, 62, 5)


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


def fetch_location():
    # ip-api.com: free, HTTP, no key required
    r = urequests.get("http://ip-api.com/json/?fields=lat,lon,city,country", timeout=10)
    data = r.json()
    r.close()
    return data["lat"], data["lon"], data.get("city", ""), data.get("country", "")


def fetch_weather(lat, lon):
    url = (
        "http://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,apparent_temperature,"
        "relative_humidity_2m,wind_speed_10m,wind_direction_10m,wind_gusts_10m,surface_pressure,weather_code"
        "&temperature_unit=fahrenheit&wind_speed_unit=mph"
        "&timezone=auto"
    )
    r = urequests.get(url, timeout=15)
    data = r.json()
    r.close()
    tz_abbr = data.get("timezone_abbreviation", "UTC")
    utc_offset = data.get("utc_offset_seconds", 0)
    return data["current"], tz_abbr, utc_offset


# ---------------------------------------------------------------------------
# LVGL UI
# ---------------------------------------------------------------------------
def _fmt_time(utc_offset):
    t = utime.localtime(utime.time() + utc_offset)
    hour, minute = t[3], t[4]
    ampm = "AM" if hour < 12 else "PM"
    hour12 = hour % 12 or 12
    return f"{hour12}:{minute:02d} {ampm}"


class WeatherUI:
    DARK_BG = 0x0d1117
    ACCENT = 0x58a6ff
    TEXT_WHITE = 0xe6edf3
    TEXT_DIM = 0x8b949e
    TEXT_WARN = 0xf0a500
    TEXT_GREEN = 0x3fb950
    TEXT_RED = 0xff4444

    def __init__(self, scr):
        scr.set_style_bg_color(lv.color_hex(self.DARK_BG), lv.PART.MAIN)

        def label(parent, font, color, text, align, x=0, y=0):
            lb = lv.label(parent)
            if font is not None:
                lb.set_style_text_font(font, lv.PART.MAIN)
            lb.set_style_text_color(lv.color_hex(color), lv.PART.MAIN)
            lb.set_text(text)
            lb.align(align, x, y)
            return lb

        def mfont(*sizes):
            for s in sizes:
                f = getattr(lv, f"font_montserrat_{s}", None)
                if f is not None:
                    return f
            return None  # omit font call; LVGL uses its compiled-in default

        f48 = mfont(36, 32, 28, 24)  # large temperature
        f24 = mfont(22, 20, 18)  # city / condition
        f18 = mfont(18, 16, 14)  # secondary info
        f14 = mfont(14, 12)

        top = lv.ALIGN.TOP_MID
        bot = lv.ALIGN.BOTTOM_MID

        # noinspection PyTypeChecker
        self.lbl_city = label(scr, f24, self.ACCENT, "Connecting...", top, 0, 12)
        # noinspection PyTypeChecker
        self.lbl_time = label(scr, f18, self.TEXT_WHITE, "--:-- --", top, 0, 44)
        # noinspection PyTypeChecker
        self.lbl_temp = label(scr, f48, self.TEXT_WHITE, "--\xb0F", top, 0, 78)
        # noinspection PyTypeChecker
        self.lbl_feels = label(scr, f18, self.TEXT_DIM, "Feels like --\xb0F", top, 0, 118)

        # Weather icon (64×64) sits between feels-like and condition
        self.icon = WeatherIcon(scr, y=155)
        # noinspection PyTypeChecker
        self.lbl_condition = label(scr, f24, self.TEXT_WARN, "--", top, 0, 228)

        # Separator
        sep = lv.line(scr)
        sep.set_points([{"x": 0, "y": 0}, {"x": 280, "y": 0}], 2)
        sep.set_style_line_color(lv.color_hex(0x30363d), lv.PART.MAIN)
        sep.set_style_line_width(2, lv.PART.MAIN)
        sep.align(top, 0, 258)

        # noinspection PyTypeChecker
        self.lbl_humidity = label(scr, f18, self.ACCENT, "Humidity:   --%", top, 0, 273)
        # noinspection PyTypeChecker
        self.lbl_wind = label(scr, f18, self.TEXT_GREEN, "Wind:      -- mph --", top, 0, 301)
        # noinspection PyTypeChecker
        self.lbl_gust = label(scr, f18, self.TEXT_GREEN, "Gust:      -- mph", top, 0, 329)
        # noinspection PyTypeChecker
        self.lbl_pressure = label(scr, f18, self.ACCENT, "Pressure: -- inHg", top, 0, 357)
        # noinspection PyTypeChecker
        self.lbl_updated = label(scr, f14, self.TEXT_DIM, "Last updated: --", bot, 0, -40)
        # noinspection PyTypeChecker
        self.lbl_status = label(scr, f14, self.TEXT_RED, "", bot, 0, -18)

    def show_status(self, msg, color=None):
        self.lbl_status.set_style_text_color(
            lv.color_hex(color if color else self.TEXT_RED), lv.PART.MAIN)
        self.lbl_status.set_text(msg)

    def update_time(self, utc_offset):
        self.lbl_time.set_text(_fmt_time(utc_offset))

    @staticmethod
    def _compass(deg):
        dirs = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
        return dirs[int((deg + 22.5) / 45) % 8]

    def update(self, city, country, weather, utc_offset=0):
        temp = weather.get("temperature_2m", None)
        feels = weather.get("apparent_temperature", None)
        hum = weather.get("relative_humidity_2m", None)
        wind = weather.get("wind_speed_10m", None)
        wdir = weather.get("wind_direction_10m", None)
        gust = weather.get("wind_gusts_10m", None)
        pres = weather.get("surface_pressure", None)
        code = weather.get("weather_code", -1)

        self.lbl_city.set_text(f"{city}, {country}" if city else "Unknown location")
        self.update_time(utc_offset)

        self.lbl_temp.set_text(
            f"{temp:.0f}\xb0F" if temp is not None else "--\xb0F")
        self.lbl_feels.set_text(
            f"Feels like {feels:.0f}\xb0F" if feels is not None else "Feels like --\xb0F")
        self.icon.draw(code)
        self.lbl_condition.set_text(WMO_CODES.get(code, "Unknown"))
        self.lbl_humidity.set_text(
            f"Humidity:   {hum:.0f}%" if hum is not None else "Humidity:   --%")

        if wind is not None:
            direction = f" {self._compass(wdir)}" if wdir is not None else ""
            self.lbl_wind.set_text(f"Wind:      {wind:.1f} mph{direction}")
        else:
            self.lbl_wind.set_text("Wind:      -- mph")

        self.lbl_gust.set_text(
            f"Gust:      {gust:.1f} mph" if gust is not None else "Gust:      -- mph")

        in_hg = pres * 0.02953 if pres is not None else None
        self.lbl_pressure.set_text(
            f"Pressure: {in_hg:.2f} inHg" if in_hg is not None else "Pressure: -- inHg")

        self.lbl_updated.set_text(f"Updated: {_fmt_time(utc_offset)}")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
def run():
    while True:
        utime.sleep_ms(lv.timer_handler())


class WeatherStation:
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

        self.ui = WeatherUI(lv.screen_active())
        lv.timer_handler()

        self._lat = None
        self._lon = None
        self._city = ""
        self._country = ""
        self._utc_offset = 0
        self._tz_abbr = "UTC"
        self._ntp_synced = False

        # First update immediately, then every 10 minutes
        self._update()
        self._timer = lv.timer_create(self._on_timer, UPDATE_INTERVAL_MS, None)
        self._clock_timer = lv.timer_create(self._on_clock, 60_000, None)

    def _on_timer(self, _t):
        self._update()

    def _on_clock(self, _t):
        self.ui.update_time(self._utc_offset)

    def _update(self):
        # noinspection PyTypeChecker
        self.ui.show_status("Updating...", self.ui.ACCENT)
        lv.timer_handler()
        try:
            if not wifi_connect():
                # noinspection PyTypeChecker
                self.ui.show_status("WiFi failed")
                return

            if not self._ntp_synced:
                try:
                    import ntptime
                    ntptime.settime()
                    self._ntp_synced = True
                except Exception:
                    pass

            if self._lat is None:
                self._lat, self._lon, self._city, self._country = fetch_location()

            weather, self._tz_abbr, self._utc_offset = fetch_weather(self._lat, self._lon)
            self.ui.update(self._city, self._country, weather, self._utc_offset)
            # noinspection PyTypeChecker
            self.ui.show_status("")
        except Exception as e:
            # noinspection PyTypeChecker
            self.ui.show_status(f"Error: {e}"[:40])


station = WeatherStation()
run()
