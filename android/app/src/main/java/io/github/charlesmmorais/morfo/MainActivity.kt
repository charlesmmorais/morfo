package io.github.charlesmmorais.morfo

import android.Manifest
import android.app.Activity
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.Gravity
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.view.WindowInsetsController
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Switch

/**
 * Tela do celular: mostra se está tudo pronto, liga o modo "abrir ao conectar",
 * troca o tema e permite abrir o Morfo na tela grande na hora.
 */
class MainActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        MorfoService.criarCanais(this)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
        }
        if (Prefs.abrirAoConectar(this)) MorfoService.ligar(this)
    }

    override fun onResume() {
        super.onResume()
        montar()
    }

    private fun montar() {
        val t = Prefs.tema(this)
        val c = this

        window.insetsController?.setSystemBarsAppearance(
            if (t.escuro) 0 else WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS or WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS,
            WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS or WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS,
        )

        val raiz = FrameLayout(c)
        raiz.addView(ImageView(c).apply {
            setImageResource(t.fundo)
            scaleType = ImageView.ScaleType.CENTER_CROP
        }, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))

        val rolagem = ScrollView(c).apply { isFillViewport = true }
        val coluna = LinearLayout(c).apply {
            orientation = LinearLayout.VERTICAL
            val p = Ui.dp(c, 20f)
            setPadding(p, Ui.dp(c, 56f), p, Ui.dp(c, 40f))
        }
        rolagem.addView(coluna)
        raiz.addView(rolagem, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))

        // Marca e frase.
        val marca = LinearLayout(c).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        marca.addView(ImageView(c).apply { setImageResource(t.logo) }, LinearLayout.LayoutParams(Ui.dp(c, 40f), Ui.dp(c, 40f)))
        marca.addView(Ui.texto(c, "morfo", 30f, t.texto, 600).apply { setPadding(Ui.dp(c, 14f), 0, 0, 0) })
        coluna.addView(marca)
        coluna.addView(Ui.espaco(c, 14f))
        coluna.addView(Ui.texto(c, "Conecte o celular a um monitor e o Claude abre na tela grande.", 16f, t.suave).apply {
            setLineSpacing(0f, 1.25f)
        })
        coluna.addView(Ui.espaco(c, 26f))

        // Estado.
        val estado = Ui.cartao(c, t)
        estado.addView(Ui.texto(c, "Tudo pronto?", 17f, t.texto, 600))
        estado.addView(Ui.espaco(c, 14f))
        val claudeOk = Lancador.claudeInstalado(c)
        estado.addView(linhaEstado(t, claudeOk, "App do Claude", if (claudeOk) "instalado" else "instalar") {
            Lancador.abrirNaLoja(c, android.view.Display.DEFAULT_DISPLAY)
        })
        val sobreposicao = Settings.canDrawOverlays(c)
        estado.addView(linhaEstado(t, sobreposicao, "Abrir sozinho no monitor", if (sobreposicao) "permitido" else "permitir") {
            Lancador.abrirPermissaoSobreposicao(c)
        })
        val telas = Lancador.telasExternas(c)
        val descricaoTela = telas.firstOrNull()?.let { d ->
            val m = d.mode
            "${d.name} · ${m.physicalWidth}×${m.physicalHeight}"
        } ?: "nenhum conectado"
        estado.addView(linhaEstado(t, telas.isNotEmpty(), "Monitor", descricaoTela, null))
        coluna.addView(estado)
        coluna.addView(Ui.espaco(c, 16f))

        // Ao conectar.
        val conectar = Ui.cartao(c, t)
        conectar.addView(Ui.texto(c, "Ao conectar o HDMI", 17f, t.texto, 600))
        conectar.addView(Ui.espaco(c, 8f))
        conectar.addView(chave(t, "Abrir o Morfo no monitor", Prefs.abrirAoConectar(c)) { ligado ->
            Prefs.setAbrirAoConectar(c, ligado)
            if (ligado) MorfoService.ligar(c) else MorfoService.desligar(c)
        })
        conectar.addView(chave(t, "Abrir o Claude em seguida", Prefs.abrirClaudeAuto(c)) { ligado ->
            Prefs.setAbrirClaudeAuto(c, ligado)
        })
        coluna.addView(conectar)
        coluna.addView(Ui.espaco(c, 16f))

        // Tema.
        val tema = Ui.cartao(c, t)
        tema.addView(Ui.texto(c, "Tema", 17f, t.texto, 600))
        tema.addView(Ui.espaco(c, 14f))
        val opcoes = LinearLayout(c).apply { orientation = LinearLayout.HORIZONTAL }
        for (opcao in Tema.entries) {
            val escolhido = opcao == t
            val b = Ui.texto(c, opcao.rotulo, 15f, if (escolhido) 0xFFFFFFFF.toInt() else t.texto, if (escolhido) 600 else 400).apply {
                gravity = Gravity.CENTER
                val v = Ui.dp(c, 12f)
                setPadding(0, v, 0, v)
                background = if (escolhido) Ui.degrade(opcao.destaqueClaro, opcao.destaque, Ui.dp(c, 12f).toFloat())
                else Ui.fundoArredondado(0, Ui.dp(c, 12f).toFloat(), t.borda, Ui.dp(c, 1f))
                setOnClickListener {
                    Prefs.setTema(c, opcao)
                    montar()
                }
            }
            val lp = LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f)
            if (opcao != Tema.entries.first()) lp.marginStart = Ui.dp(c, 10f)
            opcoes.addView(b, lp)
        }
        tema.addView(opcoes)
        coluna.addView(tema)
        coluna.addView(Ui.espaco(c, 22f))

        // Ações.
        val abrirAgora = Ui.botaoPrincipal(c, t, if (telas.isNotEmpty()) "Abrir no monitor agora" else "Ver como fica (prévia)") {
            val destino = telas.firstOrNull()?.displayId ?: android.view.Display.DEFAULT_DISPLAY
            Lancador.abrirDesktop(c, destino)
        }
        coluna.addView(abrirAgora, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
        coluna.addView(Ui.espaco(c, 28f))
        coluna.addView(Ui.texto(c, "Morfo é um projeto independente, sem vínculo com a Anthropic. \"Claude\" é marca da Anthropic, PBC.", 12f, t.suave).apply {
            gravity = Gravity.CENTER
            setLineSpacing(0f, 1.2f)
        })

        setContentView(raiz)
    }

    private fun linhaEstado(t: Tema, ok: Boolean, rotulo: String, valor: String, acao: (() -> Unit)?): View {
        val c = this
        val linha = LinearLayout(c).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, Ui.dp(c, 8f), 0, Ui.dp(c, 8f))
        }
        val ponto = View(c).apply {
            background = Ui.fundoArredondado(if (ok) t.destaque else t.suave, Ui.dp(c, 99f).toFloat())
            alpha = if (ok) 1f else 0.45f
        }
        linha.addView(ponto, LinearLayout.LayoutParams(Ui.dp(c, 10f), Ui.dp(c, 10f)))
        linha.addView(Ui.texto(c, rotulo, 15f, t.texto).apply { setPadding(Ui.dp(c, 12f), 0, 0, 0) },
            LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f))
        if (!ok && acao != null) {
            linha.addView(Ui.pilula(c, t, valor) { acao() })
        } else {
            linha.addView(Ui.texto(c, valor, 14f, t.suave))
        }
        return linha
    }

    private fun chave(t: Tema, rotulo: String, ligado: Boolean, aoMudar: (Boolean) -> Unit): View {
        val c = this
        val linha = LinearLayout(c).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, Ui.dp(c, 6f), 0, Ui.dp(c, 6f))
        }
        linha.addView(Ui.texto(c, rotulo, 15f, t.texto), LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f))
        linha.addView(Switch(c).apply {
            isChecked = ligado
            setOnCheckedChangeListener { _, v -> aoMudar(v) }
        })
        return linha
    }
}
