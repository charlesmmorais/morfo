//! O agente: quem responde no chat.
//!
//! O "cérebro" é trocável por trás da trait `Agent`. Nesta fase ele é um
//! interpretador de intenções simples; depois virá um modelo remoto e,
//! no futuro, um modelo local. O shell não muda quando o cérebro muda.
//!
//! As respostas podem ser texto ou superfícies (cartões) — o embrião da
//! interface que se molda à tarefa.

use alloc::format;
use alloc::string::{String, ToString};
use alloc::vec;
use alloc::vec::Vec;

pub enum Reply {
    Text(String),
    Card { title: String, rows: Vec<(String, String)> },
    Clear,
}

pub trait Agent {
    fn name(&self) -> &str;
    fn respond(&mut self, input: &str) -> Vec<Reply>;
}

/// Capacidades que o agente recebeu nesta fase. No kernel definitivo
/// isto vira um conjunto de capabilities verificado pelo kernel.
const GRANTED: &[&str] = &["ler informações do sistema", "limpar a conversa"];

pub struct IntentAgent;

impl Agent for IntentAgent {
    fn name(&self) -> &str {
        "Morfo"
    }

    fn respond(&mut self, input: &str) -> Vec<Reply> {
        let q = normalize(input);
        // Frases casam por trecho; palavras soltas casam pelo início de cada palavra.
        let has = |words: &[&str]| {
            words.iter().any(|w| {
                if w.contains(' ') {
                    q.contains(w)
                } else {
                    q.split_whitespace().any(|t| t.starts_with(w))
                }
            })
        };

        if q.is_empty() {
            return vec![];
        }
        if has(&["limpa", "apaga a conversa", "clear"]) {
            return vec![Reply::Clear];
        }
        if has(&["ajuda", "help", "o que voce faz", "comandos"]) {
            return vec![text(
                "Ainda sou o cérebro inicial do Morfo: entendo pedidos simples. Experimente: \
                 \"memória\", \"sistema\", \"usb\", \"há quanto tempo estou ligado?\", \"permissões\", \
                 \"sobre\" ou \"limpar\".",
            )];
        }
        if has(&["usb", "dispositivo", "teclado"]) {
            return usb_cards();
        }
        if has(&["memoria", "ram"]) {
            return vec![memory_card()];
        }
        if has(&["sistema", "status", "info", "hardware"]) {
            return vec![system_card()];
        }
        if has(&["tempo", "uptime", "ligado"]) {
            return vec![text(&format!("Estou ligado há {}.", fmt_duration(crate::time::uptime_secs())))];
        }
        if has(&["permiss", "capabilit", "capacidade", "pode fazer"]) {
            let mut s = String::from("Nesta fase eu só posso: ");
            s.push_str(&GRANTED.join(", "));
            s.push_str(". Qualquer coisa além disso precisará de uma capability que você me conceder.");
            return vec![text(&s)];
        }
        if has(&["sobre", "quem e voce", "o que e o morfo", "morfo"]) {
            return vec![text(
                "Morfo é um sistema operacional experimental escrito do zero em Rust. A interface \
                 começa no chat e vai se moldar à tarefa: planilha, documento, web. Eu sou o agente \
                 que trabalha por você, sempre dentro das permissões que o kernel impõe.",
            )];
        }
        if has(&["oi", "ola", "bom dia", "boa tarde", "boa noite", "e ai"]) {
            return vec![text("Olá! Como posso ajudar? Digite \"ajuda\" para ver o que já sei fazer.")];
        }
        vec![text(
            "Ainda não entendo isso. Meu cérebro atual é só um interpretador simples; o modelo \
             de linguagem chega numa fase futura. Digite \"ajuda\".",
        )]
    }
}

fn text(s: &str) -> Reply {
    Reply::Text(s.to_string())
}

fn memory_card() -> Reply {
    let info = crate::BOOT_INFO.get().expect("boot info");
    let mib = |b: u64| format!("{} MiB", b / (1024 * 1024));
    Reply::Card {
        title: "Memória".to_string(),
        rows: vec![
            ("RAM do sistema".to_string(), mib(info.total_ram)),
            ("RAM livre no boot".to_string(), mib(info.usable_ram)),
            ("Heap do kernel".to_string(), mib(info.heap_size as u64)),
            ("Heap em uso".to_string(), format!("{} KiB", crate::allocator::used() / 1024)),
            ("DMA em uso".to_string(), format!("{} KiB", crate::memory::dma_used() / 1024)),
        ],
    }
}

fn system_card() -> Reply {
    let info = crate::BOOT_INFO.get().expect("boot info");
    Reply::Card {
        title: "Sistema".to_string(),
        rows: vec![
            ("Kernel".to_string(), format!("Morfo {}", env!("CARGO_PKG_VERSION"))),
            ("Bootloader".to_string(), info.bootloader.to_string()),
            ("Tela".to_string(), format!("{} × {}", info.fb_width, info.fb_height)),
            ("Ligado há".to_string(), fmt_duration(crate::time::uptime_secs())),
            ("Agente".to_string(), "interpretador de intenções".to_string()),
        ],
    }
}

pub fn usb_cards() -> Vec<Reply> {
    let r = crate::usb::REPORT.lock();
    let mut out = Vec::new();
    let mut rows: Vec<(String, String)> = Vec::new();
    for c in &r.controllers {
        rows.push(("Controlador".to_string(), c.clone()));
    }
    for d in &r.devices {
        match d.split_once(": ") {
            Some((place, desc)) => rows.push((place.to_string(), desc.to_string())),
            None => rows.push(("Dispositivo".to_string(), d.clone())),
        }
    }
    if rows.is_empty() {
        rows.push(("Estado".to_string(), "nada encontrado ainda".to_string()));
    }
    out.push(Reply::Card { title: format!("USB · {} teclado(s)", r.keyboards), rows });
    if !r.log.is_empty() {
        let mut s = String::from("Registro do USB: ");
        s.push_str(&r.log.join(" | "));
        out.push(Reply::Text(s));
    }
    out
}

fn fmt_duration(secs: u64) -> String {
    let (h, m, s) = (secs / 3600, (secs / 60) % 60, secs % 60);
    if h > 0 {
        format!("{h} h {m} min")
    } else if m > 0 {
        format!("{m} min {s} s")
    } else {
        format!("{s} s")
    }
}

/// Minúsculas, sem acentos e sem pontuação — para casar intenções.
fn normalize(input: &str) -> String {
    input
        .chars()
        .map(|c| match c {
            'á' | 'à' | 'â' | 'ã' | 'Á' | 'À' | 'Â' | 'Ã' => 'a',
            'é' | 'ê' | 'É' | 'Ê' => 'e',
            'í' | 'Í' => 'i',
            'ó' | 'ô' | 'õ' | 'Ó' | 'Ô' | 'Õ' => 'o',
            'ú' | 'Ú' => 'u',
            'ç' | 'Ç' => 'c',
            c if c.is_ascii_punctuation() => ' ',
            c => c.to_ascii_lowercase(),
        })
        .collect::<String>()
        .trim()
        .to_string()
}
