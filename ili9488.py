import struct
import micropython
import st77xx

_MADCTL_MX = 0x40
_MADCTL_MY = 0x80
_MADCTL_MV = 0x20

_MADCTL_ROTS = (
    _MADCTL_MX,                             # portrait
    _MADCTL_MV,                             # landscape
    _MADCTL_MY,                             # inverted portrait
    _MADCTL_MX | _MADCTL_MY | _MADCTL_MV,  # inverted landscape
)

ILI9488_PORTRAIT = st77xx.ST77XX_PORTRAIT
ILI9488_LANDSCAPE = st77xx.ST77XX_LANDSCAPE
ILI9488_INV_PORTRAIT = st77xx.ST77XX_INV_PORTRAIT
ILI9488_INV_LANDSCAPE = st77xx.ST77XX_INV_LANDSCAPE


# Converts LVGL little-endian RGB565 → 18-bit pixels in BGR byte order.
# BGR order corrects the R/B swap on this panel (physical BGR stripe, MADCTL BGR=0).
# Runs as native machine code via viper (~10-50x faster than a Python loop).
@micropython.viper
def _rgb565_to_rgb666(src: ptr8, dst: ptr8, n: int):
    si = 0
    di = 0
    end = n * 2
    while si < end:
        lo = int(src[si])      # bits 7-0:  GGG BBBBB  (G lower + B)
        hi = int(src[si + 1])  # bits 15-8: RRRRR GGG  (R + G upper)
        dst[di]     = (lo & 31) << 3                         # B → byte 0
        dst[di + 1] = ((hi & 7) << 5) | ((lo & 0xE0) >> 3)  # G → byte 1
        dst[di + 2] = hi & 0xF8                              # R → byte 2
        si += 2
        di += 3


class Ili9488_hw(st77xx.St77xx_hw):
    def __init__(self, **kw):
        super().__init__(
            res=(320, 480),
            suppRes=[(320, 480)],
            model=None,
            suppModel=None,
            bgr=False,
            **kw,
        )

    def config_hw(self):
        self._run_seq([
            (0x01, None, 200),
            (0x11, None, 120),
            (0xE0, bytes([0x00, 0x03, 0x09, 0x08, 0x16, 0x0A, 0x3F, 0x78, 0x4C, 0x09, 0x0A, 0x08, 0x16, 0x1A, 0x0F])),
            (0xE1, bytes([0x00, 0x16, 0x19, 0x03, 0x0F, 0x05, 0x32, 0x45, 0x46, 0x04, 0x0E, 0x0D, 0x35, 0x37, 0x0F])),
            (0xC0, bytes([0x17, 0x15])),
            (0xC1, bytes([0x41])),
            (0xC2, bytes([0x44])),
            (0xC5, bytes([0x00, 0x12, 0x80])),
            (0x3A, bytes([0x66])),   # 18-bit RGB666 — ILI9488 requires 18-bit over SPI
            (0xB0, bytes([0x00])),
            (0xB1, bytes([0xA0])),
            (0xB4, bytes([0x02])),
            (0xB6, bytes([0x02, 0x02])),
            (0xE9, bytes([0x00])),
            (0x53, bytes([0x28])),
            (0x51, bytes([0x7F])),
            (0xF7, bytes([0xA9, 0x51, 0x2C, 0x02])),
            (0x29, None, 120),
        ])

    def apply_rotation(self, rot):
        self.rot = rot
        if (self.rot % 2) == 0:
            self.width, self.height = self.res
        else:
            self.height, self.width = self.res
        self.write_register(0x36, bytes([_MADCTL_ROTS[self.rot % 4]]))

    def set_window(self, x, y, w, h):
        struct.pack_into('>HH', self.buf4, 0, x, x + w - 1)
        self.write_register(0x2A, self.buf4)
        struct.pack_into('>HH', self.buf4, 0, y, y + h - 1)
        self.write_register(0x2B, self.buf4)

    def clear(self, color):
        # RGB565 → 3-byte BGR666 pixel: B first, R last (matches panel stripe order)
        pixel = bytes([(color << 3) & 0xF8,   # B
                       (color >> 3) & 0xFC,    # G
                       (color >> 8) & 0xF8])   # R
        bs = 128
        buf = bs * pixel
        npx = self.width * self.height
        self.set_window(0, 0, self.width, self.height)
        self.write_register(0x2C, None)
        self.cs.value(0)
        self.dc.value(1)
        for _ in range(npx // bs): self.spi.write(buf)
        rem = npx % bs
        if rem: self.spi.write(rem * pixel)
        self.cs.value(1)


class Ili9488(Ili9488_hw, st77xx.St77xx_lvgl):
    def __init__(self, doublebuffer=True, factor=4, **kw):
        Ili9488_hw.__init__(self, **kw)
        st77xx.St77xx_lvgl.__init__(self, doublebuffer, factor)
        self._rgb666_buf = bytearray(self.width * (self.height // factor) * 3)

    def disp_drv_flush_cb(self, disp_drv, area, color_p):
        w = area.x2 - area.x1 + 1
        h = area.y2 - area.y1 + 1
        size = w * h
        src = color_p.__dereference__(size * self.pixel_size)
        _rgb565_to_rgb666(src, self._rgb666_buf, size)
        self.blit(area.x1, area.y1, w, h, memoryview(self._rgb666_buf)[:size * 3], is_blocking=False)
        self.disp_drv.flush_ready()
