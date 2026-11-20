//! Controlador USB 2.0 (EHCI).
//!
//! Só usa a fila assíncrona (transferências de controle). O teclado é lido
//! por GET_REPORT periódico, o que evita a fila periódica nesta fase.
//! Dispositivos full/low-speed atrás de um hub USB 2.0 usam transações
//! "split" pelo Transaction Translator do hub — é o caso do Mac mini 2011,
//! cujas portas passam pelo hub interno do chipset Intel.

use alloc::vec::Vec;
use core::ptr::{read_volatile, write_volatile};
use core::sync::atomic::{Ordering, fence};

use crate::memory::{DmaBuf, dma_alloc, map_mmio};
use crate::pci::PciDevice;
use crate::time::{sleep_ms, ticks_ms};

// Registradores operacionais (deslocamento a partir de CAPLENGTH).
const USBCMD: usize = 0x00;
const USBSTS: usize = 0x04;
const USBINTR: usize = 0x08;
const CTRLDSSEGMENT: usize = 0x10;
const PERIODICLISTBASE: usize = 0x14;
const ASYNCLISTADDR: usize = 0x18;
const CONFIGFLAG: usize = 0x40;
const PORTSC: usize = 0x44;

const CMD_RUN: u32 = 1 << 0;
const CMD_RESET: u32 = 1 << 1;
const CMD_ASYNC: u32 = 1 << 5;
const STS_HALTED: u32 = 1 << 12;

const PORT_CONNECT: u32 = 1 << 0;
const PORT_ENABLED: u32 = 1 << 2;
const PORT_RESET: u32 = 1 << 8;
const PORT_POWER: u32 = 1 << 12;
const PORT_OWNER: u32 = 1 << 13;
/// Bits "escreva 1 para limpar" que não podem ser regravados sem querer.
const PORT_RWC: u32 = (1 << 1) | (1 << 3) | (1 << 5);

const TERMINATE: u32 = 1;
const TYPE_QH: u32 = 1 << 1;

const TOK_ACTIVE: u32 = 1 << 7;
const TOK_HALTED: u32 = 1 << 6;
const TOK_ERRORS: u32 = 0b0111_1100; // halted, buffer, babble, xact, missed µframe
const PID_OUT: u32 = 0;
const PID_IN: u32 = 1;
const PID_SETUP: u32 = 2;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Speed {
    Full,
    Low,
    High,
}

impl Speed {
    pub fn name(self) -> &'static str {
        match self {
            Speed::Full => "full-speed",
            Speed::Low => "low-speed",
            Speed::High => "high-speed",
        }
    }
}

/// Onde fica o Transaction Translator usado por um dispositivo FS/LS.
#[derive(Clone, Copy, Debug)]
pub struct Tt {
    pub hub_addr: u8,
    pub port: u8,
}

#[derive(Debug)]
#[allow(dead_code)] // o código do erro aparece no registro via Debug
pub enum UsbError {
    Timeout,
    Stall,
    Transaction(u32),
}

pub struct Ehci {
    op: *mut u8,
    pub ports: usize,
    async_head: DmaBuf,
}

unsafe impl Send for Ehci {}

/// Canal de controle de um dispositivo: um QH fixo na fila assíncrona,
/// três qTDs e buffers reutilizados em toda transferência.
pub struct ControlPipe {
    qh: DmaBuf,
    tds: [DmaBuf; 3],
    setup: DmaBuf,
    pub data: DmaBuf,
    pub addr: u8,
    pub speed: Speed,
    pub tt: Option<Tt>,
    pub max_packet: u16,
}

unsafe impl Send for ControlPipe {}

#[inline]
fn rd(buf: &DmaBuf, dword: usize) -> u32 {
    unsafe { read_volatile((buf.virt as *const u32).add(dword)) }
}

#[inline]
fn wr(buf: &DmaBuf, dword: usize, v: u32) {
    unsafe { write_volatile((buf.virt as *mut u32).add(dword), v) }
}

