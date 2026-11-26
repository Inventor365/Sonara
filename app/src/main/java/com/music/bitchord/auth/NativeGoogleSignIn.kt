package com.music.bitchord.auth

import android.accounts.Account
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.util.Log
import com.google.android.gms.auth.api.identity.AuthorizationRequest
import com.google.android.gms.auth.api.identity.AuthorizationResult
import com.google.android.gms.auth.api.identity.Identity
import com.google.android.gms.common.ConnectionResult
import com.google.android.gms.common.GoogleApiAvailability
import com.google.android.gms.common.api.ApiException
import com.google.android.gms.common.api.CommonStatusCodes
import com.google.android.gms.common.api.Scope
import com.music.bitchord.data.backup.await

/**
 * Signing in to YouTube Music the way other Android apps sign in with Google: Google Play
 * services' own sheet lists the accounts already on the phone, one tap picks one (and, for an
 * account with brand channels, Google's own channel picker follows), and no password or web page
 * is involved. What comes back is an OAuth access token for the `youtube` scope, which
 * [com.music.bitchord.data.innertube.Innertube.bearer] sends instead of the web session's cookies.
 *
 * It needs an OAuth client for Sonara in a Google Cloud project: an "Android" client registered
 * for this package name and signing certificate, with the YouTube Data API enabled. Until one
 * exists Google refuses the request ([Outcome.NotConfigured]) and the web sign-in is used instead.
 * Off by default for that reason — see AppSettings.nativeGoogleSignIn.
 *
 * No token is stored: Play services keeps the grant and hands back a fresh token on request
 * ([freshToken]), without any UI once the listener has agreed.
 */
object NativeGoogleSignIn {

    private const val SCOPE_YOUTUBE = "https://www.googleapis.com/auth/youtube"
    private const val ACCOUNT_TYPE = "com.google"
    private const val TAG = "BitChord"

    sealed interface Outcome {
        data class Granted(val accessToken: String, val email: String?) : Outcome

        /** Google's sheet has to be shown: only an activity can start [intent]. */
        data class NeedsConsent(val intent: PendingIntent) : Outcome

        /** No OAuth client is registered for this build's package and certificate. */
        data object NotConfigured : Outcome

        /** Backed out of Google's sheet. */
        data object Cancelled : Outcome

        data class Failed(val reason: String) : Outcome
    }

    /** Whether the phone has Google Play services to sign in with at all. */
    fun available(context: Context): Boolean =
        GoogleApiAvailability.getInstance().isGooglePlayServicesAvailable(context) == ConnectionResult.SUCCESS

    /**
     * A token for [account], or the sheet that gets one. With [account] null, Google's sheet lets
     * the listener pick any account on the phone.
     */
    suspend fun authorize(context: Context, account: String?): Outcome = attempt {
        val request = AuthorizationRequest.builder()
            .setRequestedScopes(listOf(Scope(SCOPE_YOUTUBE)))
            .apply { if (account != null) setAccount(Account(account, ACCOUNT_TYPE)) }
            .build()
        Identity.getAuthorizationClient(context).authorize(request).await().toOutcome()
    }

    /**
     * What Google's sheet returned. Its status decides between a listener who backed out
     * ([Outcome.Cancelled]) and a refusal ([Outcome.NotConfigured], [Outcome.Failed]); an
     * activity closed with nothing to say counts as backed out only when it wasn't an OK.
     */
    fun fromIntent(context: Context, data: Intent?, resultCode: Int = android.app.Activity.RESULT_OK): Outcome = attemptNow {
        if (data == null) {
            return@attemptNow if (resultCode == android.app.Activity.RESULT_OK) Outcome.Failed("Google returned nothing") else Outcome.Cancelled
        }
        Identity.getAuthorizationClient(context).getAuthorizationResultFromIntent(data).toOutcome()
    }

    /** A fresh token for an account already signed in this way, with no UI; null if it needs the sheet again. */
    suspend fun freshToken(context: Context, account: String): String? =
        (authorize(context, account) as? Outcome.Granted)?.accessToken

    /**
     * Points requests at [email]'s native sign-in: no cookie, and a token from Play services,
     * minted on the first request that needs one and again whenever Google says it has expired.
     */
    fun install(context: Context, email: String) {
        val app = context.applicationContext
        com.music.bitchord.data.innertube.Innertube.cookie = null
        com.music.bitchord.data.innertube.Innertube.bearer = null
        com.music.bitchord.data.innertube.Innertube.refreshBearer = { freshToken(app, email) }
    }

    /** Back to web sessions only: a cookie session never reaches for a token. */
    fun uninstall() {
        com.music.bitchord.data.innertube.Innertube.bearer = null
        com.music.bitchord.data.innertube.Innertube.refreshBearer = null
    }

    private fun AuthorizationResult.toOutcome(): Outcome {
        val pending = pendingIntent
        if (hasResolution() && pending != null) return Outcome.NeedsConsent(pending)
        val token = accessToken ?: return Outcome.Failed("Google returned no access token")
        val email = runCatching { toGoogleSignInAccount()?.email }.getOrNull()
        return Outcome.Granted(token, email)
    }

    private suspend fun attempt(block: suspend () -> Outcome): Outcome = try {
        block()
    } catch (e: ApiException) {
        e.toOutcome()
    } catch (e: Exception) {
        Log.w(TAG, "native Google sign-in failed: ${e.message}")
        Outcome.Failed(e.message ?: e.javaClass.simpleName)
    }

    private fun attemptNow(block: () -> Outcome): Outcome = try {
        block()
    } catch (e: ApiException) {
        e.toOutcome()
    } catch (e: Exception) {
        Outcome.Failed(e.message ?: e.javaClass.simpleName)
    }

    private fun ApiException.toOutcome(): Outcome = when (statusCode) {
        // What an unregistered package/certificate pair is answered with.
        CommonStatusCodes.DEVELOPER_ERROR -> Outcome.NotConfigured.also { Log.w(TAG, "native Google sign-in is not set up for this build") }
        CommonStatusCodes.CANCELED -> Outcome.Cancelled
        else -> Outcome.Failed("Google sign-in error $statusCode: $message")
    }
}

