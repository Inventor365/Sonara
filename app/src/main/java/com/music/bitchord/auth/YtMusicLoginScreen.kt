package com.music.bitchord.auth

import android.annotation.SuppressLint
import android.webkit.CookieManager
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import com.music.bitchord.data.DebugLog as Log
import kotlinx.coroutines.launch
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import com.music.bitchord.data.web.QuietWebChromeClient

private const val MUSIC_ORIGIN = "https://music.youtube.com"

private const val LOGIN_URL = DeviceGoogleAccounts.LOGIN_URL

private const val TAG = "BitChord"

/**
 * In-app Google sign-in for YouTube Music, and the way to change which channel
 * it listens as.
 *
 * [WebSessionMode.SIGN_IN] loads the standard Google web login with
 * `continue=music.youtube.com`. The user authenticates directly against
 * accounts.google.com (2FA, passkeys etc. all work — it's the real page). When
 * Google redirects back to music.youtube.com the listener confirms the profile
 * shown by the live page. This deliberately leaves a multiple-channel account
 * enough time to choose its Personal or Brand identity before anything is
 * saved. The browser's local Google cookies are cleared on the way in without
 * visiting Google's logout endpoint, so adding an account cannot invalidate a
 * previously saved session.
 *
 * [WebSessionMode.SWITCH_CHANNEL] keeps those cookies and opens YouTube Music
 * itself, so the listener can use the avatar menu's own Accounts list — the one
 * screen that authoritatively knows which channels exist and which is which.
 * Nothing is taken automatically there: the session is read when they say so,
 * by raising [captureRequest].
 *
 * Either way what is read is the page's own `ytcfg`, not a guess made later
 * from a server-side fetch. The credential itself never passes through app code.
 */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun YtMusicLoginScreen(
    mode: WebSessionMode,
    /** Cookie snapshot to install before opening an existing account's channel picker. */
    initialCookie: String? = null,
    onCaptured: (CapturedSession) -> Unit,
    modifier: Modifier = Modifier,
    /**
     * Raise to take the session from the page as it stands. Ignored at its
     * initial value, so arriving on the screen doesn't capture anything.
     */
    captureRequest: Int = 0,
    /** Told when a capture was asked for and there was no session to take. */
    onCaptureUnavailable: () -> Unit = {},
    /** True once a signed-in YouTube Music page is available for confirmation. */
    onPageReady: (Boolean) -> Unit = {},
    /** For a host that needs the WebView set up differently — the TV app, for its remote. */
    configureWebView: (WebView) -> Unit = {},
    /**
     * Offer the Google accounts already on the device first (see [DeviceGoogleAccounts]); the web
     * login stays one tap away, behind the chooser's back button and "Add account".
     */
    useDeviceAccounts: Boolean = true,
    /**
     * Told when a sign-in is being taken without "Use this profile": in [WebSessionMode.SIGN_IN],
     * an account that turns out to have a single channel has nothing to choose, so its session is
     * taken as soon as it lands. An account with brand channels still waits for the listener; see
     * [channelCount].
     */
    onAutoConfirming: () -> Unit = {},
) {
    val autoConfirm = mode == WebSessionMode.SIGN_IN
    var webView by remember { mutableStateOf<WebView?>(null) }
    val scope = androidx.compose.runtime.rememberCoroutineScope()
    // Once a probe has given a real answer, the page is the listener's to confirm from then on.
    var autoAnswered by remember { mutableStateOf(false) }
    var probing by remember { mutableStateOf(false) }
    val context = androidx.compose.ui.platform.LocalContext.current
    // Where the sign-in WebView starts. In SIGN_IN mode with device accounts it waits for the
    // chooser: a one-time sign-in link for the chosen account, the web login with that address
    // filled in, or — backed out — the plain web login.
    val viaDevice = mode == WebSessionMode.SIGN_IN && useDeviceAccounts &&
        remember { DeviceGoogleAccounts.available(context) }
    var startUrl by androidx.compose.runtime.saveable.rememberSaveable {
        mutableStateOf(
            when {
                mode != WebSessionMode.SIGN_IN -> "$MUSIC_ORIGIN/"
                viaDevice -> null
                else -> LOGIN_URL
            },
        )
    }
    val chooser = androidx.activity.compose.rememberLauncherForActivityResult(
        androidx.activity.result.contract.ActivityResultContracts.StartActivityForResult(),
    ) { result ->
        // Google refuses its one-time device sign-in link to apps outside Google: measured, the
        // server answers WILL_NOT_SIGN_IN after showing an "UnsupportedTokenLabel" consent screen.
        // So the chosen account goes straight into Google's own sign-in, already filled in, where
        // Google can confirm it with a prompt to this phone instead of a password.
        val email = DeviceGoogleAccounts.chosenAccount(result.data)
        startUrl = email?.let(DeviceGoogleAccounts::prefilledLoginUrl) ?: LOGIN_URL
    }
    LaunchedEffect(Unit) {
        if (startUrl == null) {
            runCatching { chooser.launch(DeviceGoogleAccounts.chooserIntent()) }
                .onFailure { startUrl = LOGIN_URL }
        }
    }
    val currentOnCaptured by rememberUpdatedState(onCaptured)
    val currentOnUnavailable by rememberUpdatedState(onCaptureUnavailable)
    val currentOnPageReady by rememberUpdatedState(onPageReady)
    val currentOnAutoConfirming by rememberUpdatedState(onAutoConfirming)

    LaunchedEffect(captureRequest) {
        if (captureRequest == 0) return@LaunchedEffect
        val view = webView
        if (view == null) currentOnUnavailable()
        else captureFrom(view, currentOnCaptured, currentOnUnavailable)
    }

    AndroidView(
        modifier = modifier.fillMaxSize(),
        factory = { context ->
            if (mode == WebSessionMode.SIGN_IN) {
                BrowserSession.clearGoogleCookies()
            } else initialCookie?.let(BrowserSession::installGoogleCookies)
            WebView(context).apply {
                if (mode == WebSessionMode.SIGN_IN) {
                    clearCache(true)
                    clearHistory()
                    clearFormData()
                }
                settings.javaScriptEnabled = true
                settings.domStorageEnabled = true
                webChromeClient = QuietWebChromeClient()
                configureWebView(this)

                webViewClient = object : WebViewClient() {
                    override fun onPageFinished(view: WebView?, url: String?) {
                        // Reaching the Music origin only enables confirmation.
                        // A multi-channel login can still be waiting for the
                        // listener to choose an identity on this very page.
                        // Capturing automatically here is the race that used to
                        // create a fake "Personal" profile and close too soon.
                        val ready = url?.startsWith(MUSIC_ORIGIN) == true
                        currentOnPageReady(ready)
                        // One account, one channel: nothing to choose, so no "Use this profile".
                        // Asked of YouTube itself (accounts_list) from the signed-in page, never
                        // guessed; any doubt leaves the button for the listener.
                        if (ready && autoConfirm && !autoAnswered && !probing && view != null) {
                            probing = true
                            scope.launch {
                                val count = channelCount(view)
                                probing = false
                                if (count == null) return@launch // not signed in yet: try on the next page
                                autoAnswered = true
                                if (count == 1) {
                                    currentOnAutoConfirming()
                                    captureFrom(view, currentOnCaptured, currentOnUnavailable)
                                }
                            }
                        }
                    }
                }

                webView = this
                startUrl?.let(::loadUrl)
            }
        },
        // The chooser answers after the WebView exists: load its answer once, when it lands.
        update = { view ->
            val url = startUrl
            if (url != null && view.url == null) view.loadUrl(url)
        },
    )
}

