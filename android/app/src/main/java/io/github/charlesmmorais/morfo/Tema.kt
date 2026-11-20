package io.github.charlesmmorais.morfo

import android.content.Context
import android.graphics.Color

/** Os dois temas do Morfo, iguais aos do Morfo Linux. */
enum class Tema(
    val id: String,
    val rotulo: String,
    val fundo: Int,
    val logo: Int,
    val texto: Int,
    val suave: Int,
    val cartao: Int,
    val borda: Int,
    val destaque: Int,
    val destaqueClaro: Int,
    val escuro: Boolean,
) {
    GRAFITE(
        "grafite", "Grafite", R.drawable.fundo_grafite, R.drawable.logo_grafite,
        texto = Color.parseColor("#E6E9F0"),
        suave = Color.parseColor("#8C93A5"),
        cartao = Color.parseColor("#B8181B24"),
        borda = Color.parseColor("#B32C3242"),
        destaque = Color.parseColor("#4A6CF7"),
        destaqueClaro = Color.parseColor("#8FB8FF"),
        escuro = true,
    ),
    AREIA(
        "areia", "Areia", R.drawable.fundo_areia, R.drawable.logo_areia,
        texto = Color.parseColor("#2B2420"),
        suave = Color.parseColor("#7D7066"),
        cartao = Color.parseColor("#B8FBF8F3"),
        borda = Color.parseColor("#B3E2D6C6"),
        destaque = Color.parseColor("#7A3F6E"),
        destaqueClaro = Color.parseColor("#B07AA6"),
        escuro = false,
    );

    val outro: Tema get() = if (this == GRAFITE) AREIA else GRAFITE

    companion object {
        fun porId(id: String?): Tema = entries.firstOrNull { it.id == id } ?: GRAFITE
    }
}

/** Preferências guardadas no aparelho. */
object Prefs {
    private fun sp(c: Context) = c.getSharedPreferences("morfo", Context.MODE_PRIVATE)

    fun tema(c: Context): Tema = Tema.porId(sp(c).getString("tema", null))
    fun setTema(c: Context, t: Tema) = sp(c).edit().putString("tema", t.id).apply()

    /** Abrir a área de trabalho do Morfo ao conectar um monitor. */
    fun abrirAoConectar(c: Context): Boolean = sp(c).getBoolean("abrir_ao_conectar", true)
    fun setAbrirAoConectar(c: Context, v: Boolean) = sp(c).edit().putBoolean("abrir_ao_conectar", v).apply()

    /** Abrir o Claude sozinho, alguns segundos depois da área de trabalho. */
    fun abrirClaudeAuto(c: Context): Boolean = sp(c).getBoolean("abrir_claude_auto", true)
    fun setAbrirClaudeAuto(c: Context, v: Boolean) = sp(c).edit().putBoolean("abrir_claude_auto", v).apply()
}