impl Ehci {
    fn reg(&self, off: usize) -> u32 {
        unsafe { read_volatile(self.op.add(off) as *const u32) }
    }

    fn set(&self, off: usize, v: u32) {
        unsafe { write_volatile(self.op.add(off) as *mut u32, v) }
    }

    fn portsc(&self, port: usize) -> u32 {
        self.reg(PORTSC + 4 * port)
    }

    fn set_portsc(&self, port: usize, v: u32) {
        self.set(PORTSC + 4 * port, v);
    }

    /// Assume o controlador: tira do firmware, reseta e liga a fila assíncrona.
    pub async fn init(pci: &PciDevice, log: &mut Vec<alloc::string::String>) -> Option<Ehci> {
        use alloc::format;
        pci.enable_mmio_and_dma();
        let bar = pci.bar_mem(0);
        let base = map_mmio(bar, 0x1000);
        let caplen = unsafe { read_volatile(base) } as usize;
        let hcs = unsafe { read_volatile(base.add(4) as *const u32) };
        let hcc = unsafe { read_volatile(base.add(8) as *const u32) };
        let ports = (hcs & 0xF) as usize;
        let op = unsafe { base.add(caplen) };

        // 1. Handoff: pede ao firmware (SMM) que solte o controlador.
        let eecp = ((hcc >> 8) & 0xFF) as u8;
        if eecp >= 0x40 {
            let legsup = pci.read(eecp);
            if legsup & 0xFF == 1 {
                pci.write(eecp, legsup | (1 << 24));
                let start = ticks_ms();
                while pci.read(eecp) & (1 << 16) != 0 {
                    if ticks_ms() - start > 1000 {
                        log.push(format!("EHCI: firmware não soltou o controlador; forçando"));
                        pci.write(eecp, (pci.read(eecp) & !(1 << 16)) | (1 << 24));
                        break;
                    }
                    sleep_ms(5).await;
                }
                // Desliga as interrupções SMI do modo legado.
                pci.write(eecp + 4, 0);
            }
        }

        let hc = Ehci { op, ports, async_head: dma_alloc(64, 64) };

        // 2. Para e reseta.
        hc.set(USBCMD, hc.reg(USBCMD) & !CMD_RUN);
        let start = ticks_ms();
        while hc.reg(USBSTS) & STS_HALTED == 0 {
            if ticks_ms() - start > 100 {
                break;
            }
            sleep_ms(1).await;
        }
        hc.set(USBCMD, CMD_RESET);
        let start = ticks_ms();
        while hc.reg(USBCMD) & CMD_RESET != 0 {
            if ticks_ms() - start > 500 {
                log.push(format!("EHCI: reset não terminou"));
                return None;
            }
            sleep_ms(1).await;
        }

        // 3. Estruturas: lista periódica vazia e QH "cabeça" da fila assíncrona.
        if hcc & 1 != 0 {
            hc.set(CTRLDSSEGMENT, 0);
        }
        hc.set(USBINTR, 0);
        let periodic = dma_alloc(4096, 4096);
        for i in 0..1024 {
            wr(&periodic, i, TERMINATE);
        }
        hc.set(PERIODICLISTBASE, periodic.phys32());

        let head = hc.async_head;
        wr(&head, 0, head.phys32() | TYPE_QH); // aponta para si mesmo
        wr(&head, 1, 1 << 15); // H: cabeça da lista
        wr(&head, 4, TERMINATE);
        wr(&head, 5, TERMINATE);
        wr(&head, 6, TOK_HALTED);
        fence(Ordering::SeqCst);
        hc.set(ASYNCLISTADDR, head.phys32());

        // 4. Liga, com limiar de interrupção de 8 microframes.
        hc.set(USBCMD, (8 << 16) | CMD_ASYNC | CMD_RUN);
        hc.set(CONFIGFLAG, 1); // todas as portas passam a ser do EHCI
        sleep_ms(10).await;

        // 5. Energia nas portas.
        if hcs & (1 << 4) != 0 {
            for p in 0..ports {
                let v = hc.portsc(p) & !PORT_RWC;
                hc.set_portsc(p, v | PORT_POWER);
            }
            sleep_ms(30).await;
        }
        Some(hc)
    }