/**
 * Takes the session from [view], if it is holding one.
 *
 * @return whether there was one to take. False means the cookie jar has no
 *   signing secret in it yet — the page is mid-login, or is not a YouTube page
 *   at all — and the caller should leave the screen open rather than saving
 *   something that cannot sign a request. See [AuthStore.hasApiSid].
 */
private fun captureFrom(
    view: WebView,
    onCaptured: (CapturedSession) -> Unit,
    onUnavailable: () -> Unit,
) {
    val cookies = CookieManager.getInstance().getCookie(MUSIC_ORIGIN)
    if (cookies == null || !AuthStore.hasApiSid(cookies)) {
        onUnavailable()
        return
    }
    // Flushed here rather than left to the WebView's own schedule: the screen
    // is usually closing in the next frame, and a cookie jar written after
    // that is a jar the next sign-in reads instead of this one.
    CookieManager.getInstance().flush()

    view.evaluateJavascript(YTCFG_PROBE) { raw ->
        val config = raw.parseConfig()
        val loggedIn = config?.get("loggedIn").let {
            it is JsonPrimitive && it.content == "true"
        }
        if (config == null || !loggedIn) {
            Log.w(TAG, "confirmation requested before the page exposed a signed-in identity")
            onUnavailable()
            return@evaluateJavascript
        }
        val pageId = config.string("pageId")
        onCaptured(
            CapturedSession(
                cookie = cookies,
                // A delegated identity is the most specific answer the live
                // page can give. Otherwise normalise its DATASYNC_ID.
                dataSyncId = pageId ?: normalizeDataSyncId(config.string("dataSyncId")),
                pageId = pageId,
                authUser = config.string("authUser"),
                visitorData = config.string("visitorData"),
                clientVersion = config.string("clientVersion"),
                loggedIn = true,
            ),
        )
    }
}

/**
 * How many channels the signed-in page's account can act as: its own plus any brand channels,
 * from YouTube's `accounts_list`, asked by the page itself so it carries the page's own session.
 *
 * @return null while the page isn't signed in yet; 0 when YouTube's answer couldn't be read
 *   (the listener then confirms by hand, as before).
 */
