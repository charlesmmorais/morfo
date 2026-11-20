# Morfo — kernel experimental em Rust

Sistema operacional experimental, escrito do zero em Rust, para o Mac mini (Mid 2011, A1347).
A interface começa numa conversa e, nas próximas fases, se molda à tarefa.

## Fase 1 — o que já funciona

- Boot UEFI (e BIOS) pelo Limine
- Heap do kernel na RAM física (mapeamento HHDM)
- GDT, TSS, IDT, exceções da CPU e PIC 8259 (timer e teclado)
- Executor assíncrono: o kernel roda como tarefas `async` e dorme (`hlt`) quando ocioso
- Gráficos 2D por software no framebuffer GOP, com buffer duplo
- Shell de chat: balões, cartões (o embrião das "superfícies") e caixa de entrada
- Agente atrás da trait `Agent`: hoje um interpretador de intenções; depois um modelo remoto/local

## Fase 2 — USB

- Varredura do barramento PCI
- Mapeamento de registradores de dispositivo (MMIO) sem cache e reserva de DMA abaixo de 4 GiB
- Timer a 1 kHz e `sleep` assíncrono
- Driver EHCI (USB 2.0): handoff do firmware, reset, fila assíncrona, transferências de controle
- Enumeração com hubs, inclusive transações *split* pelo Transaction Translator do hub
  (caminho necessário no Mac mini 2011, cujas portas passam pelo hub interno do chipset)
- Teclado USB (HID, protocolo de boot) com repetição ao segurar
- Teclas mortas do layout US-Internacional para acentuar: `'a` = á, `~a` = ã, `^e` = ê, `` `a`` = à, `'c` = ç
- Ao terminar a detecção, o chat mostra sozinho o relatório do USB (o Mac mini não tem porta serial)
- Comando `usb` no chat mostra controladores, dispositivos e o registro

## Estrutura

```
kernel/src/
  main.rs        pedidos ao Limine e sequência de boot
  allocator.rs   heap
  gdt.rs         segmentos e pilha de falha dupla
  interrupts.rs  IDT, exceções, timer, teclado
  task.rs        executor assíncrono
  keyboard.rs    teclado como fluxo assíncrono de teclas
  gfx.rs         canvas 2D, fontes, tela de pânico
  agent.rs       o agente (cérebro trocável) e as respostas
  shell.rs       a interface de chat
  time.rs        PIT a 1 kHz e sleep assíncrono
  memory.rs      DMA e mapeamento de MMIO
  pci.rs         barramento PCI
  usb/ehci.rs    controlador EHCI e transferências de controle
  usb/mod.rs     enumeração e driver de hub
  usb/hid.rs     teclado USB
```

## Compilar

Os comandos abaixo rodam na raiz do repositório.

Requisitos: Rust (estável serve), `rust-src`, `xorriso`, `make`, `git`; para testar, `qemu-system-x86` e `ovmf`.

```
rustup component add rust-src
./build.sh          # gera dist/morfo.iso e dist/pendrive/
./build.sh run      # roda no QEMU com UEFI, EHCI e teclado USB
```

O `build.sh` usa `RUSTC_BOOTSTRAP=1` para liberar `build-std` e a ABI `x86-interrupt` no Rust estável.

No ChromeOS Flex, ative o "Ambiente de desenvolvimento Linux" e instale os mesmos pacotes no Debian dele.

## Rodar no Mac mini

1. Formate um pendrive em **FAT32** (o app Arquivos do ChromeOS faz isso).
2. Copie para a raiz do pendrive o **conteúdo** de `dist/pendrive/` (as pastas `EFI` e `boot`).
3. Desligue o Mac mini, ligue segurando **Option (⌥)** e escolha o pendrive ("EFI Boot").

O disco interno não é tocado. Para voltar ao sistema atual, basta reiniciar sem o pendrive.

**Teclado no Mac mini:**
- Use um teclado **USB com fio**, conectado **antes** de ligar (ainda não há detecção a quente).
- Teclado Bluetooth não funciona: exige uma pilha Bluetooth inteira.
- Uns 2 segundos após a tela aparecer, o chat mostra o cartão "USB" com o que foi encontrado.
  Se o teclado não responder, esse cartão e o registro abaixo dele dizem onde parou.

O caminho pelo hub interno (transações *split*) segue a especificação EHCI, mas o QEMU não
consegue emulá-lo; só o hardware real confirma.

## Próximas fases

2. ~~USB (EHCI) e teclado no Mac~~ (feito); falta fila periódica, detecção a quente, APIC e múltiplos núcleos
3. Capabilities, modelo de componentes e IPC tipado
4. Disco (AHCI) e armazenamento de objetos em grafo, transacional
5. Rede (Broadcom tg3), smoltcp e rustls
6. Superfícies: planilha, documento e web nativa (html5ever, Taffy, Boa)
7. Agente com modelo de linguagem, rótulos de origem e controle de fluxo de informação
