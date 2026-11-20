//! Pilha USB: acha controladores EHCI, enumera dispositivos (passando por
//! hubs) e liga o teclado HID. Tudo roda como uma tarefa assíncrona.

pub mod ehci;
mod hid;

use alloc::boxed::Box;
use alloc::format;
use alloc::string::String;
use alloc::sync::Arc;
use alloc::vec::Vec;
use core::future::Future;
use core::pin::Pin;
use spin::Mutex;

use ehci::{ControlPipe, Ehci, Speed, Tt};

/// O que a pilha USB encontrou — mostrado pelo agente no comando "usb".
pub struct UsbReport {
    pub controllers: Vec<String>,
    pub devices: Vec<String>,
    pub log: Vec<String>,
    pub keyboards: usize,
}

pub static REPORT: Mutex<UsbReport> = Mutex::new(UsbReport {
    controllers: Vec::new(),
    devices: Vec::new(),
    log: Vec::new(),
    keyboards: 0,
});

fn note(msg: String) {
    crate::log!("usb: {}", msg);
    let mut r = REPORT.lock();
    if r.log.len() < 40 {
        r.log.push(msg);
    }
}

struct Bus {
    hc: Ehci,
    next_addr: Mutex<u8>,
}

/// Ponto de entrada: tarefa assíncrona disparada no boot.
pub async fn run() {
    let pci = crate::pci::scan();
    let ehcis: Vec<_> = pci
        .iter()
        .filter(|d| d.class == 0x0C && d.subclass == 0x03 && d.prog_if == 0x20)
        .copied()
        .collect();
    let others = pci.iter().filter(|d| d.class == 0x0C && d.subclass == 0x03 && d.prog_if != 0x20).count();
    if others > 0 {
        note(format!("{others} controlador(es) USB de outro tipo (UHCI/OHCI/xHCI) ignorado(s)"));
    }
    if ehcis.is_empty() {
        note(String::from("nenhum controlador EHCI encontrado"));
        finish();
        return;
    }

    for dev in ehcis {
        let mut log = Vec::new();
        let hc = Ehci::init(&dev, &mut log).await;
        for l in log {
            note(l);
        }
        let Some(hc) = hc else { continue };
        REPORT.lock().controllers.push(format!(
            "EHCI {:04x}:{:04x} em {:02x}:{:02x}.{} ({} portas)",
            dev.vendor, dev.device, dev.bus, dev.dev, dev.func, hc.ports
        ));
        let bus = Arc::new(Bus { hc, next_addr: Mutex::new(1) });
        for port in 0..bus.hc.ports {
            if !bus.hc.port_connected(port) {
                continue;
            }
            match bus.hc.reset_port(port).await {
                Some(speed) => enumerate(bus.clone(), speed, None, 0, format!("raiz {}", port + 1)).await,
                None => note(format!("porta raiz {}: dispositivo não high-speed ignorado", port + 1)),
            }
        }
    }
    finish();
}

/// Publica o resultado no chat: no Mac mini não há porta serial, e se o
/// teclado falhar o usuário não conseguiria nem pedir o diagnóstico.
fn finish() {
    if REPORT.lock().keyboards == 0 {
        note(String::from("nenhum teclado USB encontrado"));
    }
    crate::shell::notify(crate::agent::usb_cards());
}

