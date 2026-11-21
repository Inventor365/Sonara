package com.music.bitchord.ui.theme

import android.graphics.BitmapShader
import android.graphics.RuntimeShader
import android.graphics.Shader
import android.os.Build
import androidx.annotation.RequiresApi
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.ShaderBrush
import androidx.compose.ui.graphics.asAndroidBitmap

/**
 * The accretion disk, shaded from the offline-traced LUT (scripts/space/bake_space_assets.py).
 * Nothing is traced here: each texel reads where its light crossed the disk and with what redshift,
 * turns the plasma texture by Keplerian rotation and colours it — three texture reads and some
 * arithmetic, at the LUT's size (~100k texels), twenty times a second. The CPU twin is [DiskRaster].
 */
actual class BlackHoleShader actual constructor() {
    // A shader the platform refuses to compile falls back to the CPU raster, not a crash.
    private val impl: Impl? = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
        runCatching { Impl() }.onFailure { android.util.Log.w("BlackHoleShader", "AGSL refused; shading on the CPU", it) }.getOrNull()
    } else {
        null
    }

    actual val supported: Boolean get() = impl != null

    actual fun brush(
        lutA: ImageBitmap, lutB: ImageBitmap, disk: ImageBitmap, timeSec: Float, energy: Float, tint: Color, events: FloatArray,
    ): Brush? = impl?.brush(lutA, lutB, disk, timeSec, energy, tint, events)

    @RequiresApi(Build.VERSION_CODES.TIRAMISU)
    private class Impl {
        private val shader = RuntimeShader(AGSL)
        private val brush = ShaderBrush(shader)
        private var bound: ImageBitmap? = null

        fun brush(lutA: ImageBitmap, lutB: ImageBitmap, disk: ImageBitmap, t: Float, energy: Float, tint: Color, ev: FloatArray): Brush {
            if (bound !== lutA) {
                // The LUTs are data: read by exact texel, never filtered. The plasma is a picture:
                // filtered, and repeating round the orbit.
                fun exact(img: ImageBitmap) = BitmapShader(img.asAndroidBitmap(), Shader.TileMode.CLAMP, Shader.TileMode.CLAMP).apply {
                    filterMode = BitmapShader.FILTER_MODE_NEAREST
                }
                shader.setInputBuffer("lutA", exact(lutA))
                shader.setInputBuffer("lutB", exact(lutB))
                shader.setInputBuffer(
                    "disk",
                    BitmapShader(disk.asAndroidBitmap(), Shader.TileMode.REPEAT, Shader.TileMode.CLAMP).apply {
                        filterMode = BitmapShader.FILTER_MODE_LINEAR
                    },
                )
                shader.setFloatUniform("diskSize", disk.width.toFloat(), disk.height.toFloat())
                bound = lutA
            }
            // Kept to a few minutes' range: float precision for phi - Omega t stays fine.
            shader.setFloatUniform("time", t % 2400f)
            shader.setFloatUniform("energy", energy.coerceIn(0f, 1f))
            shader.setFloatUniform("tint", tint.red, tint.green, tint.blue, tint.alpha)
            shader.setFloatUniform("ev0", ev[0], ev[1], ev[2], ev[3])
            shader.setFloatUniform("ev1", ev[4], ev[5], ev[6], ev[7])
            shader.setFloatUniform("ev2", ev[8], ev[9], ev[10], ev[11])
            shader.setFloatUniform("ev3", ev[12], ev[13], ev[14], ev[15])
            shader.setFloatUniform("ev4", ev[16], ev[17], ev[18], ev[19])
            shader.setFloatUniform("stream", ev[20], ev[21], ev[22], ev[23])
            return brush
        }
    }
}

actual fun writeSpacePixels(image: ImageBitmap, pixels: IntArray) {
    // Bitmap.setPixels takes unpremultiplied colour; the raster's is premultiplied.
    val un = IntArray(pixels.size)
    for (i in pixels.indices) {
        val p = pixels[i]
        val a = (p ushr 24) and 0xFF
        if (a == 0) { un[i] = 0; continue }
        fun c(v: Int) = ((v * 255 + a / 2) / a).coerceAtMost(255)
        un[i] = (a shl 24) or (c((p shr 16) and 0xFF) shl 16) or (c((p shr 8) and 0xFF) shl 8) or c(p and 0xFF)
    }
    val bmp = image.asAndroidBitmap()
    bmp.setPixels(un, 0, image.width, 0, 0, image.width, image.height)
}

