//! Entrada de teclado unificada.
//!
//! Várias fontes (PS/2 no QEMU, USB no Mac mini) empurram teclas para uma
//! única fila; o shell só enxerga `Keys::next_key`. Aqui também ficam as
//! teclas mortas do layout US-Internacional, para acentuar em português:
//! ' + a = á, ~ + a = ã, ^ + e = ê, ` + a = à, ' + c = ç.

use core::future::poll_fn;
use core::sync::atomic::{AtomicU8, Ordering};
use core::task::Poll;
use crossbeam_queue::ArrayQueue;
use futures_util::task::AtomicWaker;
use pc_keyboard::{DecodedKey, HandleControl, Keyboard, ScancodeSet1, layouts};
use spin::Once;

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Key {
    Char(char),
    Enter,
    Backspace,
    /// Não é tecla: acorda o shell para mostrar avisos do sistema.
    Refresh,
    Other,
}

static KEYS: Once<ArrayQueue<Key>> = Once::new();
static KEYS_WAKER: AtomicWaker = AtomicWaker::new();

static SCANCODES: Once<ArrayQueue<u8>> = Once::new();
static SCANCODES_WAKER: AtomicWaker = AtomicWaker::new();

/// Fonte de entrada ativa, para o cabeçalho do shell.
pub const SOURCE_NONE: u8 = 0;
pub const SOURCE_PS2: u8 = 1;
pub const SOURCE_USB: u8 = 2;
pub static LAST_SOURCE: AtomicU8 = AtomicU8::new(SOURCE_NONE);

pub fn init() {
    KEYS.call_once(|| ArrayQueue::new(256));
    SCANCODES.call_once(|| ArrayQueue::new(256));
}

/// Entrega uma tecla ao shell. Pode ser chamada de qualquer tarefa.
pub fn push_key(k: Key, source: u8) {
    if let Some(q) = KEYS.get() {
        if q.push(k).is_ok() {
            if source != SOURCE_NONE {
                LAST_SOURCE.store(source, Ordering::Relaxed);
            }
            KEYS_WAKER.wake();
        }
    }
}

/// Chamado pela interrupção do PS/2. Não aloca nem bloqueia.
pub fn push_scancode(code: u8) {
    if let Some(q) = SCANCODES.get() {
        if q.push(code).is_ok() {
            SCANCODES_WAKER.wake();
        }
    }
}

async fn next_from<T>(q: &'static ArrayQueue<T>, waker: &'static AtomicWaker) -> T {
    poll_fn(|cx| {
        if let Some(v) = q.pop() {
            return Poll::Ready(v);
        }
        waker.register(cx.waker());
        match q.pop() {
            Some(v) => {
                waker.take();
                Poll::Ready(v)
            }
            None => Poll::Pending,
        }
    })
    .await
}

/// Tarefa que decodifica o teclado PS/2.
pub async fn ps2_task() {
    let q = SCANCODES.get().expect("teclado não iniciado");
    let mut kb = Keyboard::new(ScancodeSet1::new(), layouts::Us104Key, HandleControl::Ignore);
    loop {
        let code = next_from(q, &SCANCODES_WAKER).await;
        if let Ok(Some(ev)) = kb.add_byte(code) {
            if let Some(k) = kb.process_keyevent(ev) {
                let key = match k {
                    DecodedKey::Unicode('\n') | DecodedKey::Unicode('\r') => Key::Enter,
                    DecodedKey::Unicode('\u{8}') => Key::Backspace,
                    DecodedKey::Unicode(c) if !c.is_control() => Key::Char(c),
                    _ => Key::Other,
                };
                push_key(key, SOURCE_PS2);
            }
        }
    }
}

pub struct Keys {
    dead: Option<char>,
    pending: Option<Key>,
}

impl Keys {
    pub fn new() -> Self {
        Keys { dead: None, pending: None }
    }

    pub async fn next_key(&mut self) -> Key {
        if let Some(k) = self.pending.take() {
            return k;
        }
        let q = KEYS.get().expect("teclado não iniciado");
        loop {
            let k = next_from(q, &KEYS_WAKER).await;
            let Key::Char(c) = k else {
                // Tecla especial: solta a tecla morta pendente como caractere.
                if let Some(d) = self.dead.take() {
                    self.pending = Some(k);
                    return Key::Char(d);
                }
                return k;
            };
            if let Some(d) = self.dead.take() {
                if let Some(composed) = compose(d, c) {
                    return Key::Char(composed);
                }
                // Não compõe: espaço confirma o símbolo; outra letra vem depois dele.
                if c != ' ' {
                    self.pending = Some(Key::Char(c));
                }
                return Key::Char(d);
            }
            if matches!(c, '\'' | '"' | '`' | '~' | '^') {
                self.dead = Some(c);
                continue;
            }
            return Key::Char(c);
        }
    }
}

fn compose(dead: char, c: char) -> Option<char> {
    Some(match (dead, c) {
        ('\'', 'a') => 'á', ('\'', 'e') => 'é', ('\'', 'i') => 'í', ('\'', 'o') => 'ó', ('\'', 'u') => 'ú',
        ('\'', 'A') => 'Á', ('\'', 'E') => 'É', ('\'', 'I') => 'Í', ('\'', 'O') => 'Ó', ('\'', 'U') => 'Ú',
        ('\'', 'c') => 'ç', ('\'', 'C') => 'Ç',
        ('~', 'a') => 'ã', ('~', 'o') => 'õ', ('~', 'A') => 'Ã', ('~', 'O') => 'Õ', ('~', 'n') => 'ñ',
        ('^', 'a') => 'â', ('^', 'e') => 'ê', ('^', 'o') => 'ô', ('^', 'A') => 'Â', ('^', 'E') => 'Ê',
        ('^', 'O') => 'Ô',
        ('`', 'a') => 'à', ('`', 'A') => 'À',
        ('"', 'u') => 'ü', ('"', 'U') => 'Ü',
        _ => return None,
    })
}
