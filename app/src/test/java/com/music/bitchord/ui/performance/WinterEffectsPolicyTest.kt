package com.music.bitchord.ui.performance

import com.music.bitchord.ui.theme.ThemeEffects
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class WinterEffectsPolicyTest {

    private val all = ThemeEffects(aurora = true, snow = true, stars = true, glass = true, frost = true)

    @Test
    fun lowTierStartsWithStillsOnly_andTheListenerCanStillTurnThingsOn() {
        val low = WinterEffectsPolicy.chosen(WinterEffectPrefs(), DeviceTier.LOW)
        assertFalse(low.aurora || low.snow || low.stars || low.glass)
        assertTrue(low.frost)
        assertTrue(WinterEffectsPolicy.chosen(WinterEffectPrefs(aurora = true), DeviceTier.LOW).aurora)
    }

    @Test
    fun midAndHighTiersStartWithEverythingOn_andAnOffSwitchWins() {
        assertEquals(all, WinterEffectsPolicy.chosen(WinterEffectPrefs(), DeviceTier.HIGH))
        val noSnow = WinterEffectsPolicy.chosen(WinterEffectPrefs(snow = false), DeviceTier.MID)
        assertFalse(noSnow.snow)
        assertTrue(noSnow.aurora)
    }

    @Test
    fun aSwitchTurnedOffRemovesItsEffect_whateverTheMoment() {
        // The bug: "off" used to mean "the still version", which looks the same in a screenshot.
        for (moment in listOf(EffectsMoment(), EffectsMoment(savingPower = true), EffectsMoment(hidden = true))) {
            val r = WinterEffectsPolicy.resolve(all.copy(aurora = false, stars = false), moment)
            assertFalse("$moment", r.aurora)
            assertFalse("$moment", r.stars)
            assertTrue("$moment", r.snow)
        }
    }

    @Test
    fun savingPowerAnimationsOffOrHidden_holdsEverythingStill_butRemovesNothing() {
        for (moment in listOf(
            EffectsMoment(modeActive = true),
            EffectsMoment(savingPower = true),
            EffectsMoment(animationsOff = true),
            EffectsMoment(hidden = true),
        )) {
            val r = WinterEffectsPolicy.resolve(all, moment)
            assertFalse("$moment", r.moving)
            assertFalse("$moment", r.anyAnimated)
            assertTrue("still shown: $moment", r.aurora && r.stars && r.snow && r.frost)
        }
    }

    @Test
    fun onlySavingPowerTakesTheGlassBlurAway() {
        assertTrue(WinterEffectsPolicy.resolve(all, EffectsMoment(hidden = true)).glass)
        assertTrue(WinterEffectsPolicy.resolve(all, EffectsMoment(modeActive = true)).glass)
        assertFalse(WinterEffectsPolicy.resolve(all, EffectsMoment(savingPower = true)).glass)
    }

    @Test
    fun nothingPaused_meansTheChoiceRunsAndMoves() {
        val chosen = ThemeEffects(aurora = true, snow = false, stars = true, glass = true, frost = false)
        val r = WinterEffectsPolicy.resolve(chosen, EffectsMoment())
        assertEquals(chosen.copy(moving = true), r)
        assertTrue(r.anyAnimated)
        // Nothing that moves is on: nothing ticks.
        assertFalse(WinterEffectsPolicy.resolve(ThemeEffects(glass = true, frost = true), EffectsMoment()).anyAnimated)
    }

    @Test
    fun lightModeStaysLightAllDay_unlessNightSkyAfterSunsetIsOn() {
        val noon = 12 * 60
        val night = 22 * 60
        val dawn = 5 * 60 + 59
        assertFalse(WinterScenePolicy.night(appIsDark = false, nightSkyAfterSunset = false, minuteOfDay = night))
        assertTrue(WinterScenePolicy.night(appIsDark = false, nightSkyAfterSunset = true, minuteOfDay = night))
        assertTrue(WinterScenePolicy.night(appIsDark = false, nightSkyAfterSunset = true, minuteOfDay = dawn))
        assertFalse(WinterScenePolicy.night(appIsDark = false, nightSkyAfterSunset = true, minuteOfDay = noon))
        assertTrue(WinterScenePolicy.night(appIsDark = true, nightSkyAfterSunset = false, minuteOfDay = noon))
    }

    @Test
    fun theSunCrossesFromLeftAtSunriseToRightAtSunset() {
        assertEquals(0f, WinterScenePolicy.sunProgress(6 * 60)!!, 1e-6f)
        assertEquals(0.5f, WinterScenePolicy.sunProgress(12 * 60)!!, 1e-6f)
        assertEquals(0.75f, WinterScenePolicy.sunProgress(15 * 60)!!, 1e-6f)
        assertNull(WinterScenePolicy.sunProgress(18 * 60))
        assertNull(WinterScenePolicy.sunProgress(3 * 60))
    }

    @Test
    fun tierRule() {
        assertEquals(DeviceTier.LOW, DeviceTier.classify(3f, lowRam = false, cores = 8, sdk = 34, maxRefreshHz = 120))
        assertEquals(DeviceTier.LOW, DeviceTier.classify(8f, lowRam = true, cores = 8, sdk = 34, maxRefreshHz = 120))
        assertEquals(DeviceTier.LOW, DeviceTier.classify(8f, lowRam = false, cores = 8, sdk = 28, maxRefreshHz = 120))
        assertEquals(DeviceTier.MID, DeviceTier.classify(6f, lowRam = false, cores = 8, sdk = 34, maxRefreshHz = 120))
        assertEquals(DeviceTier.MID, DeviceTier.classify(8f, lowRam = false, cores = 8, sdk = 34, maxRefreshHz = 60))
        assertEquals(DeviceTier.HIGH, DeviceTier.classify(8f, lowRam = false, cores = 8, sdk = 34, maxRefreshHz = 120))
    }

    // ---- Space ----

    @Test
    fun spaceDefaultsFollowTheTier_lowTierStartsStill() {
        val low = WinterEffectsPolicy.chosenSpace(SpaceEffectPrefs(), DeviceTier.LOW)
        assertFalse(low.blackHole || low.infall || low.shootingStars || low.stars || low.galaxies || low.glass || low.audioReactive)
        val mid = WinterEffectsPolicy.chosenSpace(SpaceEffectPrefs(), DeviceTier.MID)
        assertTrue(mid.blackHole && mid.infall && mid.shootingStars && mid.stars && mid.galaxies && mid.glass)
        assertFalse("audio-reactive is a high-tier default", mid.audioReactive)
        assertTrue(WinterEffectsPolicy.chosenSpace(SpaceEffectPrefs(), DeviceTier.HIGH).audioReactive)
    }

    @Test
    fun eachSpaceSwitchControlsItsOwnEffect_bothWays() {
        val high = WinterEffectsPolicy.chosenSpace(SpaceEffectPrefs(), DeviceTier.HIGH)
        val offs = listOf<Pair<SpaceEffectPrefs, (com.music.bitchord.ui.theme.ThemeEffects) -> Boolean>>(
            SpaceEffectPrefs(blackHole = false) to { it.blackHole },
            SpaceEffectPrefs(infall = false) to { it.infall },
            SpaceEffectPrefs(shootingStars = false) to { it.shootingStars },
            SpaceEffectPrefs(twinkle = false) to { it.stars },
            SpaceEffectPrefs(galaxies = false) to { it.galaxies },
            SpaceEffectPrefs(glass = false) to { it.glass },
            SpaceEffectPrefs(audioReactive = false) to { it.audioReactive },
        )
        for ((prefs, flag) in offs) {
            val r = WinterEffectsPolicy.chosenSpace(prefs, DeviceTier.HIGH)
            assertFalse("$prefs", flag(r))
            // Only that one: everything else is still as the tier has it.
            val others = offs.filter { it.first != prefs }.map { it.second(r) }
            assertEquals("$prefs", offs.filter { it.first != prefs }.map { it.second(high) }, others)
        }
        assertTrue(WinterEffectsPolicy.chosenSpace(SpaceEffectPrefs(infall = true), DeviceTier.LOW).infall)
        assertTrue(WinterEffectsPolicy.chosenSpace(SpaceEffectPrefs(shootingStars = true), DeviceTier.LOW).shootingStars)
    }

    @Test
    fun spaceFollowsTheSameRule_userToggleAndNotSavingOrAnimationsOff() {
        val all = WinterEffectsPolicy.chosenSpace(SpaceEffectPrefs(), DeviceTier.HIGH)
        for (moment in listOf(EffectsMoment(modeActive = true), EffectsMoment(savingPower = true), EffectsMoment(animationsOff = true), EffectsMoment(hidden = true))) {
            val r = WinterEffectsPolicy.resolve(all, moment)
            assertFalse("$moment", r.anyAnimated)
            assertTrue("shown, held still: $moment", r.blackHole)
        }
        assertFalse("battery saver takes the glass", WinterEffectsPolicy.resolve(all, EffectsMoment(savingPower = true)).glass)
        assertTrue(WinterEffectsPolicy.resolve(all, EffectsMoment()).anyAnimated)
        // Shooting stars alone keep the clock running; nothing that moves switched on stops it.
        val meteorsOnly = WinterEffectsPolicy.chosenSpace(
            SpaceEffectPrefs(blackHole = false, infall = false, twinkle = false, galaxies = false, audioReactive = false, movingStars = 0), DeviceTier.HIGH,
        )
        assertTrue(WinterEffectsPolicy.resolve(meteorsOnly, EffectsMoment()).anyAnimated)
        val off = WinterEffectsPolicy.chosenSpace(
            SpaceEffectPrefs(blackHole = false, infall = false, shootingStars = false, twinkle = false, galaxies = false, audioReactive = false, movingStars = 0),
            DeviceTier.HIGH,
        )
        assertFalse("nothing moving switched on: the clock stays off", WinterEffectsPolicy.resolve(off, EffectsMoment()).anyAnimated)
        // The audio-reactive disk alone keeps it running: the Player's disk pulses with the disk held still.
        assertTrue(WinterEffectsPolicy.resolve(off.copy(audioReactive = true), EffectsMoment()).anyAnimated)
    }

    @Test
    fun meteorRateAndMovingStars_defaultByTier_clampedAndLive() {
        val low = WinterEffectsPolicy.chosenSpace(SpaceEffectPrefs(), DeviceTier.LOW)
        assertEquals(0, low.movingStars)
        assertEquals(com.music.bitchord.ui.theme.MeteorRates.DEFAULT, low.meteorRate)
        assertEquals(60, WinterEffectsPolicy.chosenSpace(SpaceEffectPrefs(), DeviceTier.MID).movingStars)
        assertEquals(100, WinterEffectsPolicy.chosenSpace(SpaceEffectPrefs(), DeviceTier.HIGH).movingStars)
        // The listener's choice wins, within range.
        assertEquals(4, WinterEffectsPolicy.chosenSpace(SpaceEffectPrefs(meteorRate = 9), DeviceTier.MID).meteorRate)
        assertEquals(0, WinterEffectsPolicy.chosenSpace(SpaceEffectPrefs(meteorRate = -3), DeviceTier.MID).meteorRate)
        assertEquals(300, WinterEffectsPolicy.chosenSpace(SpaceEffectPrefs(movingStars = 5000), DeviceTier.MID).movingStars)
        assertEquals(0, WinterEffectsPolicy.chosenSpace(SpaceEffectPrefs(movingStars = 0), DeviceTier.HIGH).movingStars)
        // Moving stars alone keep the clock running, and hold still when the moment says so.
        val onlyMoving = WinterEffectsPolicy.chosenSpace(
            SpaceEffectPrefs(blackHole = false, infall = false, shootingStars = false, twinkle = false, galaxies = false, audioReactive = false, movingStars = 40),
            DeviceTier.HIGH,
        )
        assertTrue(WinterEffectsPolicy.resolve(onlyMoving, EffectsMoment()).anyAnimated)
        assertFalse(WinterEffectsPolicy.resolve(onlyMoving, EffectsMoment(savingPower = true)).anyAnimated)
        // Faster rates mean shorter gaps between meteors; "normal" is the brief's 8-25 s.
        val gaps = (0 until com.music.bitchord.ui.theme.MeteorRates.LEVELS).map { com.music.bitchord.ui.theme.MeteorRates.longestGap(it) }
        assertEquals(gaps.sortedDescending(), gaps)
        assertTrue(com.music.bitchord.ui.theme.MeteorRates.longestGap(2) in 20f..26f)
    }
}
