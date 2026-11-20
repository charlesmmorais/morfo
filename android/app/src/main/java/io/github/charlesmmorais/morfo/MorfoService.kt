package io.github.charlesmmorais.morfo

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.hardware.display.DisplayManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.provider.Settings
import android.view.Display

/**
 * Serviço leve que só escuta o DisplayManager: quando um monitor é conectado,
 * abre a área de trabalho do Morfo nele.
 */
class MorfoService : Service(), DisplayManager.DisplayListener {

    private lateinit var dm: DisplayManager
    private val principal = Handler(Looper.getMainLooper())

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        criarCanais(this)
        val n = notificacaoAtiva()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(ID_ATIVO, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(ID_ATIVO, n)
        }
        dm = getSystemService(DisplayManager::class.java)
        dm.registerDisplayListener(this, principal)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

    override fun onDestroy() {
        dm.unregisterDisplayListener(this)
        super.onDestroy()
    }

    override fun onDisplayAdded(displayId: Int) {
        if (displayId == Display.DEFAULT_DISPLAY || !Prefs.abrirAoConectar(this)) return
        val d = dm.getDisplay(displayId) ?: return
        if ((d.flags and Display.FLAG_PRIVATE) != 0) return
        // Dá um instante para a tela (ou a sessão DeX) terminar de subir.
        principal.postDelayed({ abrir(displayId) }, 1200)
    }

    override fun onDisplayRemoved(displayId: Int) {
        getSystemService(NotificationManager::class.java).cancel(ID_TELA)
    }

    override fun onDisplayChanged(displayId: Int) = Unit

    private fun abrir(displayId: Int) {
        if (dm.getDisplay(displayId) == null) return
        val abriu = Settings.canDrawOverlays(this) && Lancador.abrirDesktop(this, displayId)
        if (!abriu) avisarTelaConectada(displayId)
    }

    /** Plano B: sem permissão para abrir sozinho, uma notificação com um toque abre. */
    private fun avisarTelaConectada(displayId: Int) {
        val i = Intent(this, DesktopActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        val pi = PendingIntent.getActivity(
            this, displayId, i,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
            Lancador.opcoesNaTela(displayId),
        )
        val n = Notification.Builder(this, CANAL_TELA)
            .setSmallIcon(R.drawable.ic_notif)
            .setContentTitle("Monitor conectado")
            .setContentText("Toque para abrir o Morfo na tela grande")
            .setContentIntent(pi)
            .setAutoCancel(true)
            .build()
        getSystemService(NotificationManager::class.java).notify(ID_TELA, n)
    }

    private fun notificacaoAtiva(): Notification {
        val pi = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE,
        )
        return Notification.Builder(this, CANAL_ATIVO)
            .setSmallIcon(R.drawable.ic_notif)
            .setContentTitle("Morfo")
            .setContentText("Pronto para abrir na tela grande quando você conectar o HDMI")
            .setContentIntent(pi)
            .setOngoing(true)
            .build()
    }

    companion object {
        private const val CANAL_ATIVO = "ativo"
        private const val CANAL_TELA = "tela"
        private const val ID_ATIVO = 1
        private const val ID_TELA = 2

        fun criarCanais(c: Context) {
            val nm = c.getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(
                NotificationChannel(CANAL_ATIVO, "Morfo ativo", NotificationManager.IMPORTANCE_MIN)
                    .apply { description = "Mostra que o Morfo está esperando um monitor" },
            )
            nm.createNotificationChannel(
                NotificationChannel(CANAL_TELA, "Monitor conectado", NotificationManager.IMPORTANCE_HIGH)
                    .apply { description = "Avisa quando um monitor é conectado" },
            )
        }

        fun ligar(c: Context) {
            c.startForegroundService(Intent(c, MorfoService::class.java))
        }

        fun desligar(c: Context) {
            c.stopService(Intent(c, MorfoService::class.java))
        }
    }
}

/** Liga o serviço depois de reiniciar o celular ou atualizar o app. */
class BootReceiver : android.content.BroadcastReceiver() {
    override fun onReceive(c: Context, intent: Intent) {
        if (Prefs.abrirAoConectar(c)) {
            try {
                MorfoService.ligar(c)
            } catch (e: Exception) {
                android.util.Log.w("Morfo", "Não liguei o serviço no boot", e)
            }
        }
    }
}
