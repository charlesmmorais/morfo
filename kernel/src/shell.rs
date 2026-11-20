//! Shell de chat — a interface única do Morfo.
//!
//! Desenha a conversa (balões e cartões) e a caixa de entrada. Cada
//! resposta do agente pode ser texto ou uma superfície; nesta fase a
//! única superfície é o cartão, mas é aqui que a planilha, o documento
//! e a web vão "brotar" do chat nas próximas fases.

use alloc::string::String;
use alloc::vec::Vec;
use spin::Mutex;

use crate::agent::{Agent, IntentAgent, Reply};
use crate::gfx::{CANVAS, Canvas, Rgb};
use crate::keyboard::{Key, Keys};

const BG: Rgb = Rgb(16, 18, 24);
const HEADER: Rgb = Rgb(24, 27, 36);
const ACCENT: Rgb = Rgb(120, 170, 255);
const TEXT: Rgb = Rgb(230, 233, 240);
const MUTED: Rgb = Rgb(140, 147, 165);
const USER_BUBBLE: Rgb = Rgb(48, 86, 170);
const AGENT_BUBBLE: Rgb = Rgb(34, 38, 50);
const CARD_BG: Rgb = Rgb(28, 33, 46);
const INPUT_BG: Rgb = Rgb(30, 34, 44);

/// Mensagens que o próprio sistema publica no chat (sem o usuário pedir).
static NOTICES: Mutex<Vec<Reply>> = Mutex::new(Vec::new());

pub fn notify(replies: Vec<Reply>) {
    NOTICES.lock().extend(replies);
    crate::keyboard::push_key(Key::Refresh, crate::keyboard::SOURCE_NONE);
}

fn push_replies(msgs: &mut Vec<Msg>, replies: Vec<Reply>) {
    for r in replies {
        match r {
            Reply::Text(t) => msgs.push(Msg { from: From::Agent, body: Body::Text(t) }),
            Reply::Card { title, rows } => msgs.push(Msg { from: From::Agent, body: Body::Card { title, rows } }),
            Reply::Clear => msgs.clear(),
        }
    }
    // Mantém o histórico limitado nesta fase.
    if msgs.len() > 60 {
        msgs.drain(..msgs.len() - 60);
    }
}

enum From {
    User,
    Agent,
}

enum Body {
    Text(String),
    Card { title: String, rows: Vec<(String, String)> },
}

struct Msg {
    from: From,
    body: Body,
}

pub async fn run() {
    let mut keys = Keys::new();
    let mut agent = IntentAgent;
    let mut msgs: Vec<Msg> = Vec::new();
    let mut input = String::new();

    msgs.push(Msg {
        from: From::Agent,
        body: Body::Text(String::from(
            "Olá! Eu sou o Morfo, um sistema operacional que começa numa conversa. \
             Digite \"ajuda\" para ver o que já sei fazer.",
        )),
    });
    render(&msgs, &input, agent.name());

    loop {
        match keys.next_key().await {
            Key::Char(c) => {
                if input.chars().count() < 200 {
                    input.push(c);
                }
            }
            Key::Backspace => {
                input.pop();
            }
            Key::Enter => {
                let text = core::mem::take(&mut input);
                if text.trim().is_empty() {
                    continue;
                }
                crate::log!("usuário: {}", text);
                let replies = agent.respond(&text);
                msgs.push(Msg { from: From::User, body: Body::Text(text) });
                push_replies(&mut msgs, replies);
            }
            Key::Refresh => {
                let notices = core::mem::take(&mut *NOTICES.lock());
                push_replies(&mut msgs, notices);
            }
            Key::Other => continue,
        }
        render(&msgs, &input, agent.name());
    }
}

