package io.github.charlesmmorais.morfo

import android.app.ActivityOptions
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.hardware.display.DisplayManager
import android.net.Uri
import android.provider.Settings
import android.util.Log
import android.view.Display

/** Abre coisas em uma tela específica (o celular ou o monitor). */
object Lancador {
    const val PACOTE_CLAUDE = "com.anthropic.claude"
    private const val TAG = "Morfo"

    fun claudeInstalado(c: Context): Boolean =
        c.packageManager.getLaunchIntentForPackage(PACOTE_CLAUDE) != null

    /** Telas externas (HDMI/DisplayPort ou a sessão DeX), sem as privadas. */
    fun telasExternas(c: Context): List<Display> {
        val dm = c.getSystemService(DisplayManager::class.java)
        return dm.displays.filter {
            it.displayId != Display.DEFAULT_DISPLAY && (it.flags and Display.FLAG_PRIVATE) == 0
        }
    }

    fun opcoesNaTela(displayId: Int) =
        ActivityOptions.makeBasic().setLaunchDisplayId(displayId).toBundle()

    /** A área de trabalho do Morfo na tela indicada. */
    fun abrirDesktop(c: Context, displayId: Int): Boolean {
        val i = Intent(c, DesktopActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        return iniciar(c, i, displayId)
    }

    /** O app do Claude na tela indicada; se não estiver instalado, a loja. */
    fun abrirClaude(c: Context, displayId: Int): Boolean {
        val i = c.packageManager.getLaunchIntentForPackage(PACOTE_CLAUDE)
            ?.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            ?: return abrirNaLoja(c, displayId)
        return iniciar(c, i, displayId)
    }

    fun abrirNaLoja(c: Context, displayId: Int): Boolean {
        val loja = Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=$PACOTE_CLAUDE"))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        if (iniciar(c, loja, displayId)) return true
        val web = Intent(Intent.ACTION_VIEW, Uri.parse("https://play.google.com/store/apps/details?id=$PACOTE_CLAUDE"))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        return iniciar(c, web, displayId)
    }

    fun abrirNavegador(c: Context, displayId: Int): Boolean {
        val i = Intent(Intent.ACTION_VIEW, Uri.parse("https://www.google.com"))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        return iniciar(c, i, displayId)
    }

    fun abrirPermissaoSobreposicao(c: Context) {
        val i = Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:${c.packageName}"))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        try {
            c.startActivity(i)
        } catch (e: ActivityNotFoundException) {
            c.startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }
    }

    private fun iniciar(c: Context, i: Intent, displayId: Int): Boolean = try {
        c.startActivity(i, opcoesNaTela(displayId))
        true
    } catch (e: Exception) {
        // Sem tela com esse id, app ausente ou bloqueio de abertura em segundo plano.
        Log.w(TAG, "Não abri ${i.component ?: i.data} na tela $displayId", e)
        false
    }
}