    /// Reseta a porta raiz. Devolve a velocidade se um dispositivo
    /// high-speed ficou habilitado (FS/LS direto na raiz não é suportado:
    /// iria para um controlador companheiro, que o Mac mini 2011 não tem).
    pub async fn reset_port(&self, port: usize) -> Option<Speed> {
        let sc = self.portsc(port);
        if sc & PORT_CONNECT == 0 {
            return None;
        }
        let line = (sc >> 10) & 0b11;
        if line == 0b01 {
            // Estado K: dispositivo low-speed direto na raiz.
            self.set_portsc(port, (sc & !PORT_RWC) | PORT_OWNER);
            return None;
        }
        let v = (sc & !PORT_RWC & !PORT_ENABLED) | PORT_RESET;
        self.set_portsc(port, v);
        sleep_ms(50).await;
        self.set_portsc(port, self.portsc(port) & !PORT_RWC & !PORT_RESET);
        let start = ticks_ms();
        while self.portsc(port) & PORT_RESET != 0 {
            if ticks_ms() - start > 100 {
                return None;
            }
            sleep_ms(1).await;
        }
        sleep_ms(10).await;
        let sc = self.portsc(port);
        // Limpa os bits de mudança.
        self.set_portsc(port, sc);
        if sc & PORT_ENABLED != 0 { Some(Speed::High) } else { None }
    }

    pub fn port_connected(&self, port: usize) -> bool {
        self.portsc(port) & PORT_CONNECT != 0
    }

    /// Cria o canal de controle para um dispositivo (endereço 0 até SET_ADDRESS)
    /// e o encaixa na fila assíncrona.
    pub fn new_pipe(&self, speed: Speed, tt: Option<Tt>) -> ControlPipe {
        let pipe = ControlPipe {
            qh: dma_alloc(96, 64),
            tds: [dma_alloc(64, 64), dma_alloc(64, 64), dma_alloc(64, 64)],
            setup: dma_alloc(8, 32),
            data: dma_alloc(4096, 4096),
            addr: 0,
            speed,
            tt,
            max_packet: if speed == Speed::High { 64 } else { 8 },
        };
        pipe.write_qh_endpoint();
        wr(&pipe.qh, 4, TERMINATE);
        wr(&pipe.qh, 5, TERMINATE);
        wr(&pipe.qh, 6, 0);
        // Insere logo após a cabeça.
        fence(Ordering::SeqCst);
        wr(&pipe.qh, 0, rd(&self.async_head, 0));
        fence(Ordering::SeqCst);
        wr(&self.async_head, 0, pipe.qh.phys32() | TYPE_QH);
        fence(Ordering::SeqCst);
        pipe
    }

