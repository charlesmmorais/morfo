//! Tempo: PIT a 1 kHz, relógio de boot e `sleep` assíncrono.

use alloc::vec::Vec;
use core::future::Future;
use core::pin::Pin;
use core::sync::atomic::{AtomicU64, Ordering};
use core::task::{Context, Poll, Waker};
use spin::Mutex;
use x86_64::instructions::port::Port;

pub const HZ: u64 = 1000;
static TICKS: AtomicU64 = AtomicU64::new(0);
static SLEEPERS: Mutex<Vec<(u64, Waker)>> = Mutex::new(Vec::new());

/// Programa o canal 0 do PIT para 1000 interrupções por segundo.
pub fn init() {
    let divisor: u16 = (1_193_182 / HZ) as u16;
    unsafe {
        Port::<u8>::new(0x43).write(0x36);
        let mut data = Port::<u8>::new(0x40);
        data.write((divisor & 0xFF) as u8);
        data.write((divisor >> 8) as u8);
    }
}

/// Chamado pela interrupção do timer.
pub fn on_tick() {
    let now = TICKS.fetch_add(1, Ordering::Relaxed) + 1;
    // try_lock: se o código principal estiver mexendo na lista, tenta no próximo tick.
    if let Some(mut s) = SLEEPERS.try_lock() {
        s.retain(|(deadline, waker)| {
            if *deadline <= now {
                waker.wake_by_ref();
                false
            } else {
                true
            }
        });
    }
}

pub fn ticks_ms() -> u64 {
    TICKS.load(Ordering::Relaxed)
}

pub fn uptime_secs() -> u64 {
    ticks_ms() / HZ
}

/// Espera `ms` milissegundos sem ocupar a CPU.
pub fn sleep_ms(ms: u64) -> Sleep {
    Sleep { deadline: ticks_ms() + ms.max(1) }
}

pub struct Sleep {
    deadline: u64,
}

impl Future for Sleep {
    type Output = ();
    fn poll(self: Pin<&mut Self>, cx: &mut Context) -> Poll<()> {
        if ticks_ms() >= self.deadline {
            return Poll::Ready(());
        }
        let waker = cx.waker().clone();
        let deadline = self.deadline;
        x86_64::instructions::interrupts::without_interrupts(|| SLEEPERS.lock().push((deadline, waker)));
        if ticks_ms() >= self.deadline { Poll::Ready(()) } else { Poll::Pending }
    }
}
