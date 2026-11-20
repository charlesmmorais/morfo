package io.github.charlesmmorais.morfo

import android.app.Activity
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView

/**
 * A área de trabalho do Morfo no monitor: relógio, data e o Claude a um toque.
 * Abre o Claude sozinho depois de alguns segundos (dá para cancelar).
 */
class DesktopActivity : Activity() {

    private val relogio = Handler(Looper.getMainLooper())
    private lateinit var hora: TextView
    private lateinit var data: TextView
    private lateinit var status: TextView
    private var contagem = 0
    private var jaAbriuSozinho = false

    private val tique = object : Runnable {
        override fun run() {
            hora.text = Calendario.hora()
            data.text = Calendario.data()
            relogio.postDelayed(this, 1000)
        }
    }

    private val contador = object : Runnable {
        override fun run() {
            if (contagem <= 0) {
                status.text = ""
                abrirClaude()
                return
            }
            status.text = "Abrindo o Claude em $contagem s  ·  toque aqui para cancelar"
            contagem--
            relogio.postDelayed(this, 1000)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        jaAbriuSozinho = savedInstanceState?.getBoolean("ja_abriu") ?: false
        montar()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putBoolean("ja_abriu", jaAbriuSozinho)
    }

    override fun onResume() {
        super.onResume()
        telaCheia()
        relogio.post(tique)
        if (!jaAbriuSozinho && Prefs.abrirClaudeAuto(this) && Lancador.claudeInstalado(this)) {
            jaAbriuSozinho = true
            contagem = 3
            relogio.post(contador)
        }
    }

    override fun onPause() {
        relogio.removeCallbacksAndMessages(null)
        super.onPause()
    }

    private fun telaCheia() {
        window.insetsController?.let {
            it.hide(WindowInsets.Type.systemBars())
            it.systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }
    }

    private fun idDaTela(): Int = display?.displayId ?: android.view.Display.DEFAULT_DISPLAY

    private fun abrirClaude() {
        relogio.removeCallbacks(contador)
        status.text = ""
        if (!Lancador.abrirClaude(this, idDaTela())) {
            status.text = "Não consegui abrir o Claude nesta tela."
        }
    }

    private fun cancelarContagem() {
        relogio.removeCallbacks(contador)
        status.text = ""
    }

    private fun montar() {
        val t = Prefs.tema(this)
        val c = this
        val raiz = FrameLayout(c)

        raiz.addView(ImageView(c).apply {
            setImageResource(t.fundo)
            scaleType = ImageView.ScaleType.CENTER_CROP
        }, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))

        val coluna = LinearLayout(c).apply { orientation = LinearLayout.VERTICAL }
        raiz.addView(coluna, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))

        // Topo: marca e tema.
        val topo = LinearLayout(c).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(Ui.dp(c, 28f), Ui.dp(c, 22f), Ui.dp(c, 28f), Ui.dp(c, 22f))
        }
        topo.addView(ImageView(c).apply { setImageResource(t.logo) }, LinearLayout.LayoutParams(Ui.dp(c, 30f), Ui.dp(c, 30f)))
        topo.addView(Ui.texto(c, "morfo", 19f, t.texto, 600).apply { setPadding(Ui.dp(c, 12f), 0, 0, 0) })
        topo.addView(View(c), LinearLayout.LayoutParams(0, 1, 1f))
        topo.addView(Ui.pilula(c, t, "Tema ${t.rotulo}  ·  mudar para ${t.outro.rotulo}") {
            Prefs.setTema(c, t.outro)
            cancelarContagem()
            recreate()
        })
        coluna.addView(topo)

        // Centro: relógio, data e o cartão do Claude.
        val centro = LinearLayout(c).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
        }
        hora = Ui.texto(c, Calendario.hora(), 96f, t.texto, 300).apply {
            letterSpacing = -0.04f
            gravity = Gravity.CENTER
        }
        data = Ui.texto(c, Calendario.data(), 18f, t.suave).apply { gravity = Gravity.CENTER }
        centro.addView(hora)
        centro.addView(Ui.espaco(c, 10f))
        centro.addView(data)
        centro.addView(Ui.espaco(c, 34f))

        val cartao = Ui.cartao(c, t).apply { gravity = Gravity.CENTER_HORIZONTAL }
        cartao.addView(Ui.texto(c, "Claude", 22f, t.texto, 600))
        cartao.addView(Ui.espaco(c, 6f))
        cartao.addView(Ui.texto(c, "Sua conversa em tela cheia", 14f, t.suave))
        cartao.addView(Ui.espaco(c, 18f))
        val instalado = Lancador.claudeInstalado(c)
        cartao.addView(
            Ui.botaoPrincipal(c, t, if (instalado) "Abrir o Claude" else "Instalar o Claude") { abrirClaude() },
            LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT),
        )
        cartao.addView(Ui.espaco(c, 12f))
        status = Ui.texto(c, "", 13f, t.suave).apply {
            gravity = Gravity.CENTER
            setOnClickListener { cancelarContagem() }
        }
        cartao.addView(status, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
        centro.addView(cartao, LinearLayout.LayoutParams(Ui.dp(c, 400f), WRAP_CONTENT))

        coluna.addView(centro, LinearLayout.LayoutParams(MATCH_PARENT, 0, 1f))

        // Rodapé: atalhos discretos.
        val rodape = LinearLayout(c).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            setPadding(0, Ui.dp(c, 18f), 0, Ui.dp(c, 26f))
        }
        rodape.addView(Ui.pilula(c, t, "Navegador") { cancelarContagem(); Lancador.abrirNavegador(c, idDaTela()) })
        rodape.addView(View(c), LinearLayout.LayoutParams(Ui.dp(c, 10f), 1))
        rodape.addView(Ui.pilula(c, t, "Configurações do Morfo") {
            cancelarContagem()
            startActivity(android.content.Intent(c, MainActivity::class.java), Lancador.opcoesNaTela(android.view.Display.DEFAULT_DISPLAY))
        })
        coluna.addView(rodape)

        setContentView(raiz)
    }
}