/// Configura um dispositivo recém-resetado e, conforme a classe, liga o
/// driver de hub ou de teclado. Recursiva (hubs dentro de hubs).
fn enumerate(
    bus: Arc<Bus>,
    speed: Speed,
    tt: Option<Tt>,
    depth: u8,
    place: String,
) -> Pin<Box<dyn Future<Output = ()>>> {
    Box::pin(async move {
        if depth > 5 {
            return;
        }
        let hc = &bus.hc;
        let mut pipe = hc.new_pipe(speed, tt);

        // Primeiros 8 bytes do descritor: tamanho máximo de pacote do EP0.
        let get_dev = [0x80, 6, 0, 1, 0, 0, 8, 0];
        if let Err(e) = hc.control(&pipe, get_dev, 8, None).await {
            note(format!("{place}: falha ao ler descritor ({e:?}, {})", speed.name()));
            return;
        }
        let mps = unsafe { *pipe.data.virt.add(7) };
        if mps > 0 {
            pipe.max_packet = mps as u16;
        }

        let addr = {
            let mut n = bus.next_addr.lock();
            let a = *n;
            *n = n.wrapping_add(1).max(1);
            a
        };
        if let Err(e) = hc.control(&pipe, [0, 5, addr, 0, 0, 0, 0, 0], 0, None).await {
            note(format!("{place}: SET_ADDRESS falhou ({e:?})"));
            return;
        }
        crate::time::sleep_ms(10).await;
        pipe.addr = addr;
        pipe.write_qh_endpoint();

        let Ok(n) = hc.control(&pipe, [0x80, 6, 0, 1, 0, 0, 18, 0], 18, None).await else {
            note(format!("{place}: descritor completo falhou"));
            return;
        };
        let d = unsafe { core::slice::from_raw_parts(pipe.data.virt, n) };
        if n < 18 {
            return;
        }
        let dev_class = d[4];
        let vendor = u16::from_le_bytes([d[8], d[9]]);
        let product = u16::from_le_bytes([d[10], d[11]]);

        // Configuração: cabeçalho e depois inteira.
        let Ok(_) = hc.control(&pipe, [0x80, 6, 0, 2, 0, 0, 9, 0], 9, None).await else { return };
        let total = unsafe { u16::from_le_bytes([*pipe.data.virt.add(2), *pipe.data.virt.add(3)]) } as usize;
        let total = total.min(1024);
        let Ok(n) = hc.control(&pipe, [0x80, 6, 0, 2, 0, 0, total as u8, (total >> 8) as u8], total, None).await
        else {
            return;
        };
        let cfg: Vec<u8> = unsafe { core::slice::from_raw_parts(pipe.data.virt, n) }.to_vec();
        if cfg.len() < 9 {
            return;
        }
        let cfg_value = cfg[5];

        // Interfaces que interessam.
        let mut is_hub = dev_class == 9;
        let mut keyboard_iface = None;
        let mut i = 0;
        while i + 1 < cfg.len() {
            let len = cfg[i] as usize;
            if len == 0 {
                break;
            }
            if cfg[i + 1] == 4 && i + 8 < cfg.len() {
                let (class, sub, proto) = (cfg[i + 5], cfg[i + 6], cfg[i + 7]);
                if class == 9 {
                    is_hub = true;
                }
                if class == 3 && sub == 1 && proto == 1 && keyboard_iface.is_none() {
                    keyboard_iface = Some(cfg[i + 2]);
                }
            }
            i += len;
        }

        let kind = if is_hub {
            "hub"
        } else if keyboard_iface.is_some() {
            "teclado"
        } else {
            "outro"
        };
        REPORT.lock().devices.push(format!(
            "{place}: {vendor:04x}:{product:04x} {kind} ({}, endereço {addr})",
            speed.name()
        ));

        if hc.control(&pipe, [0, 9, cfg_value, 0, 0, 0, 0, 0], 0, None).await.is_err() {
            note(format!("{place}: SET_CONFIGURATION falhou"));
            return;
        }

        if is_hub {
            hub(bus.clone(), pipe, tt, depth, place).await;
        } else if let Some(iface) = keyboard_iface {
            REPORT.lock().keyboards += 1;
            // O teclado fica em laço para sempre: roda como tarefa própria.
            crate::task::spawn(hid::keyboard(bus, pipe, iface, place));
        }
    })
}

/// Driver de hub: liga as portas, reseta e enumera o que estiver conectado.
async fn hub(bus: Arc<Bus>, pipe: ControlPipe, parent_tt: Option<Tt>, depth: u8, place: String) {
    let hc = &bus.hc;
    let Ok(n) = hc.control(&pipe, [0xA0, 6, 0, 0x29, 0, 0, 16, 0], 16, None).await else {
        note(format!("{place}: descritor de hub falhou"));
        return;
    };
    if n < 7 {
        return;
    }
    let (ports, power_delay) = unsafe { (*pipe.data.virt.add(2), *pipe.data.virt.add(5) as u64 * 2) };

    for p in 1..=ports {
        // SET_FEATURE(PORT_POWER)
        let _ = hc.control(&pipe, [0x23, 3, 8, 0, p, 0, 0, 0], 0, None).await;
    }
    crate::time::sleep_ms(power_delay.max(100) + 100).await;

    for p in 1..=ports {
        let Some(status) = port_status(hc, &pipe, p).await else { continue };
        if status & 1 == 0 {
            continue; // nada conectado
        }
        // SET_FEATURE(PORT_RESET) e espera terminar.
        let _ = hc.control(&pipe, [0x23, 3, 4, 0, p, 0, 0, 0], 0, None).await;
        let mut status = 0;
        for _ in 0..50 {
            crate::time::sleep_ms(10).await;
            status = port_status(hc, &pipe, p).await.unwrap_or(0);
            if status & (1 << 4) == 0 {
                break;
            }
        }
        // Limpa C_PORT_RESET e C_PORT_CONNECTION.
        let _ = hc.control(&pipe, [0x23, 1, 20, 0, p, 0, 0, 0], 0, None).await;
        let _ = hc.control(&pipe, [0x23, 1, 16, 0, p, 0, 0, 0], 0, None).await;
        crate::time::sleep_ms(20).await;
        if status & (1 << 1) == 0 {
            note(format!("{place}, porta {p}: não habilitou após reset"));
            continue;
        }
        let speed = if status & (1 << 10) != 0 {
            Speed::High
        } else if status & (1 << 9) != 0 {
            Speed::Low
        } else {
            Speed::Full
        };
        // Dispositivo FS/LS: usa o TT deste hub se ele for high-speed;
        // senão herda o TT de cima.
        let tt = if speed == Speed::High {
            None
        } else if pipe.speed == Speed::High {
            Some(Tt { hub_addr: pipe.addr, port: p })
        } else {
            parent_tt
        };
        let child_place = format!("{place} › {p}");
        enumerate(bus.clone(), speed, tt, depth + 1, child_place).await;
    }
}

async fn port_status(hc: &Ehci, pipe: &ControlPipe, port: u8) -> Option<u16> {
    let n = hc.control(pipe, [0xA3, 0, 0, 0, port, 0, 4, 0], 4, None).await.ok()?;
    if n < 2 {
        return None;
    }
    Some(unsafe { u16::from_le_bytes([*pipe.data.virt, *pipe.data.virt.add(1)]) })
}
