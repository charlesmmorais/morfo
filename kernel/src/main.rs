//! Morfo — kernel experimental em Rust.
//!
//! Fase 1: boot pelo Limine, memória, interrupções, executor assíncrono
//! e o shell de chat desenhado direto no framebuffer.
//! Fase 2: PCI, USB 2.0 (EHCI), hubs e teclado USB.

#![no_std]
#![no_main]
#![feature(abi_x86_interrupt)]

extern crate alloc;

mod agent;
mod allocator;
mod gdt;
mod gfx;
mod interrupts;
mod keyboard;
mod memory;
mod pci;
mod serial;
mod shell;
mod task;
mod time;
mod usb;

use limine::request::{BootloaderInfoRequest, FramebufferRequest, HhdmRequest, MemmapRequest};
use limine::{BaseRevision, RequestsEndMarker, RequestsStartMarker};

// ---------------------------------------------------------------------------
// Pedidos ao bootloader (Limine). Ficam em seções próprias do binário.
// ---------------------------------------------------------------------------

#[used]
#[unsafe(link_section = ".limine_requests")]
static BASE_REVISION: BaseRevision = BaseRevision::with_revision(3);

#[used]
#[unsafe(link_section = ".limine_requests")]
static FRAMEBUFFER: FramebufferRequest = FramebufferRequest::new();

#[used]
#[unsafe(link_section = ".limine_requests")]
static HHDM: HhdmRequest = HhdmRequest::new();

#[used]
#[unsafe(link_section = ".limine_requests")]
static MEMMAP: MemmapRequest = MemmapRequest::new();

#[used]
#[unsafe(link_section = ".limine_requests")]
static BOOTLOADER: BootloaderInfoRequest = BootloaderInfoRequest::new();

#[used]
#[unsafe(link_section = ".limine_requests_start")]
static _START: RequestsStartMarker = RequestsStartMarker::new();

#[used]
#[unsafe(link_section = ".limine_requests_end")]
static _END: RequestsEndMarker = RequestsEndMarker::new();

/// Informações coletadas no boot, mostradas pelo agente.
pub struct BootInfo {
    pub total_ram: u64,
    pub usable_ram: u64,
    pub heap_size: usize,
    pub fb_width: u64,
    pub fb_height: u64,
    pub bootloader: &'static str,
}

pub static BOOT_INFO: spin::Once<BootInfo> = spin::Once::new();

#[unsafe(no_mangle)]
extern "C" fn kmain() -> ! {
    serial::init();
    log!("Morfo: iniciando");

    if !BASE_REVISION.is_supported() {
        log!("Morfo: revisão do protocolo Limine não suportada");
        halt();
    }

    // 1. Memória: o Limine mapeia toda a RAM física a partir do offset HHDM.
    let hhdm = HHDM.response().expect("sem HHDM").offset;
    let memmap = MEMMAP.response().expect("sem mapa de memória");
    let (total_ram, usable_ram, heap_size) = allocator::init(hhdm, memmap.entries());
    log!("Morfo: heap de {} MiB", heap_size / (1024 * 1024));

    // 2. CPU: segmentos, tabela de interrupções e controlador PIC.
    gdt::init();
    interrupts::init();
    time::init();
    keyboard::init();

    // 3. Tela.
    let fbs = FRAMEBUFFER.response().expect("sem framebuffer");
    let fb = fbs.framebuffers().first().expect("nenhum framebuffer");
    let (w, h) = (fb.width, fb.height);
    gfx::init(fb);
    log!("Morfo: framebuffer {}x{}", w, h);

    let bootloader = BOOTLOADER.response().map(|r| r.name()).unwrap_or("desconhecido");
    BOOT_INFO.call_once(|| BootInfo {
        total_ram,
        usable_ram,
        heap_size,
        fb_width: w,
        fb_height: h,
        bootloader,
    });

    // 4. Liga as interrupções e entrega o controle ao executor assíncrono.
    x86_64::instructions::interrupts::enable();

    let mut executor = task::Executor::new();
    executor.spawn(task::Task::new(shell::run()));
    executor.spawn(task::Task::new(keyboard::ps2_task()));
    executor.spawn(task::Task::new(usb::run()));
    executor.run()
}

pub fn halt() -> ! {
    loop {
        x86_64::instructions::hlt();
    }
}

#[panic_handler]
fn panic(info: &core::panic::PanicInfo) -> ! {
    x86_64::instructions::interrupts::disable();
    log!("PANIC: {}", info);
    gfx::panic_screen(info);
    halt()
}
