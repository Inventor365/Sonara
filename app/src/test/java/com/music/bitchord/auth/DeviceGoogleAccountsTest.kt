package com.music.bitchord.auth

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class DeviceGoogleAccountsTest {

    @Test
    fun theLoginCarriesTheChosenAccount_forGooglesCurrentAndOlderPages() {
        val url = DeviceGoogleAccounts.prefilledLoginUrl("listener+music@gmail.com")
        assertTrue(url.startsWith("https://accounts.google.com/ServiceLogin?"))
        // `login_hint` is what fills the address in today (checked on a phone); `Email` for older pages.
        assertTrue(url.contains("&login_hint=listener%2Bmusic%40gmail.com"))
        assertEquals("listener%2Bmusic%40gmail.com", url.substringAfter("&Email="))
        // The account is already chosen: no account picker, and YouTube Music opens as that account.
        assertTrue("prompt=select_account" !in url)
        val home = java.net.URLDecoder.decode(url.substringAfter("continue=").substringBefore("&"), "UTF-8")
        assertEquals("https://music.youtube.com/?authuser=listener+music@gmail.com", home)
    }

    @Test
    fun theSessionMustBeTheAccountTheLoginNamed() {
        val url = DeviceGoogleAccounts.prefilledLoginUrl("listener+music@gmail.com")
        assertEquals("listener+music@gmail.com", DeviceGoogleAccounts.hintedEmail(url))
        assertEquals(null, DeviceGoogleAccounts.hintedEmail(DeviceGoogleAccounts.LOGIN_URL))
        assertEquals(null, DeviceGoogleAccounts.hintedEmail(null))
    }
}
