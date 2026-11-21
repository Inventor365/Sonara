package com.music.bitchord.ui.theme

import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asSkiaBitmap

/** The desktop shades Space's disk on the CPU ([DiskRaster]): no runtime shader here. */
actual class BlackHoleShader actual constructor() {
    actual val supported: Boolean = false

    actual fun brush(
        lutA: ImageBitmap, lutB: ImageBitmap, disk: ImageBitmap, timeSec: Float, energy: Float, tint: Color, events: FloatArray,
    ): Brush? = null
}

actual fun writeSpacePixels(image: ImageBitmap, pixels: IntArray) {
    // Skia's N32 bitmap is premultiplied BGRA/RGBA by platform: write through its own pixel setter.
    val bmp = image.asSkiaBitmap()
    val bytes = ByteArray(pixels.size * 4)
    val bgra = bmp.colorInfo.colorType == org.jetbrains.skia.ColorType.BGRA_8888
    for (i in pixels.indices) {
        val p = pixels[i]
        val a = (p ushr 24) and 0xFF
        val r = (p shr 16) and 0xFF
        val g = (p shr 8) and 0xFF
        val b = p and 0xFF
        val o = i * 4
        if (bgra) {
            bytes[o] = b.toByte(); bytes[o + 1] = g.toByte(); bytes[o + 2] = r.toByte()
        } else {
            bytes[o] = r.toByte(); bytes[o + 1] = g.toByte(); bytes[o + 2] = b.toByte()
        }
        bytes[o + 3] = a.toByte()
    }
    bmp.installPixels(bmp.imageInfo, bytes, image.width * 4)
}