private suspend fun channelCount(view: WebView): Int? {
    val started = view.evaluate(CHANNELS_PROBE)?.let { runCatching { json.decodeFromString<String>(it) }.getOrNull() }
    if (started != "started") return 0
    repeat(40) {
        kotlinx.coroutines.delay(250)
        val raw = view.evaluate("window.__sonaraChannels") ?: return@repeat
        val text = runCatching { json.decodeFromString<String>(raw) }.getOrNull() ?: return@repeat
        when {
            text == "ERR:signedout" -> return null
            text.startsWith("ERR:") -> {
                Log.w(TAG, "channel probe: ${text.take(120)}")
                return 0
            }
            text.startsWith("OK:") -> return runCatching {
                com.music.bitchord.data.innertube.InnertubeParser
                    .parseAccountChannels(json.parseToJsonElement(text.substring(3))).size
            }.getOrDefault(0)
        }
    }
    return 0
}

private suspend fun WebView.evaluate(script: String): String? =
    kotlinx.coroutines.suspendCancellableCoroutine { done ->
        evaluateJavascript(script) { if (done.isActive) done.resumeWith(Result.success(it)) }
    }

/**
 * Starts `account/accounts_list` from inside the page and leaves its answer in
 * `window.__sonaraChannels` ("OK:<json>", or "ERR:…"). Signed the way the web client signs its own
 * calls: SAPISIDHASH over the timestamp, the SAPISID cookie and the origin.
 */
private const val CHANNELS_PROBE = """
(function () {
  window.__sonaraChannels = null;
  try {
    var cfg = window.ytcfg;
    if (!cfg || !cfg.get || !cfg.get('LOGGED_IN')) { window.__sonaraChannels = 'ERR:signedout'; return 'started'; }
    var m = document.cookie.match(/(?:^|;\s*)(?:SAPISID|__Secure-3PAPISID)=([^;]+)/);
    if (!m) { window.__sonaraChannels = 'ERR:nosapisid'; return 'started'; }
    var origin = location.origin, ts = Math.floor(Date.now() / 1000);
    crypto.subtle.digest('SHA-1', new TextEncoder().encode(ts + ' ' + m[1] + ' ' + origin)).then(function (buf) {
      var hex = Array.prototype.map.call(new Uint8Array(buf), function (b) { return ('0' + b.toString(16)).slice(-2); }).join('');
      var headers = {
        'Content-Type': 'application/json',
        'Authorization': 'SAPISIDHASH ' + ts + '_' + hex,
        'X-Origin': origin,
        'X-Goog-AuthUser': String(cfg.get('SESSION_INDEX') || 0),
        'X-Youtube-Client-Name': String(cfg.get('INNERTUBE_CONTEXT_CLIENT_NAME') || 67),
        'X-Youtube-Client-Version': String(cfg.get('INNERTUBE_CLIENT_VERSION') || '')
      };
      var page = cfg.get('DELEGATED_SESSION_ID');
      if (page) headers['X-Goog-PageId'] = String(page);
      return fetch('/youtubei/v1/account/accounts_list?prettyPrint=false', {
        method: 'POST', credentials: 'include', headers: headers,
        body: JSON.stringify({ context: cfg.get('INNERTUBE_CONTEXT') })
      });
    }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.text();
    }).then(function (t) { window.__sonaraChannels = 'OK:' + t; })
      .catch(function (e) { window.__sonaraChannels = 'ERR:' + e; });
  } catch (e) {
    window.__sonaraChannels = 'ERR:' + e;
  }
  return 'started';
})()
"""

/**
 * The identity of the page as the page itself has it.
 *
 * Returns an object rather than a string so the WebView serialises it — a
 * probe that stringified its own result would come back double-encoded. A page
 * without `ytcfg` (an error page, a redirect that hasn't landed) returns null,
 * which is a fine answer and not an error.
 */
private const val YTCFG_PROBE = """
(function () {
  try {
    if (!window.ytcfg || !window.ytcfg.get) return null;
    var get = function (key) {
      var value = window.ytcfg.get(key);
      return (value === undefined || value === null || value === '') ? null : String(value);
    };
    return {
      loggedIn: String(!!window.ytcfg.get('LOGGED_IN')),
      pageId: get('DELEGATED_SESSION_ID'),
      dataSyncId: get('DATASYNC_ID'),
      authUser: get('SESSION_INDEX'),
      visitorData: get('VISITOR_DATA'),
      clientVersion: get('INNERTUBE_CLIENT_VERSION')
    };
  } catch (e) {
    return null;
  }
})()
"""

private val json = Json { ignoreUnknownKeys = true }

/** The probe's result, or null for anything that isn't the object it promises. */
private fun String?.parseConfig(): JsonObject? =
    this?.let { runCatching { json.parseToJsonElement(it).jsonObject }.getOrNull() }

private fun JsonObject.string(key: String): String? =
    (this[key] as? JsonPrimitive)?.contentOrNull?.takeIf { it.isNotBlank() }