    /// Transferência de controle. `data_out` envia dados; senão, `len` bytes
    /// são lidos para `pipe.data`. Retorna quantos bytes vieram.
    pub async fn control(
        &self,
        pipe: &ControlPipe,
        setup: [u8; 8],
        len: usize,
        data_out: Option<&[u8]>,
    ) -> Result<usize, UsbError> {
        let dir_in = setup[0] & 0x80 != 0;
        unsafe { core::ptr::copy_nonoverlapping(setup.as_ptr(), pipe.setup.virt, 8) };
        if let Some(d) = data_out {
            unsafe { core::ptr::copy_nonoverlapping(d.as_ptr(), pipe.data.virt, d.len()) };
        }
        let len = len.min(4096);
        let token = |pid: u32, bytes: usize, toggle: u32, ioc: bool| {
            (toggle << 31) | ((bytes as u32) << 16) | ((ioc as u32) << 15) | (3 << 10) | (pid << 8) | TOK_ACTIVE
        };

        let [td_setup, td_data, td_status] = &pipe.tds;
        let has_data = len > 0;
        let status_td = if has_data { td_status } else { td_data };

        // SETUP
        wr(td_setup, 0, if has_data { td_data.phys32() } else { status_td.phys32() });
        wr(td_setup, 1, TERMINATE);
        wr(td_setup, 3, pipe.setup.phys32());
        for i in 4..8 {
            wr(td_setup, i, 0);
        }
        // DADOS
        if has_data {
            wr(td_data, 0, td_status.phys32());
            // Pacote curto (resposta menor que o pedido) também segue para o STATUS.
            wr(td_data, 1, td_status.phys32());
            wr(td_data, 2, token(if dir_in { PID_IN } else { PID_OUT }, len, 1, false));
            wr(td_data, 3, pipe.data.phys32());
            for i in 4..8 {
                wr(td_data, i, 0);
            }
        }
        // STATUS: direção oposta ao dado (IN se não houver dado).
        let status_pid = if has_data && dir_in { PID_OUT } else { PID_IN };
        wr(status_td, 0, TERMINATE);
        wr(status_td, 1, TERMINATE);
        wr(status_td, 2, token(status_pid, 0, 1, true));
        for i in 3..8 {
            wr(status_td, i, 0);
        }
        wr(td_setup, 2, token(PID_SETUP, 8, 0, false));

        // Entrega a cadeia ao QH (que está ocioso).
        fence(Ordering::SeqCst);
        wr(&pipe.qh, 6, 0);
        wr(&pipe.qh, 5, TERMINATE);
        wr(&pipe.qh, 4, td_setup.phys32());
        fence(Ordering::SeqCst);

        let start = ticks_ms();
        loop {
            let st = rd(status_td, 2);
            let errs = [rd(td_setup, 2), if has_data { rd(td_data, 2) } else { 0 }, st];
            if let Some(e) = errs.iter().find(|t| *t & TOK_HALTED != 0) {
                self.unlink_chain(pipe);
                return Err(if e & (TOK_ERRORS & !TOK_HALTED) == 0 {
                    UsbError::Stall
                } else {
                    UsbError::Transaction(*e)
                });
            }
            if st & TOK_ACTIVE == 0 {
                break;
            }
            if ticks_ms() - start > 500 {
                self.unlink_chain(pipe);
                return Err(UsbError::Timeout);
            }
            sleep_ms(1).await;
        }
        fence(Ordering::SeqCst);
        let got = if has_data { len - ((rd(td_data, 2) >> 16) & 0x7FFF) as usize } else { 0 };
        Ok(got)
    }

    /// Desativa a cadeia após erro, deixando o QH ocioso para a próxima.
    fn unlink_chain(&self, pipe: &ControlPipe) {
        for td in &pipe.tds {
            wr(td, 2, rd(td, 2) & !TOK_ACTIVE);
        }
        wr(&pipe.qh, 4, TERMINATE);
        wr(&pipe.qh, 6, 0);
        fence(Ordering::SeqCst);
    }
}

impl ControlPipe {
    /// Grava as características do endpoint 0 no QH.
    pub fn write_qh_endpoint(&self) {
        let eps = match self.speed {
            Speed::Full => 0,
            Speed::Low => 1,
            Speed::High => 2,
        };
        let not_hs = self.speed != Speed::High;
        let nak_reload = if not_hs { 0 } else { 4 };
        let chars = (nak_reload << 28)
            | ((not_hs as u32) << 27) // C: endpoint de controle não high-speed
            | ((self.max_packet as u32) << 16)
            | (1 << 14) // DTC: toggle vem de cada qTD
            | (eps << 12)
            | self.addr as u32;
        wr(&self.qh, 1, chars);
        let caps = match (not_hs, self.tt) {
            (true, Some(tt)) => (1 << 30) | ((tt.port as u32) << 23) | ((tt.hub_addr as u32) << 16),
            _ => 1 << 30,
        };
        wr(&self.qh, 2, caps);
        fence(Ordering::SeqCst);
    }
}
