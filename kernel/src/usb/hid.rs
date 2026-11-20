//! Teclado USB (HID, protocolo de boot).
//!
//! Lê o estado das teclas com GET_REPORT a cada 10 ms pelo canal de
//! controle. É mais simples que um endpoint de interrupção e funciona
//! igual atrás do hub interno do Mac mini. Gera repetição ao segurar.

use alloc::format;
use alloc::string::String;
use alloc::sync::Arc;

use super::Bus;
use super::ehci::ControlPipe;
use crate::keyboard::{Key, SOURCE_USB, push_key};
use crate::time::{sleep_ms, ticks_ms};

const POLL_MS: u64 = 10;
const REPEAT_DELAY_MS: u64 = 450;
const REPEAT_RATE_MS: u64 = 40;

pub async fn keyboard(bus: Arc<Bus>, pipe: ControlPipe, iface: u8, place: String) {
    let hc = &bus.hc;
    // SET_PROTOCOL(boot) e SET_IDLE(0). Alguns teclados recusam; não é fatal.
    let _ = hc.control(&pipe, [0x21, 0x0B, 0, 0, iface, 0, 0, 0], 0, None).await;
    let _ = hc.control(&pipe, [0x21, 0x0A, 0, 0, iface, 0, 0, 0], 0, None).await;
    super::note(format!("{place}: teclado pronto"));

    let mut prev = [0u8; 8];
    let mut held: Option<(u8, u8, u64)> = None; // (uso HID, modificadores, próximo disparo)
    let mut errors = 0u32;

    loop {
        sleep_ms(POLL_MS).await;
        let report = match hc.control(&pipe, [0xA1, 0x01, 0, 1, iface, 0, 8, 0], 8, None).await {
            Ok(n) if n >= 3 => {
                errors = 0;
                let mut r = [0u8; 8];
                unsafe { core::ptr::copy_nonoverlapping(pipe.data.virt, r.as_mut_ptr(), n.min(8)) };
                r
            }
            Ok(_) => continue,
            Err(e) => {
                errors += 1;
                if errors == 50 {
                    super::note(format!("{place}: teclado não responde ({e:?})"));
                }
                sleep_ms(if errors > 50 { 500 } else { 10 }).await;
                continue;
            }
        };
        // Relatório de "rollover" (teclas demais): ignora.
        if report[2] == 1 {
            continue;
        }

        let mods = report[0];
        for &usage in &report[2..8] {
            if usage != 0 && !prev[2..8].contains(&usage) {
                emit(usage, mods);
                held = Some((usage, mods, ticks_ms() + REPEAT_DELAY_MS));
            }
        }
        // Repetição enquanto a última tecla continua pressionada.
        if let Some((usage, m, next)) = held {
            if !report[2..8].contains(&usage) {
                held = None;
            } else if ticks_ms() >= next {
                emit(usage, m);
                held = Some((usage, m, ticks_ms() + REPEAT_RATE_MS));
            }
        }
        prev = report;
    }
}

fn emit(usage: u8, mods: u8) {
    let shift = mods & 0x22 != 0;
    let key = match usage {
        0x28 | 0x58 => Key::Enter,
        0x2A => Key::Backspace,
        u => match to_char(u, shift) {
            Some(c) => Key::Char(c),
            None => Key::Other,
        },
    };
    push_key(key, SOURCE_USB);
}

/// Layout US (o mesmo dos teclados Apple vendidos sem ABNT2).
fn to_char(usage: u8, shift: bool) -> Option<char> {
    let c = match usage {
        0x04..=0x1D => {
            let c = (b'a' + usage - 0x04) as char;
            return Some(if shift { c.to_ascii_uppercase() } else { c });
        }
        0x1E..=0x27 => {
            const N: &[u8; 10] = b"1234567890";
            const S: &[u8; 10] = b"!@#$%^&*()";
            let i = (usage - 0x1E) as usize;
            return Some(if shift { S[i] } else { N[i] } as char);
        }
        0x2C => ' ',
        0x2D => if shift { '_' } else { '-' },
        0x2E => if shift { '+' } else { '=' },
        0x2F => if shift { '{' } else { '[' },
        0x30 => if shift { '}' } else { ']' },
        0x31 => if shift { '|' } else { '\\' },
        0x33 => if shift { ':' } else { ';' },
        0x34 => if shift { '"' } else { '\'' },
        0x35 => if shift { '~' } else { '`' },
        0x36 => if shift { '<' } else { ',' },
        0x37 => if shift { '>' } else { '.' },
        0x38 => if shift { '?' } else { '/' },
        _ => return None,
    };
    Some(c)
}
