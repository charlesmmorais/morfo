//! Barramento PCI pelo mecanismo de configuração #1 (portas 0xCF8/0xCFC).

use alloc::vec::Vec;
use x86_64::instructions::port::Port;

#[derive(Clone, Copy, Debug)]
pub struct PciDevice {
    pub bus: u8,
    pub dev: u8,
    pub func: u8,
    pub vendor: u16,
    pub device: u16,
    pub class: u8,
    pub subclass: u8,
    pub prog_if: u8,
}

fn addr(bus: u8, dev: u8, func: u8, off: u8) -> u32 {
    0x8000_0000 | (bus as u32) << 16 | (dev as u32) << 11 | (func as u32) << 8 | (off as u32 & 0xFC)
}

pub fn read32(bus: u8, dev: u8, func: u8, off: u8) -> u32 {
    unsafe {
        Port::<u32>::new(0xCF8).write(addr(bus, dev, func, off));
        Port::<u32>::new(0xCFC).read()
    }
}

pub fn write32(bus: u8, dev: u8, func: u8, off: u8, val: u32) {
    unsafe {
        Port::<u32>::new(0xCF8).write(addr(bus, dev, func, off));
        Port::<u32>::new(0xCFC).write(val);
    }
}

impl PciDevice {
    pub fn read(&self, off: u8) -> u32 {
        read32(self.bus, self.dev, self.func, off)
    }

    pub fn write(&self, off: u8, val: u32) {
        write32(self.bus, self.dev, self.func, off, val)
    }

    /// Endereço físico de uma BAR de memória (32 ou 64 bits).
    pub fn bar_mem(&self, index: u8) -> u64 {
        let off = 0x10 + index * 4;
        let low = self.read(off);
        let base = (low & 0xFFFF_FFF0) as u64;
        if (low >> 1) & 0b11 == 0b10 {
            base | (self.read(off + 4) as u64) << 32
        } else {
            base
        }
    }

    /// Liga acesso à memória e "bus master" (o dispositivo faz DMA).
    pub fn enable_mmio_and_dma(&self) {
        let cmd = self.read(0x04);
        // Os 16 bits de cima (status) são "escreva 1 para limpar": vão zerados.
        self.write(0x04, (cmd & 0xFFFF) | 0b110);
    }
}

pub fn scan() -> Vec<PciDevice> {
    let mut out = Vec::new();
    for bus in 0..=255u8 {
        for dev in 0..32u8 {
            for func in 0..8u8 {
                let id = read32(bus, dev, func, 0);
                if id & 0xFFFF == 0xFFFF {
                    if func == 0 {
                        break;
                    }
                    continue;
                }
                let class = read32(bus, dev, func, 0x08);
                out.push(PciDevice {
                    bus,
                    dev,
                    func,
                    vendor: id as u16,
                    device: (id >> 16) as u16,
                    class: (class >> 24) as u8,
                    subclass: (class >> 16) as u8,
                    prog_if: (class >> 8) as u8,
                });
                // Dispositivo de função única: não varre as outras.
                if func == 0 && (read32(bus, dev, 0, 0x0C) >> 16) & 0x80 == 0 {
                    break;
                }
            }
        }
    }
    out
}
