//! Tabela de interrupções (IDT), exceções da CPU e o PIC 8259.
//!
//! Fase 1 usa o PIC legado (timer e teclado PS/2). O APIC entra
//! junto com o suporte a múltiplos núcleos.

use pic8259::ChainedPics;
use spin::{Lazy, Mutex};
use x86_64::structures::idt::{InterruptDescriptorTable, InterruptStackFrame, PageFaultErrorCode};

pub const PIC_1_OFFSET: u8 = 32;
pub const PIC_2_OFFSET: u8 = PIC_1_OFFSET + 8;

pub static PICS: Mutex<ChainedPics> =
    Mutex::new(unsafe { ChainedPics::new(PIC_1_OFFSET, PIC_2_OFFSET) });


#[derive(Clone, Copy)]
#[repr(u8)]
enum Irq {
    Timer = PIC_1_OFFSET,
    Keyboard = PIC_1_OFFSET + 1,
}

static IDT: Lazy<InterruptDescriptorTable> = Lazy::new(|| {
    let mut idt = InterruptDescriptorTable::new();
    idt.breakpoint.set_handler_fn(breakpoint);
    idt.page_fault.set_handler_fn(page_fault);
    idt.general_protection_fault.set_handler_fn(general_protection);
    unsafe {
        idt.double_fault
            .set_handler_fn(double_fault)
            .set_stack_index(crate::gdt::DOUBLE_FAULT_IST);
    }
    idt[Irq::Timer as u8].set_handler_fn(timer);
    idt[Irq::Keyboard as u8].set_handler_fn(keyboard);
    idt
});

pub fn init() {
    IDT.load();
    unsafe {
        let mut pics = PICS.lock();
        pics.initialize();
        // Libera só timer (IRQ0) e teclado (IRQ1).
        pics.write_masks(0b1111_1100, 0b1111_1111);
    }
}

extern "x86-interrupt" fn breakpoint(frame: InterruptStackFrame) {
    crate::log!("EXCEÇÃO: breakpoint\n{:#?}", frame);
}

extern "x86-interrupt" fn page_fault(frame: InterruptStackFrame, code: PageFaultErrorCode) {
    let addr = x86_64::registers::control::Cr2::read();
    panic!("falha de página em {:?} ({:?})\n{:#?}", addr, code, frame);
}

extern "x86-interrupt" fn general_protection(frame: InterruptStackFrame, code: u64) {
    panic!("falha de proteção geral (código {})\n{:#?}", code, frame);
}

extern "x86-interrupt" fn double_fault(frame: InterruptStackFrame, _code: u64) -> ! {
    panic!("falha dupla\n{:#?}", frame);
}

extern "x86-interrupt" fn timer(_frame: InterruptStackFrame) {
    crate::time::on_tick();
    unsafe { PICS.lock().notify_end_of_interrupt(Irq::Timer as u8) };
}

extern "x86-interrupt" fn keyboard(_frame: InterruptStackFrame) {
    let scancode: u8 = unsafe { x86_64::instructions::port::Port::new(0x60).read() };
    crate::keyboard::push_scancode(scancode);
    unsafe { PICS.lock().notify_end_of_interrupt(Irq::Keyboard as u8) };
}