fn render(msgs: &[Msg], input: &str, agent_name: &str) {
    let mut guard = CANVAS.lock();
    let Some(cv) = guard.as_mut() else { return };

    let gw = cv.glyph_w();
    let gh = cv.glyph_h();
    let pad = gw;
    let (w, h) = (cv.width, cv.height);

    cv.clear(BG);

    // Cabeçalho.
    let header_h = gh * 2;
    cv.fill_rect(0, 0, w, header_h, HEADER);
    let ty = ((header_h - 8 * cv.scale) / 2) as isize;
    cv.draw_text(pad as isize, ty, agent_name, ACCENT);
    let status = match crate::keyboard::LAST_SOURCE.load(core::sync::atomic::Ordering::Relaxed) {
        crate::keyboard::SOURCE_USB => "fase 2 · teclado USB",
        crate::keyboard::SOURCE_PS2 => "fase 2 · teclado PS/2",
        _ => "fase 2 · kernel em Rust",
    };
    let sx = w as isize - (status.chars().count() * gw + pad) as isize;
    cv.draw_text(sx, ty, status, MUTED);

    // Caixa de entrada.
    let input_h = gh * 2;
    let input_y = (h - input_h - pad) as isize;
    cv.fill_round_rect(pad as isize, input_y, w - 2 * pad, input_h, gh / 2, INPUT_BG);
    let iy = input_y + ((input_h - 8 * cv.scale) / 2) as isize;
    let ix = (pad * 2) as isize;
    let max_cols = (w - 4 * pad) / gw - 1;
    if input.is_empty() {
        cv.draw_text(ix + (gw / 2) as isize, iy, "Converse com o Morfo...", MUTED);
        cv.fill_rect(ix, iy, cv.scale * 2, 8 * cv.scale, ACCENT);
    } else {
        // Mostra o final do texto se ele não couber.
        let n = input.chars().count();
        let shown: String = input.chars().skip(n.saturating_sub(max_cols)).collect();
        cv.draw_text(ix, iy, &shown, TEXT);
        let cx = ix + (shown.chars().count() * gw) as isize;
        cv.fill_rect(cx, iy, cv.scale * 2, 8 * cv.scale, ACCENT);
    }

    // Conversa: desenhada de baixo para cima, até o cabeçalho.
    let top = (header_h + pad) as isize;
    let mut y = input_y - pad as isize;
    let bubble_cols = ((w * 62 / 100) / gw).max(16);
    let card_cols = ((w * 72 / 100) / gw).max(20);

    for msg in msgs.iter().rev() {
        let height = measure(cv, msg, bubble_cols);
        y -= height as isize;
        if y + (height as isize) < top {
            break;
        }
        draw_msg(cv, msg, y, bubble_cols, card_cols);
        y -= (gh / 2) as isize;
    }

    // Repinta o cabeçalho por cima de mensagens cortadas.
    cv.fill_rect(0, header_h as isize, w, pad, BG);
    cv.fill_rect(0, 0, w, header_h, HEADER);
    cv.draw_text(pad as isize, ty, agent_name, ACCENT);
    cv.draw_text(sx, ty, status, MUTED);

    cv.present();
}

fn measure(cv: &Canvas, msg: &Msg, bubble_cols: usize) -> usize {
    let gh = cv.glyph_h();
    match &msg.body {
        Body::Text(t) => wrap(t, bubble_cols).len() * gh + gh,
        // título + linhas + margens
        Body::Card { rows, .. } => (rows.len() + 1) * gh + gh * 2 + gh / 2,
    }
}

fn draw_msg(cv: &mut Canvas, msg: &Msg, y: isize, bubble_cols: usize, card_cols: usize) {
    let gw = cv.glyph_w();
    let gh = cv.glyph_h();
    let pad = gw;
    let w = cv.width;

    match &msg.body {
        Body::Text(t) => {
            let lines = wrap(t, bubble_cols);
            let longest = lines.iter().map(|l| l.chars().count()).max().unwrap_or(1);
            let bw = longest * gw + 2 * pad;
            let bh = lines.len() * gh + gh;
            let (x, color) = match msg.from {
                From::User => ((w - bw - pad) as isize, USER_BUBBLE),
                From::Agent => (pad as isize, AGENT_BUBBLE),
            };
            cv.fill_round_rect(x, y, bw, bh, gh / 2, color);
            let mut ly = y + (gh / 2) as isize + 2;
            for line in &lines {
                cv.draw_text(x + pad as isize, ly, line, TEXT);
                ly += gh as isize;
            }
        }
        Body::Card { title, rows } => {
            let cw = card_cols * gw;
            let ch = (rows.len() + 1) * gh + gh * 2 + gh / 2;
            let x = pad as isize;
            cv.fill_round_rect(x, y, cw, ch, gh / 2, CARD_BG);
            cv.fill_rect(x, y + (gh / 2) as isize, cv.scale * 2, ch - gh, ACCENT);
            let inner = x + (pad * 2) as isize;
            let mut ly = y + gh as isize;
            cv.draw_text(inner, ly, title, ACCENT);
            ly += (gh + gh / 2) as isize;
            for (label, value) in rows {
                cv.draw_text(inner, ly, label, MUTED);
                let vx = x + cw as isize - (value.chars().count() * gw + pad * 2) as isize;
                cv.draw_text(vx, ly, value, TEXT);
                ly += gh as isize;
            }
        }
    }
}

/// Quebra o texto em linhas de no máximo `cols` caracteres, por palavra.
fn wrap(text: &str, cols: usize) -> Vec<String> {
    let mut lines = Vec::new();
    let mut line = String::new();
    let mut len = 0;
    for word in text.split_whitespace() {
        let wl = word.chars().count();
        if len > 0 && len + 1 + wl > cols {
            lines.push(core::mem::take(&mut line));
            len = 0;
        }
        if len > 0 {
            line.push(' ');
            len += 1;
        }
        // Palavras maiores que a linha são cortadas.
        if wl > cols {
            for ch in word.chars() {
                if len == cols {
                    lines.push(core::mem::take(&mut line));
                    len = 0;
                }
                line.push(ch);
                len += 1;
            }
        } else {
            line.push_str(word);
            len += wl;
        }
    }
    if !line.is_empty() || lines.is_empty() {
        lines.push(line);
    }
    lines
}
