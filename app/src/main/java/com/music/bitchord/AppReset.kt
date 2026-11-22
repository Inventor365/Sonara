package com.music.bitchord

import android.app.Activity
import android.app.ActivityManager
import android.app.Application
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.Process
import com.music.bitchord.data.settings.AppSettings
import java.io.File

/**
 * Settings → Miscellaneous → Reset Sonara.
 *
 * Two depths. [showWelcomeAgain] only brings the welcome screen back: library, stats, settings and
 * sign-ins stay. [eraseEverything] leaves the app as a fresh install would be, then opens it on the
 * welcome screen.
 *
 * Erasing can't be done by the process being erased. Its SharedPreferences live in memory and
 * write their whole map back on the next `apply()`, so a file deleted under a running app comes
 * straight back. And Android's own `clearApplicationUserData()` kills the app without opening it
 * again. So the work is handed to [ResetActivity], in a process of its own (`:reset`): it waits for
 * the app's main process to end, deletes the app's data, and starts the app fresh.
 */
object AppReset {
    const val PROCESS_SUFFIX = ":reset"

    fun showWelcomeAgain() = AppSettings.resetOnboarding()

    fun eraseEverything(activity: Activity) {
        activity.startActivity(
            Intent(activity, ResetActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK or Intent.FLAG_ACTIVITY_NO_ANIMATION),
        )
        activity.finishAffinity()
        // The reset process waits for this one to be gone before it touches anything.
        Process.killProcess(Process.myPid())
    }

    /** Whether this is the `:reset` process, where the app's usual start-up must not run. */
    fun isResetProcess(): Boolean = currentProcessName().endsWith(PROCESS_SUFFIX)

    private fun currentProcessName(): String =
        if (Build.VERSION.SDK_INT >= 28) {
            Application.getProcessName().orEmpty()
        } else {
            runCatching { File("/proc/self/cmdline").readText().trimEnd('\u0000') }.getOrDefault("")
        }
}

/** Does [AppReset.eraseEverything]'s work, in the `:reset` process. Has no screen of its own. */
class ResetActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Thread {
            waitForMainProcessToEnd()
            erase(applicationContext)
            packageManager.getLaunchIntentForPackage(packageName)?.let { launch ->
                startActivity(launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
            }
            runOnUiThread { finish() }
            Process.killProcess(Process.myPid())
        }.start()
    }

    private fun waitForMainProcessToEnd() {
        val manager = getSystemService(ActivityManager::class.java) ?: return
        val deadline = System.currentTimeMillis() + 5_000
        while (System.currentTimeMillis() < deadline) {
            val running = manager.runningAppProcesses.orEmpty().any { it.processName == packageName }
            if (!running) return
            Thread.sleep(100)
        }
    }

    private fun erase(context: Context) {
        runCatching { context.getSystemService(NotificationManager::class.java)?.cancelAll() }
        // Everything under the app's data directory but its native libraries: settings, stats,
        // downloads, caches, the WebView's cookies and storage, databases.
        context.dataDir.listFiles().orEmpty()
            .filter { it.name != "lib" }
            .forEach { it.deleteRecursively() }
        // And what it keeps on shared storage (Android/data/<package>).
        context.getExternalFilesDir(null)?.parentFile?.listFiles().orEmpty().forEach { it.deleteRecursively() }
    }
}
