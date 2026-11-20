//! Log pela porta serial COM1. No QEMU aparece no terminal;
//! no Mac mini (sem porta serial) as escritas simplesmente se perdem.

use core::fmt::Write;
use spin::Mutex;
use uart_16550::SerialPort;

static SERIAL: Mutex<Option<SerialPort>> = Mutex::new(None);

pub fn init() {
    let mut port = unsafe { SerialPort::new(0x3F8) };
    port.init();
    *SERIAL.lock() = Some(port);
}

#[doc(hidden)]
pub fn _print(args: core::fmt::Arguments) {
    x86_64::instructions::interrupts::without_interrupts(|| {
        if let Some(port) = SERIAL.lock().as_mut() {
            let _ = port.write_fmt(args);
            let _ = port.write_str("\n");
        }
    });
}

#[macro_export]
macro_rules! log {
    ($($arg:tt)*) => { $crate::serial::_print(format_args!($($arg)*)) };
}
