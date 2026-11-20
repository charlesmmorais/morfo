# Morfo para Android

Ligou o celular num monitor, o Morfo abre na tela grande com o Claude a um toque.
Feito para o **Galaxy S25+**, funciona em qualquer Android 12+ com saída de vídeo.

- Detecta o monitor (HDMI/USB-C) e abre a área de trabalho do Morfo nele
- Relógio, data e o Claude em destaque; o Claude abre sozinho em 3 segundos (dá para cancelar)
- Temas **Grafite** e **Areia**, os mesmos do Morfo Linux
- O celular continua livre enquanto o monitor mostra o Morfo
- Sem bibliotecas extras: só a plataforma Android, em Kotlin

## Instalar

1. Baixe `morfo-android-<versão>.apk` na página de [Releases](../../../releases).
2. No celular, abra o arquivo e permita "instalar apps desta fonte".
3. Abra o **Morfo**, toque em **permitir** em "Abrir sozinho no monitor" e instale o app do Claude se faltar.
4. Conecte o monitor.

> No Samsung, o monitor costuma abrir no DeX. O Morfo abre por cima dele, em tela cheia.

## Compilar

```bash
gradle -p android assembleRelease    # Gradle 8.11+, JDK 17, Android SDK 35
```

No GitHub, cada push gera o APK nos *Artifacts*, e cada tag `v*` o publica na release.
Para atualizar sem desinstalar, cadastre os segredos `MORFO_KEYSTORE_B64`,
`MORFO_KEYSTORE_PASSWORD`, `MORFO_KEY_ALIAS` e `MORFO_KEY_PASSWORD`; sem eles o APK
usa uma chave de depuração diferente a cada build.

Projeto independente, sem vínculo com a Anthropic. "Claude" é marca da Anthropic, PBC.
