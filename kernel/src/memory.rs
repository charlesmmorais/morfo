//! Memória para dispositivos: reserva de DMA e mapeamento de MMIO.

use core::sync::atomic::{AtomicU64, Ordering};
use spin::Mutex;
use x86_64::structures::paging::{
    FrameAllocator, Mapper, OffsetPageTable, Page, PageTable, PageTableFlags, PhysFrame, Size4KiB,
    Translate,
};
use x86_64::{PhysAddr, VirtAddr};

static HHDM: AtomicU64 = AtomicU64::new(0);

struct Dma {
    next: u64,
    end: u64,
}

static DMA: Mutex<Dma> = Mutex::new(Dma { next: 0, end: 0 });

pub fn init_dma(hhdm: u64, phys: u64, size: u64) {
    HHDM.store(hhdm, Ordering::Relaxed);
    *DMA.lock() = Dma { next: phys, end: phys + size };
}

pub fn hhdm() -> u64 {
    HHDM.load(Ordering::Relaxed)
}

/// Bloco de memória física contígua, zerada, abaixo de 4 GiB.
/// Nesta fase a DMA nunca é devolvida: os drivers alocam uma vez e reutilizam.
#[derive(Clone, Copy)]
pub struct DmaBuf {
    pub phys: u64,
    pub virt: *mut u8,
    #[allow(dead_code)]
    pub len: usize,
}

unsafe impl Send for DmaBuf {}
unsafe impl Sync for DmaBuf {}

impl DmaBuf {
    pub fn phys32(&self) -> u32 {
        self.phys as u32
    }
}

pub fn dma_alloc(len: usize, align: usize) -> DmaBuf {
    let mut d = DMA.lock();
    let align = align.max(16) as u64;
    let start = (d.next + align - 1) & !(align - 1);
    let end = start + len as u64;
    assert!(end <= d.end, "reserva de DMA esgotada");
    d.next = end;
    let virt = (hhdm() + start) as *mut u8;
    unsafe { core::ptr::write_bytes(virt, 0, len) };
    DmaBuf { phys: start, virt, len }
}

pub fn dma_used() -> u64 {
    let d = DMA.lock();
    crate::allocator::DMA_SIZE - (d.end - d.next)
}

struct DmaFrames;

unsafe impl FrameAllocator<Size4KiB> for DmaFrames {
    fn allocate_frame(&mut self) -> Option<PhysFrame> {
        let b = dma_alloc(4096, 4096);
        Some(PhysFrame::containing_address(PhysAddr::new(b.phys)))
    }
}

static MAPPER_LOCK: Mutex<()> = Mutex::new(());

/// Mapeia registradores de um dispositivo (MMIO) sem cache e devolve o
/// endereço virtual. Usa o mesmo esquema do HHDM: virtual = HHDM + físico.
pub fn map_mmio(phys: u64, len: usize) -> *mut u8 {
    let _guard = MAPPER_LOCK.lock();
    let hhdm = hhdm();
    let mut mapper = unsafe {
        let (l4_frame, _) = x86_64::registers::control::Cr3::read();
        let l4 = &mut *((hhdm + l4_frame.start_address().as_u64()) as *mut PageTable);
        OffsetPageTable::new(l4, VirtAddr::new(hhdm))
    };

    let first = phys & !0xFFF;
    let last = (phys + len as u64 - 1) & !0xFFF;
    let flags = PageTableFlags::PRESENT
        | PageTableFlags::WRITABLE
        | PageTableFlags::NO_CACHE
        | PageTableFlags::WRITE_THROUGH
        | PageTableFlags::NO_EXECUTE;

    let mut p = first;
    while p <= last {
        let virt = VirtAddr::new(hhdm + p);
        if mapper.translate_addr(virt).is_none() {
            let page: Page<Size4KiB> = Page::containing_address(virt);
            let frame = PhysFrame::containing_address(PhysAddr::new(p));
            unsafe {
                mapper
                    .map_to(page, frame, flags, &mut DmaFrames)
                    .expect("falha ao mapear MMIO")
                    .flush();
            }
        }
        p += 4096;
    }
    (hhdm + phys) as *mut u8
}