private const val AGSL = """
uniform shader lutA;
uniform shader lutB;
uniform shader disk;
uniform float2 diskSize;
uniform float time;
uniform float energy;
uniform float4 tint;
uniform float4 ev0;
uniform float4 ev1;
uniform float4 ev2;
uniform float4 ev3;
uniform float4 ev4;
uniform float4 stream;

const float TAU = 6.2831853;
const float PI = 3.14159265;
const float R_IN = 6.0;
const float R_OUT = 20.0;
const float OMEGA_IN = 0.26179939;   // TAU / 24 s: the inner edge's turn
const float T_MAX = 0.81903625;

// A 16-bit value from two 8-bit channels, as a fraction. Every intermediate stays small: GPUs may run
// this at half precision, where hi * 255 * 256 (up to 65280) overflows and phi collapses to a constant.
float u16(float hi, float lo) { return hi * 0.99610895 + lo * 0.0038910506; }

// Observed temperature -> colour: deep red, amber, warm white, white, blue-white.
float3 ramp(float t) {
    float3 c = mix(float3(0.25, 0.015, 0.0), float3(0.80, 0.14, 0.015), clamp(t / 0.30, 0.0, 1.0));
    c = mix(c, float3(1.0, 0.42, 0.07), clamp((t - 0.30) / 0.25, 0.0, 1.0));
    c = mix(c, float3(1.0, 0.74, 0.40), clamp((t - 0.55) / 0.23, 0.0, 1.0));
    c = mix(c, float3(1.0, 0.93, 0.82), clamp((t - 0.78) / 0.20, 0.0, 1.0));
    c = mix(c, float3(0.94, 0.96, 1.0), clamp((t - 0.98) / 0.20, 0.0, 1.0));
    return mix(c, float3(0.76, 0.85, 1.0), clamp((t - 1.18) / 0.27, 0.0, 1.0));
}

float3 filmic(float3 x) { return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0); }

// A clump on its orbit: Gaussian across the orbit and, stretched by c.z, along it. The distance
// along the orbit is the chord, 2 r sin(dphi / 2): smooth, and with no wrap-around to get wrong.
float clump(float4 c, float r, float phi) {
    if (c.w <= 0.0) return 0.0;
    float dr = (r - c.x) / 0.22;
    float ds = 2.0 * r * sin(0.5 * (phi - c.y)) / c.z;
    return exp(-dr * dr - ds * ds) * c.w;
}

half4 main(float2 p) {
    float2 tx = floor(p) + 0.5;
    half4 a = lutA.eval(tx);
    half4 b = lutB.eval(tx);
    float cov = b.g;
    if (cov <= 0.002) return half4(0);
    float phi = u16(a.r, a.g) * TAU;
    float r = R_IN + (a.b * 255.0 - 1.0) / 254.0 * (R_OUT - R_IN);
    float g = 0.2 + b.r * 1.6;
    float far = b.b > 0.5 ? 0.85 : 1.0;

    // Thin-disk temperature, hottest just outside the ISCO; the plasma turned by Kepler.
    float temp = pow(r / R_IN, -0.75) * pow(max(1.0 - 0.55 * sqrt(R_IN / r), 0.0), 0.25) / T_MAX;
    float omega = OMEGA_IN * pow(r / R_IN, -1.5);
    float u = fract((phi - omega * time) / TAU);
    float fy = clamp((r - R_IN) / (R_OUT - R_IN), 0.0, 1.0) * (diskSize.y - 1.0) + 0.5;
    // Churn: a second layer of the plasma turning at 0.78 of the speed, from other rows, so
    // filaments form, stretch and dissolve rather than only going round.
    float u2 = fract((phi - omega * 0.78 * time) / TAU + 0.37);
    float fy2 = mod(fy + 23.0, diskSize.y);
    float t1 = disk.eval(float2(u * diskSize.x, fy)).r;
    float t2 = disk.eval(float2(u2 * diskSize.x, fy2)).r;
    float tex = (0.375 + (mix(t1, t2, 0.45) - 0.375) * 1.3) * 1.6;

    // Doppler and gravitational shift: brighter and bluer-white where the gas comes toward us.
    float3 col = ramp(clamp(temp * g * 1.05, 0.0, 1.6));
    col = mix(col, col * tint.rgb * 1.6, tint.a * 0.18);
    float edge = pow(clamp((R_OUT - r) / 9.0, 0.0, 1.0), 2.2) * clamp((r - R_IN) / 0.35, 0.0, 1.0);
    float g2 = g * g;
    float inten = g2 * g2 * pow(temp, 2.6) * tex * edge * (2.6 + 0.35 * energy) * far;

    // Matter falling in, and a tidal stream, in the disk plane: lensed exactly as the disk is.
    float e = clump(ev0, r, phi) + clump(ev1, r, phi) + clump(ev2, r, phi) + clump(ev3, r, phi) + clump(ev4, r, phi);
    if (stream.w > 0.0) {
        float ang = fract((stream.x - phi) / TAU) * TAU;
        if (ang < stream.y) {
            float rs = stream.z - 2.2 * (ang / 3.6);
            float dr = (r - rs) / (0.40 + 0.40 * ang);
            e += exp(-dr * dr) * exp(-ang / max(0.3, stream.y) * 2.2) * stream.w;
        }
    }
    e *= g2 * g;

    float3 lit = pow(filmic(col * inten + float3(1.0, 0.86, 0.66) * e), float3(1.0 / 2.2));
    // Premultiplied and valid: a layer clamps colour above its alpha, which greys the disk out. So
    // the disk covers at least as much as it shines (over the dark sky behind, the same look).
    float3 rgb = lit * cov;
    float alpha = max(clamp(inten * 1.5 + e, 0.0, 1.0) * cov, max(rgb.r, max(rgb.g, rgb.b)));
    return half4(half3(rgb), half(alpha));
}
"""
