package io.github.charlesmmorais.morfo

import android.content.Context
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView

/** Pequenos construtores de interface, sem bibliotecas: o app fica leve. */
object Ui {
    fun dp(c: Context, v: Float): Int =
        TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, c.resources.displayMetrics).toInt()

    fun fonte(c: Context, peso: Int): Typeface = when (peso) {
        300 -> c.resources.getFont(R.font.inter_light)
        600 -> c.resources.getFont(R.font.inter_semibold)
        else -> c.resources.getFont(R.font.inter_regular)
    }

    fun texto(c: Context, s: String, sp: Float, cor: Int, peso: Int = 400): TextView =
        TextView(c).apply {
            text = s
            setTextSize(TypedValue.COMPLEX_UNIT_SP, sp)
            setTextColor(cor)
            typeface = fonte(c, peso)
            includeFontPadding = false
        }

    fun fundoArredondado(cor: Int, raio: Float, borda: Int? = null, larguraBorda: Int = 0) =
        GradientDrawable().apply {
            setColor(cor)
            cornerRadius = raio
            if (borda != null) setStroke(larguraBorda, borda)
        }

    fun degrade(de: Int, para: Int, raio: Float) =
        GradientDrawable(GradientDrawable.Orientation.TL_BR, intArrayOf(de, para)).apply {
            cornerRadius = raio
        }

    /** Cartão translúcido com borda fina, no estilo da tela de login do Morfo Linux. */
    fun cartao(c: Context, t: Tema): LinearLayout = LinearLayout(c).apply {
        orientation = LinearLayout.VERTICAL
        val p = dp(c, 22f)
        setPadding(p, p, p, p)
        background = fundoArredondado(t.cartao, dp(c, 22f).toFloat(), t.borda, dp(c, 1f))
        elevation = dp(c, 8f).toFloat()
    }

    /** Botão principal com o degradê do tema. */
    fun botaoPrincipal(c: Context, t: Tema, rotulo: String, aoTocar: () -> Unit): TextView =
        texto(c, rotulo, 16f, 0xFFFFFFFF.toInt(), 600).apply {
            gravity = Gravity.CENTER
            val v = dp(c, 14f)
            setPadding(dp(c, 24f), v, dp(c, 24f), v)
            background = degrade(t.destaqueClaro, t.destaque, dp(c, 14f).toFloat())
            isClickable = true
            isFocusable = true
            setOnClickListener { aoTocar() }
        }

    /** Botão "pílula" discreto. */
    fun pilula(c: Context, t: Tema, rotulo: String, aoTocar: () -> Unit): TextView =
        texto(c, rotulo, 13f, t.suave).apply {
            gravity = Gravity.CENTER
            val v = dp(c, 8f)
            setPadding(dp(c, 16f), v, dp(c, 16f), v)
            background = fundoArredondado(t.cartao, dp(c, 999f).toFloat(), t.borda, dp(c, 1f))
            isClickable = true
            isFocusable = true
            setOnClickListener { aoTocar() }
        }

    fun espaco(c: Context, alturaDp: Float): View = View(c).apply {
        layoutParams = LinearLayout.LayoutParams(1, dp(c, alturaDp))
    }
}

/** Data por extenso em português, sem depender do idioma do aparelho. */
object Calendario {
    private val dias = arrayOf("domingo", "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado")
    private val meses = arrayOf("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")

    fun hora(): String {
        val c = java.util.Calendar.getInstance()
        return String.format(java.util.Locale.ROOT, "%02d:%02d", c.get(java.util.Calendar.HOUR_OF_DAY), c.get(java.util.Calendar.MINUTE))
    }

    fun data(): String {
        val c = java.util.Calendar.getInstance()
        val dia = dias[c.get(java.util.Calendar.DAY_OF_WEEK) - 1]
        return "$dia, ${c.get(java.util.Calendar.DAY_OF_MONTH)} de ${meses[c.get(java.util.Calendar.MONTH)]}"
    }
}
