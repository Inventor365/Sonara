package com.music.bitchord.ui.theme

import kotlin.test.Test
import kotlin.test.assertTrue

class SpaceEventsTest {

    @Test
    fun clumpsAreAlwaysFallingAndShineAtTheirOwnPlace() {
        val ev = FloatArray(24)
        var t = 0f
        while (t < 600f) {
            SpaceEvents.at(t, ev)
            val active = (0 until 5).filter { ev[it * 4 + 3] > 0f }
            assertTrue(active.isNotEmpty(), "no clump at t=$t")
            for (k in active) {
                val r = ev[k * 4]
                val phi = ev[k * 4 + 1]
                assertTrue(r in 6f..20f, "clump $k at r=$r, t=$t")
                // At its own centre, its light is its amplitude.
                val light = eventLight(r, phi, ev)
                assertTrue(light >= ev[k * 4 + 3] * 0.99f, "clump $k at t=$t: light $light < amp ${ev[k * 4 + 3]}")
            }
            t += 0.7f
        }
    }

    @Test
    fun theFirstTidalStreamComesHalfAMinuteIn_andTheDiskShadesItLit() {
        val ev = FloatArray(24)
        SpaceEvents.at(37f, ev)
        assertTrue(ev[23] > 0.3f, "stream amp ${ev[23]}")
        SpaceEvents.at(20f, ev)
        assertTrue(ev[23] == 0f)
    }
}
