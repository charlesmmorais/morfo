//! Gráficos 2D por software sobre o framebuffer do UEFI (GOP).
//!
//! Tudo é desenhado num buffer na RAM e depois copiado de uma vez para
//! a tela (`present`), sem cintilação. Não há driver de GPU nesta fase.

use alloc::vec;
use alloc::vec::Vec;
use font8x8::UnicodeFonts;
use limine::framebuffer::Framebuffer;
use spin::Mutex;

#[derive(Clone, Copy)]
pub struct Rgb(pub u8, pub u8, pub u8);

pub struct Canvas {
    fb_addr: *mut u8,
    fb_pitch: usize,
    pub width: usize,
    pub height: usize,
    back: Vec<u32>,
    shifts: (u8, u8, u8),
    /// Escala da fonte (8 px × escala).
    pub scale: usize,
}

unsafe impl Send for Canvas {}

pub static CANVAS: Mutex<Option<Canvas>> = Mutex::new(None);

pub fn init(fb: &Framebuffer) {
    let width = fb.width as usize;
    let height = fb.height as usize;
    let scale = if width >= 1600 { 3 } else if width >= 1000 { 2 } else { 1 };
    *CANVAS.lock() = Some(Canvas {
        fb_addr: fb.address() as *mut u8,
        fb_pitch: fb.pitch as usize,
        width,
        height,
        back: vec![0; width * height],
        shifts: (fb.red_mask_shift, fb.green_mask_shift, fb.blue_mask_shift),
        scale,
    });
}

impl Canvas {
    #[inline]
    fn pack(&self, c: Rgb) -> u32 {
        ((c.0 as u32) << self.shifts.0) | ((c.1 as u32) << self.shifts.1) | ((c.2 as u32) << self.shifts.2)
    }

    pub fn clear(&mut self, c: Rgb) {
        let v = self.pack(c);
        self.back.fill(v);
    }

    pub fn fill_rect(&mut self, x: isize, y: isize, w: usize, h: usize, c: Rgb) {
        let v = self.pack(c);
        let x0 = x.max(0) as usize;
        let y0 = y.max(0) as usize;
        let x1 = ((x + w as isize).max(0) as usize).min(self.width);
        let y1 = ((y + h as isize).max(0) as usize).min(self.height);
        for row in y0..y1 {
            let base = row * self.width;
            self.back[base + x0..base + x1.max(x0)].fill(v);
        }
    }

    /// Retângulo com cantos arredondados (usado pelos balões do chat).
    pub fn fill_round_rect(&mut self, x: isize, y: isize, w: usize, h: usize, r: usize, c: Rgb) {
        let r = r.min(w / 2).min(h / 2);
        let ri = r as isize;
        self.fill_rect(x, y + ri, w, h - 2 * r, c);
        for dy in 0..ri {
            // Distância até o centro do arco, para cada linha dos cantos.
            let yy = ri - dy;
            let mut inset = 0isize;
            while inset < ri {
                let xx = ri - inset;
                if xx * xx + yy * yy <= ri * ri + ri {
                    break;
                }
                inset += 1;
            }
            let span = (w as isize - 2 * inset).max(0) as usize;
            self.fill_rect(x + inset, y + dy, span, 1, c);
            self.fill_rect(x + inset, y + h as isize - 1 - dy, span, 1, c);
        }
    }

    pub fn glyph_w(&self) -> usize {
        8 * self.scale
    }

    pub fn glyph_h(&self) -> usize {
        8 * self.scale + 3 * self.scale
    }

    pub fn draw_char(&mut self, x: isize, y: isize, ch: char, c: Rgb) {
        let bitmap = font8x8::BASIC_FONTS
            .get(ch)
            .or_else(|| font8x8::LATIN_FONTS.get(ch))
            .or_else(|| font8x8::BOX_FONTS.get(ch))
            .or_else(|| font8x8::BLOCK_FONTS.get(ch))
            .unwrap_or(font8x8::BASIC_FONTS.get('?').unwrap());
        let s = self.scale as isize;
        let v = self.pack(c);
        for (row, bits) in bitmap.iter().enumerate() {
            for col in 0..8 {
                if bits & (1 << col) != 0 {
                    let px = x + col as isize * s;
                    let py = y + row as isize * s;
                    for dy in 0..s {
                        for dx in 0..s {
                            let (xx, yy) = (px + dx, py + dy);
                            if xx >= 0 && yy >= 0 && (xx as usize) < self.width && (yy as usize) < self.height {
                                self.back[yy as usize * self.width + xx as usize] = v;
                            }
                        }
                    }
                }
            }
        }
    }

    pub fn draw_text(&mut self, x: isize, y: isize, text: &str, c: Rgb) {
        let gw = self.glyph_w() as isize;
        for (i, ch) in text.chars().enumerate() {
            self.draw_char(x + i as isize * gw, y, ch, c);
        }
    }

    /// Copia o buffer para a memória de vídeo.
    pub fn present(&mut self) {
        for row in 0..self.height {
            let src = &self.back[row * self.width..(row + 1) * self.width];
            unsafe {
                let dst = self.fb_addr.add(row * self.fb_pitch) as *mut u32;
                core::ptr::copy_nonoverlapping(src.as_ptr(), dst, self.width);
            }
        }
    }
}

/// Tela de erro fatal. Não usa o heap: pode estar corrompido.
pub fn panic_screen(info: &core::panic::PanicInfo) {
    // Evita travar se o pânico aconteceu com o canvas em uso.
    let Some(mut guard) = CANVAS.try_lock() else { return };
    let Some(cv) = guard.as_mut() else { return };

    let mut buf = FixedBuf::<512>::new();
    let _ = core::fmt::write(&mut buf, format_args!("{}", info.message()));

    cv.clear(Rgb(90, 20, 30));
    let m = cv.glyph_w() as isize * 2;
    cv.draw_text(m, m, "Morfo parou: erro fatal no kernel", Rgb(255, 255, 255));
    let cols = (cv.width / cv.glyph_w()).saturating_sub(4).max(10);
    let mut y = m + cv.glyph_h() as isize * 2;
    let text = buf.as_str();
    let mut start = 0;
    while start < text.len() {
        let mut end = text.len();
        let mut count = 0;
        for (i, _) in text[start..].char_indices() {
            if count == cols {
                end = start + i;
                break;
            }
            count += 1;
        }
        cv.draw_text(m, y, &text[start..end], Rgb(255, 210, 210));
        y += cv.glyph_h() as isize;
        start = end;
    }
    cv.present();
}

struct FixedBuf<const N: usize> {
    data: [u8; N],
    len: usize,
}

impl<const N: usize> FixedBuf<N> {
    fn new() -> Self {
        FixedBuf { data: [0; N], len: 0 }
    }
    fn as_str(&self) -> &str {
        core::str::from_utf8(&self.data[..self.len]).unwrap_or("?")
    }
}

impl<const N: usize> core::fmt::Write for FixedBuf<N> {
    fn write_str(&mut self, s: &str) -> core::fmt::Result {
        for ch in s.chars() {
            let mut tmp = [0u8; 4];
            let b = ch.encode_utf8(&mut tmp).as_bytes();
            if self.len + b.len() > N {
                return Ok(());
            }
            self.data[self.len..self.len + b.len()].copy_from_slice(b);
            self.len += b.len();
        }
        Ok(())
    }
}
