//! Heap do kernel e reserva de memória para DMA.
//!
//! O heap usa a maior região livre da RAM, acessada pelo mapeamento direto
//! (HHDM) que o Limine prepara. Uma faixa abaixo de 4 GiB fica separada para
//! DMA, porque nem todo controlador enxerga endereços de 64 bits.

use limine::memmap::{
    Entry, MEMMAP_ACPI_RECLAIMABLE, MEMMAP_BOOTLOADER_RECLAIMABLE, MEMMAP_EXECUTABLE_AND_MODULES,
    MEMMAP_USABLE,
};
use linked_list_allocator::LockedHeap;

#[global_allocator]
static ALLOCATOR: LockedHeap = LockedHeap::empty();

/// Tamanho máximo do heap nesta fase.
const MAX_HEAP: u64 = 128 * 1024 * 1024;
/// Reserva de DMA (estruturas USB, tabelas de páginas novas).
pub const DMA_SIZE: u64 = 4 * 1024 * 1024;
const FOUR_GIB: u64 = 1 << 32;

/// Retorna (RAM do sistema, RAM livre, tamanho do heap).
pub fn init(hhdm: u64, entries: &[&Entry]) -> (u64, u64, usize) {
    let mut total = 0;
    let mut usable = 0;
    let mut best: Option<&Entry> = None;
    let mut dma_region: Option<&Entry> = None;

    for e in entries {
        // Conta só RAM de verdade (exclui regiões reservadas e de dispositivos).
        if matches!(
            e.type_,
            MEMMAP_USABLE | MEMMAP_BOOTLOADER_RECLAIMABLE | MEMMAP_EXECUTABLE_AND_MODULES | MEMMAP_ACPI_RECLAIMABLE
        ) {
            total += e.length;
        }
        if e.type_ == MEMMAP_USABLE {
            usable += e.length;
            if best.is_none_or(|b| e.length > b.length) {
                best = Some(e);
            }
            let fits_low = e.base + e.length <= FOUR_GIB && e.length >= DMA_SIZE * 2;
            if fits_low && dma_region.is_none_or(|d| e.length > d.length) {
                dma_region = Some(e);
            }
        }
    }

    let heap_region = best.expect("nenhuma região de memória livre");
    let dma_region = dma_region.expect("nenhuma região abaixo de 4 GiB para DMA");

    // A DMA fica no fim da sua região; se for a mesma do heap, o heap encolhe.
    let dma_phys = (dma_region.base + dma_region.length - DMA_SIZE) & !0xFFF;
    crate::memory::init_dma(hhdm, dma_phys, DMA_SIZE);

    let mut heap_len = heap_region.length;
    if core::ptr::eq(heap_region, dma_region) {
        heap_len = dma_phys - heap_region.base;
    }
    let size = heap_len.min(MAX_HEAP) as usize;
    let start = (hhdm + heap_region.base) as *mut u8;
    unsafe { ALLOCATOR.lock().init(start, size) };
    (total, usable, size)
}

pub fn used() -> usize {
    ALLOCATOR.lock().used()
}
