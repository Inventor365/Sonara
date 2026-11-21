package com.music.bitchord.ui.theme

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.layout.onPlaced
import androidx.compose.ui.layout.positionInWindow
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalWindowInfo
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.State
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.FilterQuality
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.layer.GraphicsLayer
import androidx.compose.ui.graphics.layer.drawLayer
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import com.music.bitchord.sharedui.resources.*
import org.jetbrains.compose.resources.DrawableResource
import org.jetbrains.compose.resources.imageResource
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt

/*
 * Space: a Schwarzschild black hole and the sky around it, rendered the way scientific
 * visualisations are, with the cost paid offline (scripts/space/):
 *
 *  - trace_blackhole.py integrates light rays through curved spacetime around the hole;
 *  - bake_space_assets.py turns those rays into, per scene, a PLATE (the sky as bent by the
 *    hole, its pure-black shadow, the photon ring and the disk's glow) and a small LUT: for each
 *    texel whose light came from the accretion disk, the radius, azimuth and redshift g where the
 *    ray crossed it, and how much of the texel it covers;
 *  - here, the disk is shaded from the LUT by a shader that only looks things up: the plasma
 *    texture turned by Keplerian differential rotation, Doppler-beamed and coloured by g. Matter
 *    falling in lives in the disk plane, so it goes through the same LUT and lenses as the disk does.
 *
 * Every screen has its own scene (see [SpaceScreen]); moving parts are their own canvases in their
 * own layers, and nothing is read during composition.
 */

/** The disk's shader (AGSL, Android 13+); null brush where there is none, and [DiskRaster] shades instead. */
expect class BlackHoleShader() {
    val supported: Boolean

    /**
     * The disk shaded into a frame of the LUT's size. [events] holds 5 clumps (r, phi, length, amp)
     * and the tidal stream (head, length, r0, amp); [tint] is the album's colour (alpha = how much).
     */
    fun brush(lutA: ImageBitmap, lutB: ImageBitmap, disk: ImageBitmap, timeSec: Float, energy: Float, tint: Color, events: FloatArray): androidx.compose.ui.graphics.Brush?
}

/** Copies ARGB [pixels] into [image] (for the disk shaded on the CPU). */
expect fun writeSpacePixels(image: ImageBitmap, pixels: IntArray)

/** Which scene a page sits on. */
enum class SpaceScreen { HOME, EXPLORE, LIBRARY, SEARCH, VOID }

// ---- Geometry: must match scripts/space/bake_space_assets.py --------------------------------------

/** One baked view of the hole: where its LUT sits around the hole, in M (the hole's mass), y down. */
@Immutable
class HoleView internal constructor(val lx0: Float, val lx1: Float, val ly0: Float, val ly1: Float)

private val HOME_VIEW = HoleView(-21f, 5.4f, -12f, 11f)
private val PLAYER_VIEW = HoleView(-11f, 11f, -12f, 9f)

/** Home's plate is 1152 x 1500 at 1152 wide; the hole at (1010, 856), 26 px per M. */
private const val HOME_PLATE_W = 1152f
private const val HOME_HOLE_X = 1010f / HOME_PLATE_W
private const val HOME_HOLE_Y = 856f / HOME_PLATE_W
private const val HOME_UNIT = 26f / HOME_PLATE_W

/** The Player's plate covers x -11..11 M and y -14..14 M about the hole; the art is 13 M across. */
private const val PLAYER_X0 = -11f
private const val PLAYER_Y0 = -14f
private const val PLAYER_W = 22f
private const val PLAYER_H = 28f
const val PLAYER_ART_M = 13f

/** The Einstein radius for the baked views (camera 80 M from the hole), in M: stars bend round it. */
private const val THETA_E = 17.9f

/** Lensing is exact within LENS_NEAR M of the hole and fades out by LENS_NEAR + LENS_FADE (as baked). */
private const val LENS_NEAR = 10f
private const val LENS_FADE = 14f

/** The shadow's edge (3 sqrt 3 M) and the photon ring just outside it: nothing is seen within. */
private const val SHADOW_M = 5.6f

private const val R_IN = 6f
private const val R_OUT = 20f
private const val TAU = (2 * PI).toFloat()
/** The inner edge turns once in 24 s, the outer (r = 20) in about two and a half minutes: Kepler, slowed for a UI. */
private const val OMEGA_IN = TAU / 24f
private const val T_MAX = 0.81903625f

/** How far the page under Space's sky has scrolled (px): the app writes it, the scene and the Pass read it in draw. */
val SpacePageScroll = androidx.compose.runtime.mutableFloatStateOf(0f)

/** The page floor under every plate (the plates fade into it). */
val SPACE_FLOOR = Color(0xFF04060B)

// ---- The art --------------------------------------------------------------------------------------

/** The disk's texture and one view's LUT. */
@Immutable
class SpaceDiskArt(val lutA: ImageBitmap, val lutB: ImageBitmap, val disk: ImageBitmap)

@Composable
private fun rememberDiskArt(a: DrawableResource, b: DrawableResource): SpaceDiskArt {
    val la = imageResource(a)
    val lb = imageResource(b)
    val disk = imageResource(Res.drawable.space_disk)
    return remember(la, lb, disk) { SpaceDiskArt(la, lb, disk) }
}

/** The still Home scene, for the theme picker and the welcome screen. */
@Immutable
class SpaceStill(val image: ImageBitmap)

@Composable
fun rememberSpaceStill(): SpaceStill {
    val img = imageResource(Res.drawable.space_home_still)
    return remember(img) { SpaceStill(img) }
}

/** The still scene across this scope's width, for previews that show Space without its live scene. */
fun DrawScope.drawSpaceStill(still: SpaceStill) {
    val w = size.width
    drawRect(SPACE_FLOOR)
    drawImage(still.image, dstSize = IntSize(w.toInt(), (w * 1500f / 1152f).toInt()), filterQuality = FilterQuality.Medium)
}

// ---- The scene ------------------------------------------------------------------------------------

/**
 * Space's sky under every page: [screen]'s own scene, back to front —
 *
 * - HOME: the black hole, large and partly off the right edge, below the toolbar; the disk turning
 *   ([ThemeEffects.blackHole]), matter falling in and the rare tidal flare ([ThemeEffects.infall]);
 * - LIBRARY: a spiral galaxy (M51) rising over the dark limb of a world, turning imperceptibly;
 * - EXPLORE: a wide nebula field (Webb's Cosmic Cliffs, regraded); SEARCH: a deep field;
 * - VOID (Settings, pushed pages): sparse stars.
 *
 * Over all of them: twinkle ([ThemeEffects.stars]) and shooting stars ([ThemeEffects.shootingStars]).
 * [scroll] (px the page has scrolled) is read only in draw, for a gentle parallax.
 */
@Composable
fun SpaceScene(
    screen: SpaceScreen,
    effects: ThemeEffects,
    time: State<Float>,
    layer: GraphicsLayer?,
    shader: BlackHoleShader,
    scroll: State<Float>,
    modifier: Modifier = Modifier,
) {
    // Off Home the motion is slow (a galaxy turning half a degree a second, stars drifting a few dp
    // a second): drawn at 15 fps, where it looks the same and each frame — which redraws the page's
    // glass and cards over it — costs half as often. Home's disk keeps the full clock.
    val home = screen == SpaceScreen.HOME
    val paced = remember(time, home) { if (home) time else derivedStateOf { floor(time.value * 15f) / 15f } }
    // Meteors only ask for frames while one is crossing.
    val meteorTime = remember(time, effects.meteorRate) {
        derivedStateOf { val t = time.value; if (Meteors.crossing(t, effects.meteorRate)) t else -1f }
    }
    Box(modifier.fillMaxSize()) {
        // The floor stays put; everything over it moves up with the page as one layer — a layer
        // translation, so scrolling redraws nothing of the sky.
        Canvas(Modifier.fillMaxSize()) { drawFloor() }
        Box(Modifier.fillMaxSize().graphicsLayer { translationY = -min(scroll.value * 0.12f, size.width * 0.35f) }) {
        when (screen) {
            SpaceScreen.HOME -> HomeScene(effects, time, layer, shader, scroll)
            SpaceScreen.LIBRARY -> LibraryScene(effects, paced, scroll)
            SpaceScreen.EXPLORE -> DriftPlate(Res.drawable.space_explore, 1300f, effects, paced, scroll, 60f, 20f)
            SpaceScreen.SEARCH -> DriftPlate(Res.drawable.space_search, 1200f, effects, paced, scroll, 22f, 10f)
            SpaceScreen.VOID -> VoidPlate()
        }
        if (effects.stars || effects.movingStars > 0) {
            val twinkle = remember { Twinkle() }
            val drifting = remember { MovingStars() }
            Canvas(Modifier.fillMaxSize().graphicsLayer()) {
                val t = paced.value
                val par = 0f
                // On Home the moving stars are drawn under the disk, through the lens (HomeScene).
                if (effects.movingStars > 0 && !home) drifting.draw(this, t, effects.movingStars, home, par)
                if (effects.stars) twinkle.draw(this, t, effects.moving, home, par)
            }
        }
        if (effects.shootingStars && effects.moving) {
            val meteors = remember { Meteors() }
            Canvas(Modifier.fillMaxSize().graphicsLayer()) {
                val t = meteorTime.value
                if (t >= 0f) meteors.draw(this, t, home, effects.meteorRate)
            }
        }
        }
    }
}


@Composable
private fun HomeScene(effects: ThemeEffects, time: State<Float>, layer: GraphicsLayer?, shader: BlackHoleShader, scroll: State<Float>) {
    val plate = imageResource(Res.drawable.space_home)
    val art = rememberDiskArt(Res.drawable.space_home_lut_a, Res.drawable.space_home_lut_b)
    val disk = remember(art) { DiskRenderer(art) }
    Canvas(Modifier.fillMaxSize().graphicsLayer()) {
        val w = size.width
        val dy = 0f
        drawImage(plate, dstOffset = IntOffset(0, dy.toInt()), dstSize = IntSize(w.toInt(), (w * 1500f / HOME_PLATE_W).toInt()), filterQuality = FilterQuality.Medium)
    }
    if (effects.movingStars > 0) {
        // Stars drifting behind the hole, seen through it: they swing round it in arcs, stretch
        // near the Einstein ring, show a faint second image on the far side, and are lost in the
        // shadow. Under the disk, which covers them where it is in front.
        val lensed = remember { MovingStars() }
        Canvas(Modifier.fillMaxSize().graphicsLayer()) {
            val w = size.width
            val c = Offset(w * HOME_HOLE_X, w * HOME_HOLE_Y )
            lensed.drawLensed(this, time.value, effects.movingStars, c, w * HOME_UNIT)
        }
    }
    Canvas(Modifier.fillMaxSize().graphicsLayer()) {
        val w = size.width
        val unit = w * HOME_UNIT
        val c = Offset(w * HOME_HOLE_X, w * HOME_HOLE_Y )
        if (c.y + HOME_VIEW.ly1 * unit < 0f) return@Canvas // scrolled away: nothing to shade
        disk.draw(this, HOME_VIEW, c, unit, effects, time.value, layer, shader, energy = 0f, tint = Color.Transparent)
    }
}

/**
 * Under Home's greeting: room for the black hole, so the first card starts just below its lower
 * ring and nothing sits over its face. Measured once, at Home's top, and kept for the window's
 * width — a header recycled while scrolled would otherwise measure itself somewhere else.
 */
@Composable
fun SpaceHeroClearance() {
    val density = LocalDensity.current
    val width = LocalWindowInfo.current.containerSize.width
    val measured = remember(width) { mutableStateOf(heroClearance.takeIf { it.first == width }?.second) }
    val h = measured.value ?: 0f
    Spacer(
        Modifier
            .fillMaxWidth()
            .height(with(density) { h.toDp() })
            .then(
                if (measured.value != null) {
                    Modifier
                } else {
                    Modifier.onPlaced { coords ->
                        // The hole's lower ring and its glow end 7.8 M below its centre.
                        val target = width * (HOME_HOLE_Y + 7.8f * HOME_UNIT)
                        val top = coords.positionInWindow().y
                        if (top in 0f..target) {
                            heroClearance = width to target - top
                            measured.value = target - top
                        }
                    }
                },
            ),
    )
}

private var heroClearance: Pair<Int, Float> = 0 to 0f

@Composable
private fun LibraryScene(effects: ThemeEffects, time: State<Float>, scroll: State<Float>) {
    val galaxy = imageResource(Res.drawable.space_galaxy_m51)
    val limb = imageResource(Res.drawable.space_library_limb)
    VoidPlate(stars = 260, seed = 11)
    Canvas(Modifier.fillMaxSize().graphicsLayer()) {
        // The galaxy turns, slowly but visibly (once in twelve minutes), and breathes a little.
        val w = size.width
        val t = if (effects.galaxies && effects.moving) time.value else 0f
        // In the header, between the title and the Account button, above the Pass.
        val side = w * 0.46f * (1f + 0.018f * sin(t / 6.5f))
        val dy = 0f
        translate(w * 0.62f, w * 0.27f + dy) {
            rotate(-28f - t * 0.5f, pivot = Offset.Zero) {
                drawImage(
                    galaxy,
                    dstOffset = IntOffset((-side / 2).toInt(), (-side / 2).toInt()),
                    dstSize = IntSize(side.toInt(), side.toInt()),
                    filterQuality = FilterQuality.Low,
                )
            }
        }
    }
    Canvas(Modifier.fillMaxSize().graphicsLayer()) {
        // The world's limb, in front of the galaxy: its rim at 0.37 of the width, just above the Pass.
        val w = size.width
        val top = w * 0.37f - w * 300f / 1152f 
        drawImage(limb, dstOffset = IntOffset(0, top.toInt()), dstSize = IntSize(w.toInt(), (w * 700f / 1152f).toInt()), filterQuality = FilterQuality.Medium)
    }
}

/** A plate a little wider than the screen, drifting by [ax] x [ay] px (at 1152 wide) over minutes. */
@Composable
private fun DriftPlate(res: DrawableResource, plateW: Float, effects: ThemeEffects, time: State<Float>, scroll: State<Float>, ax: Float, ay: Float) {
    val plate = imageResource(res)
    Canvas(Modifier.fillMaxSize().graphicsLayer()) {
        val w = size.width
        val k = w / 1152f
        val t = if (effects.galaxies && effects.moving) time.value else 0f
        val extra = (plateW - 1152f) * k
        // A slow camera pan, a pixel or two a second, by sub-pixel steps (no integer jitter).
        val dx = -extra / 2f + min(ax * k, extra / 2f) * sin(t / 29f)
        val dy = ay * k * sin(t / 37f) 
        translate(dx, dy) {
            drawImage(
                plate,
                dstSize = IntSize((plateW * k).toInt(), (plate.height * plateW * k / plate.width).toInt()),
                filterQuality = FilterQuality.Medium,
            )
        }
    }
}

/** Settings, sheets and pushed pages: the void and a scatter of faint stars. Drawn once. */
@Composable
private fun VoidPlate(stars: Int = 110, seed: Long = 41) {
    Canvas(Modifier.fillMaxSize().graphicsLayer()) {
        val rnd = java.util.Random(seed)
        val w = size.width
        repeat(stars) {
            val m = rnd.nextFloat().pow(3.2f)
            val c = StarTemps[rnd.nextInt(StarTemps.size)]
            drawCircle(c.copy(alpha = 0.18f + 0.62f * m), (0.45f + 0.9f * m) * density, Offset(rnd.nextFloat() * w, rnd.nextFloat() * size.height))
        }
    }
}

/** The page floor: #020306 at the top, deepening the other way to #07090F at the foot. */
private fun DrawScope.drawFloor() {
    drawRect(Brush.verticalGradient(0f to Color(0xFF020306), 0.45f to SPACE_FLOOR, 1f to Color(0xFF07090F)))
}

private val StarTemps = listOf(Color(0xFFBFD3FF), Color(0xFFE5ECFF), Color.White, Color(0xFFFFF1DC), Color(0xFFFFDDB5))

// ---- The disk -------------------------------------------------------------------------------------

/** How often the disk is re-shaded while it turns: the inner edge moves under 0.5 deg between frames. */
private const val DISK_FPS = 30f
private const val DISK_FPS_CPU = 8f

/**
 * Shades one view's disk into a frame of its LUT's size — on the GPU into [GraphicsLayer], or on the
 * CPU into a bitmap — and draws it scaled over the scene at the hole. Shaded again only when the
 * clock has moved a frame on (or once, when it holds still).
 */
class DiskRenderer(private val art: SpaceDiskArt) {
    private val events = FloatArray(24)
    private var lastKey = Float.NaN
    private var raster: DiskRaster? = null
    private var still: ImageBitmap? = null

    fun draw(
        scope: DrawScope, v: HoleView, centre: Offset, unit: Float, effects: ThemeEffects, t: Float,
        layer: GraphicsLayer?, shader: BlackHoleShader, energy: Float, tint: Color,
    ) = with(scope) {
        val lw = art.lutA.width
        val lh = art.lutA.height
        val moving = effects.blackHole && effects.moving
        val gpu = shader.supported && layer != null
        val fps = if (gpu) DISK_FPS else DISK_FPS_CPU
        // Still: one frame, chosen so the bright side shows its filaments well.
        val shadeT = if (moving) floor(t * fps) / fps else 12f
        // Matter falls in on the live clock even while the disk itself holds still.
        val withEvents = effects.infall && effects.moving
        val eventT = if (withEvents) floor(t * fps) / fps else 0f
        if (withEvents) SpaceEvents.at(eventT, events) else events.fill(0f)
        val e = if (effects.audioReactive) energy else 0f
        val key = shadeT * 7.0001f + eventT * 3.0003f + (if (withEvents) 1e5f else 0f) + (if (gpu) 2e5f else 0f) + floor(e * 40f) * 1e6f
        val dst = Offset(centre.x + v.lx0 * unit, centre.y + v.ly0 * unit)
        val sx = (v.lx1 - v.lx0) * unit / lw
        val sy = (v.ly1 - v.ly0) * unit / lh
        if (gpu && layer != null) {
            if (layer.size.width != lw || layer.size.height != lh || key != lastKey) {
                val brush = shader.brush(art.lutA, art.lutB, art.disk, shadeT, e, tint, events)
                if (brush != null) layer.record(this, layoutDirection, IntSize(lw, lh)) { drawRect(brush) }
                lastKey = key
            }
            translate(dst.x, dst.y) { scale(sx, sy, pivot = Offset.Zero) { drawLayer(layer) } }
        } else {
            val r = raster ?: DiskRaster(art).also { raster = it }
            val img = still?.takeIf { key == lastKey } ?: r.render(shadeT, e, tint, events).also { still = it; lastKey = key }
            translate(dst.x, dst.y) {
                scale(sx, sy, pivot = Offset.Zero) { drawImage(img, filterQuality = FilterQuality.Low) }
            }
        }
    }

    companion object {
        /** The views, for callers outside this file. */
        val Home: HoleView get() = HOME_VIEW
        val Player: HoleView get() = PLAYER_VIEW
    }
}

/**
 * The disk shaded on the CPU, for phones without runtime shaders: the same lookups and the same
 * formulas as the AGSL shader (BlackHoleShader.android.kt), at the LUT's size.
 */
class DiskRaster(art: SpaceDiskArt) {
    private val w = art.lutA.width
    private val h = art.lutA.height
    private val a = IntArray(w * h).also { art.lutA.readPixels(it) }
    private val b = IntArray(w * h).also { art.lutB.readPixels(it) }
    private val dw = art.disk.width
    private val dh = art.disk.height
    private val tex = IntArray(dw * dh).also { art.disk.readPixels(it) }
    private val out = IntArray(w * h)
    private val image = ImageBitmap(w, h)

    /** The plasma at a fraction [u] of the way round and row [fy], filtered, wrapping round the orbit. */
    private fun sample(u0: Float, fy: Float): Float {
        val u = u0 - floor(u0)
        val fx = u * dw
        val x0 = fx.toInt() % dw
        val x1 = (x0 + 1) % dw
        val y0 = fy.toInt().coerceIn(0, dh - 1)
        val y1 = min(y0 + 1, dh - 1)
        val ax = fx - floor(fx)
        val ay = fy - y0
        fun texel(x: Int, y: Int) = ((tex[y * dw + x] shr 16) and 0xFF) / 255f
        return (texel(x0, y0) * (1 - ax) + texel(x1, y0) * ax) * (1 - ay) + (texel(x0, y1) * (1 - ax) + texel(x1, y1) * ax) * ay
    }

    fun render(t: Float, energy: Float, tint: Color, ev: FloatArray): ImageBitmap {
        for (i in 0 until w * h) {
            val pb = b[i]
            val cov = ((pb shr 8) and 0xFF) / 255f
            if (cov <= 0f) { out[i] = 0; continue }
            val pa = a[i]
            val phi = (((pa shr 16) and 0xFF) * 256 + ((pa shr 8) and 0xFF)) / 65535f * TAU
            val r = R_IN + ((pa and 0xFF) - 1) / 254f * (R_OUT - R_IN)
            val g = 0.2f + ((pb shr 16) and 0xFF) / 255f * 1.6f
            val far = if ((pb and 0xFF) > 127) 0.85f else 1f
            val omega = OMEGA_IN * (r / R_IN).pow(-1.5f)
            val fy = ((r - R_IN) / (R_OUT - R_IN)).coerceIn(0f, 1f) * (dh - 1)
            // Two layers of the plasma at different speeds and rows: the churn (as in the shader).
            val t1 = sample((phi - omega * t) / TAU, fy)
            val t2 = sample((phi - omega * 0.78f * t) / TAU + 0.37f, (fy + 23f) % dh)
            val tv = (0.375f + ((t1 * 0.55f + t2 * 0.45f) - 0.375f) * 1.3f) * 1.6f
            // No emission beyond what it covers here: a bitmap cannot hold colour above its alpha.
            val px = shadeDisk(r, phi, g, far, cov, tv, energy, tint, ev)
            val m = max(max((px shr 16) and 0xFF, (px shr 8) and 0xFF), max(px and 0xFF, (px ushr 24) and 0xFF))
            out[i] = (m shl 24) or (px and 0xFFFFFF)
        }
        writeSpacePixels(image, out)
        return image
    }
}

/** One disk texel, as ARGB (premultiplied colour, coverage-weighted alpha). Mirrors the AGSL. */
internal fun shadeDisk(r: Float, phi: Float, g: Float, far: Float, cov: Float, tex: Float, energy: Float, tint: Color, ev: FloatArray): Int {
    val temp = (r / R_IN).pow(-0.75f) * max(1f - 0.55f * sqrt(R_IN / r), 0f).pow(0.25f) / T_MAX
    val tobs = (temp * g * 1.05f).coerceIn(0f, 1.6f)
    var cr = rampR(tobs); var cg = rampG(tobs); var cb = rampB(tobs)
    if (tint.alpha > 0f) {
        val k = tint.alpha * 0.18f
        cr = cr * (1 - k) + cr * tint.red * 1.6f * k
        cg = cg * (1 - k) + cg * tint.green * 1.6f * k
        cb = cb * (1 - k) + cb * tint.blue * 1.6f * k
    }
    val edge = ((R_OUT - r) / 9f).coerceIn(0f, 1f).pow(2.2f) * ((r - R_IN) / 0.35f).coerceIn(0f, 1f)
    val g2 = g * g
    val inten = g2 * g2 * temp.pow(2.6f) * tex * edge * (2.6f + 0.35f * energy) * far
    val e = eventLight(r, phi, ev) * g2 * g
    val lr = filmic(cr * inten + e)
    val lg = filmic(cg * inten + e * 0.86f)
    val lb = filmic(cb * inten + e * 0.66f)
    val alpha = ((inten * 1.5f + e).coerceIn(0f, 1f)) * cov
    fun ch(v: Float) = (v.pow(1f / 2.2f) * cov * 255f).toInt().coerceIn(0, 255)
    return ((alpha * 255f).toInt().coerceIn(0, 255) shl 24) or (ch(lr) shl 16) or (ch(lg) shl 8) or ch(lb)
}

private fun filmic(x: Float): Float = ((x * (2.51f * x + 0.03f)) / (x * (2.43f * x + 0.59f) + 0.14f)).coerceIn(0f, 1f)

private val RampT = floatArrayOf(0f, 0.30f, 0.55f, 0.78f, 0.98f, 1.18f, 1.45f)
private val RampR = floatArrayOf(0.25f, 0.80f, 1.00f, 1.00f, 1.00f, 0.94f, 0.76f)
private val RampG = floatArrayOf(0.015f, 0.14f, 0.42f, 0.74f, 0.93f, 0.96f, 0.85f)
private val RampB = floatArrayOf(0f, 0.015f, 0.07f, 0.40f, 0.82f, 1.00f, 1.00f)
private fun ramp(t: Float, c: FloatArray): Float {
    if (t <= RampT[0]) return c[0]
    for (i in 1 until RampT.size) {
        if (t <= RampT[i]) {
            val f = (t - RampT[i - 1]) / (RampT[i] - RampT[i - 1])
            return c[i - 1] + (c[i] - c[i - 1]) * f
        }
    }
    return c.last()
}
private fun rampR(t: Float) = ramp(t, RampR)
private fun rampG(t: Float) = ramp(t, RampG)
private fun rampB(t: Float) = ramp(t, RampB)

/** The light the clumps and the tidal stream add at a disk point (r, phi). Mirrors the AGSL. */
internal fun eventLight(r: Float, phi: Float, ev: FloatArray): Float {
    var sum = 0f
    for (k in 0 until 5) {
        val amp = ev[k * 4 + 3]
        if (amp <= 0f) continue
        val dr = (r - ev[k * 4]) / 0.22f
        val ds = 2f * r * sin(0.5f * (phi - ev[k * 4 + 1])) / ev[k * 4 + 2]
        sum += exp(-(dr * dr) - ds * ds) * amp
    }
    val samp = ev[23]
    if (samp > 0f) {
        var a = (ev[20] - phi) / TAU
        a = (a - floor(a)) * TAU
        val len = ev[21]
        if (a < len) {
            val rs = ev[22] - 2.2f * (a / 3.6f)
            val wd = 0.40f + 0.40f * a
            val dr = (r - rs) / wd
            sum += exp(-dr * dr) * exp(-a / max(0.3f, len) * 2.2f) * samp
        }
    }
    return sum
}

/**
 * Matter falling in, as a function of time (nothing integrates between frames, nothing allocates):
 * five slots, each a small clump spiralling from r0 to the ISCO over 20-60 s, then a gap. Every few
 * minutes a star is torn apart: a faint stream of debris wrapping along the disk for 15 s. The first
 * stream comes 30 s after the clock starts, so it can be seen without waiting.
 */
object SpaceEvents {
    private val periods = floatArrayOf(41f, 53f, 37f, 61f, 47f)
    private const val STREAM_SLOT = 210f
    private const val STREAM_START = 30f
    private const val STREAM_LEN = 15f

    fun at(t: Float, out: FloatArray) {
        for (i in 0 until 5) {
            val p = periods[i]
            val life = p * 0.8f
            val local = t + i * 11.3f
            val k = floor(local / p).toInt()
            val s = local - k * p
            val base = i * 4
            if (s >= life) { out[base + 3] = 0f; continue }
            val u = s / life
            val r0 = 14f + 5f * hash(k * 7 + i)
            val phi0 = TAU * hash(k * 13 + i * 3 + 1)
            val size = 0.8f + 0.3f * hash(k * 5 + i * 11 + 2)
            val rc = r0 - (r0 - (R_IN + 0.15f)) * u.pow(1.7f)
            // phi(t) = phi0 + integral of Omega(r(s)) ds: a midpoint sum, 16 steps.
            var ph = phi0
            val steps = 16
            for (j in 0 until steps) {
                val um = (j + 0.5f) / steps * u
                val rm = r0 - (r0 - (R_IN + 0.15f)) * um.pow(1.7f)
                ph += OMEGA_IN * (rm / R_IN).pow(-1.5f) * (u * life / steps)
            }
            val env = (u / 0.12f).coerceIn(0f, 1f) * ((1f - u) / 0.25f).coerceIn(0f, 1f).pow(1.3f)
            val redden = sqrt(max(0f, 1f - 3f / rc)) / sqrt(1f - 3f / r0)
            out[base] = rc
            out[base + 1] = ph
            out[base + 2] = (0.35f + 2.6f * u.pow(1.5f)) * size
            out[base + 3] = env * 3.2f * redden * size
        }
        val slot = floor(t / STREAM_SLOT).toInt()
        val at = t - slot * STREAM_SLOT - STREAM_START
        // One slot in two has a disruption (the first always): every 3.5 to 7 minutes.
        if ((slot == 0 || hash(slot * 31 + 5) < 0.5f) && at in 0f..STREAM_LEN) {
            val u = at / STREAM_LEN
            val r0 = 15.5f
            val phi0 = TAU * hash(slot * 17 + 9)
            out[20] = phi0 + OMEGA_IN * (r0 / R_IN).pow(-1.5f) * at * 1.4f
            out[21] = 0.4f + 3.6f * u.pow(0.7f)
            out[22] = r0 - 0.9f * u
            out[23] = sin(PI.toFloat() * u).pow(1.6f) * 0.75f
        } else {
            out[23] = 0f
        }
    }

    private fun hash(n: Int): Float {
        var x = n * 374761393 + 668265263
        x = (x xor (x ushr 13)) * 1274126177
        return ((x xor (x ushr 16)) and 0xFFFFFF) / 16777216f
    }
}

// ---- Live layers ----------------------------------------------------------------------------------

/**
 * Stars over the plates: varied magnitude and colour temperature, most twinkling only faintly, a
 * few a little more. Kept off the hole's face on Home.
 */
private class Twinkle {
    private val x = FloatArray(N)
    private val y = FloatArray(N)
    private val r = FloatArray(N)
    private val ph = FloatArray(N)
    private val sp = FloatArray(N)
    private val depth = FloatArray(N)
    private val col = IntArray(N)

    init {
        val rnd = java.util.Random(4021)
        for (i in 0 until N) {
            x[i] = rnd.nextFloat()
            y[i] = rnd.nextFloat() * 1.3f
            val m = rnd.nextFloat().pow(2.6f)
            r[i] = 0.5f + 1.1f * m
            ph[i] = rnd.nextFloat() * TAU
            sp[i] = 0.5f + rnd.nextFloat() * 1.6f
            depth[i] = if (rnd.nextFloat() < 0.15f) 0.45f else 0.12f
            col[i] = rnd.nextInt(StarTemps.size)
        }
    }

    fun draw(scope: DrawScope, t: Float, moving: Boolean, home: Boolean, par: Float) = with(scope) {
        val w = size.width
        val hx = w * HOME_HOLE_X
        val hy = w * HOME_HOLE_Y - par
        val keep = w * HOME_UNIT * 11f
        for (i in 0 until N) {
            val p = Offset(x[i] * w, y[i] * w - par)
            if (home && abs(p.x - hx) < keep * 1.9f && abs(p.y - hy) < keep) continue
            val k = if (moving) 1f - depth[i] * (0.5f + 0.5f * sin(t * sp[i] + ph[i])) else 0.9f
            val c = StarTemps[col[i]]
            drawCircle(c.copy(alpha = 0.85f * k), r[i] * density, p)
            if (r[i] > 1.2f) drawCircle(c.copy(alpha = 0.10f * k), r[i] * density * 3.2f, p)
        }
    }

    companion object {
        const val N = 46
    }
}

/**
 * Stars drifting slowly across the sky, all the time, at three depths: the far ones small, faint and
 * slow, the near ones a little brighter and quicker (a few dp a second at most). [count] of a fixed
 * pool, from arrays; they wrap round the edges. On Home they pass behind the hole, never over its face.
 */
private class MovingStars {
    private val x = FloatArray(MAX_MOVING_STARS)
    private val y = FloatArray(MAX_MOVING_STARS)
    private val depth = FloatArray(MAX_MOVING_STARS)
    private val col = IntArray(MAX_MOVING_STARS)

    init {
        val rnd = java.util.Random(7757)
        for (i in 0 until MAX_MOVING_STARS) {
            x[i] = rnd.nextFloat()
            y[i] = rnd.nextFloat()
            depth[i] = rnd.nextFloat().pow(1.8f)
            col[i] = rnd.nextInt(StarTemps.size)
        }
    }

    /**
     * The same drift, seen through a point lens at [c] ([unit] px per M): each star at angle beta
     * from the hole has two images, theta = (beta +- sqrt(beta^2 + 4 thetaE^2)) / 2, the primary
     * outside the Einstein ring and a faint inverted one inside it; each is stretched along the
     * ring by theta / beta and brightened by its magnification. Images inside the shadow are not
     * drawn. The Einstein radius is the baked plate's, so the moving stars bend as its stars do.
     */
    fun drawLensed(scope: DrawScope, t: Float, count: Int, c: Offset, unit: Float) = with(scope) {
        val w = size.width
        val h = size.height
        val dirX = -0.94f
        val dirY = 0.34f
        val e2 = THETA_E * THETA_E
        for (i in 0 until min(count, MAX_MOVING_STARS)) {
            val d = depth[i]
            val speed = (2.5f + 13f * d) * density
            var px = (x[i] * w + dirX * speed * t) % w
            if (px < 0f) px += w
            var py = (y[i] * h + dirY * speed * t) % h
            if (py < 0f) py += h
            val sx = (px - c.x) / unit
            val sy = (py - c.y) / unit
            val beta = sqrt(sx * sx + sy * sy).coerceAtLeast(0.05f)
            // As the baked sky: exact near the hole, fading to no lensing by LENS_NEAR + LENS_FADE.
            var wf = ((beta - LENS_NEAR) / LENS_FADE).coerceIn(0f, 1f)
            wf = wf * wf * (3f - 2f * wf)
            val root = sqrt(beta * beta + 4f * e2)
            val tone = col[i]
            val baseR = (0.45f + 0.85f * d) * density
            val baseA = 0.22f + 0.55f * d
            for (k in 0..1) {
                val lensed = if (k == 0) (beta + root) / 2f else (beta - root) / 2f // negative: far side
                // The second image belongs to the lens alone: it fades out with the lensing.
                if (k == 1 && wf >= 1f) continue
                val theta = if (k == 0) lensed * (1f - wf) + beta * wf else lensed
                val at = abs(theta)
                if (at < SHADOW_M) continue
                val mu = abs(lensed * lensed * lensed * lensed / (lensed * lensed * lensed * lensed - e2 * e2))
                val gain = if (k == 0) sqrt(mu).coerceIn(0.6f, 1.6f) * (1f - wf) + wf else sqrt(mu).coerceIn(0f, 1f) * (1f - wf)
                val a = (baseA * gain).coerceAtMost(0.95f)
                if (a < 0.03f) continue
                val stretch = ((abs(lensed) / beta) * (1f - wf) + wf).coerceIn(1f, 4f)
                val ux = sx / beta * (if (theta < 0f) -1f else 1f)
                val uy = sy / beta * (if (theta < 0f) -1f else 1f)
                val rPx = at * unit
                val ix = c.x + ux * rPx
                val iy = c.y + uy * rPx
                if (stretch < 1.3f) {
                    softStar(tone, a, baseR, ix, iy)
                } else {
                    // A short arc along the circle round the hole, brightest in the middle, tapering:
                    // a star smeared by the lens, not a stroke.
                    // Dots close enough to overlap (0.6 r apart), so the arc reads as one smear.
                    val half = baseR * stretch / rPx // half the arc, in radians
                    val ang = kotlin.math.atan2(uy, ux)
                    val n = (stretch / 0.6f).toInt().coerceIn(2, 7)
                    for (j in -n..n) {
                        val f = j / n.toFloat()
                        val aj = ang + f * half
                        val fade = (1f - 0.7f * abs(f)) / sqrt(n.toFloat())
                        softStar(tone, a * fade, baseR * (1f - 0.35f * abs(f)), c.x + cos(aj) * rPx, c.y + sin(aj) * rPx, halo = j == 0)
                    }
                }
            }
        }
    }

    /** A star: a small bright core in a faint round halo — never a hard dot or a dash. [r] in px. */
    private fun DrawScope.softStar(tone: Int, a: Float, r: Float, x: Float, y: Float, halo: Boolean = true) {
        val c = StarTemps[tone]
        if (halo) drawCircle(c.copy(alpha = a * 0.12f), r * 1.8f, Offset(x, y))
        drawCircle(c.copy(alpha = a), r, Offset(x, y))
    }

    fun draw(scope: DrawScope, t: Float, count: Int, home: Boolean, par: Float) = with(scope) {
        val w = size.width
        val h = size.height
        val hx = w * HOME_HOLE_X
        val hy = w * HOME_HOLE_Y - par
        val keepX = w * HOME_UNIT * 20f
        val keepY = w * HOME_UNIT * 9f
        // A slow diagonal drift, down and to the left, as if the camera were turning gently.
        val dirX = -0.94f
        val dirY = 0.34f
        for (i in 0 until min(count, MAX_MOVING_STARS)) {
            val d = depth[i]
            val speed = (2.5f + 13f * d) * density
            var px = (x[i] * w + dirX * speed * t) % w
            if (px < 0f) px += w
            var py = (y[i] * h + dirY * speed * t - par * (0.2f + 0.6f * d)) % h
            if (py < 0f) py += h
            if (home && abs(px - hx) < keepX && abs(py - hy) < keepY) continue
            softStar(col[i], 0.22f + 0.55f * d, (0.45f + 0.85f * d) * density, px, py)
        }
    }
}

/**
 * Shooting stars: one per slot of the chosen rate ([MeteorRates]; at "normal", every 7 to 25 s), at
 * most one at a time, a thin bright head and a tapered tail crossing part of the upper sky in
 * 0.4-0.8 s at a random angle. On Home they keep above the hole.
 */
private class Meteors {
    companion object {
        /** Whether a meteor is on screen at [t] (the same schedule [draw] follows). */
        fun crossing(t: Float, rate: Int): Boolean {
            val slotLen = MeteorRates.SLOT_SECONDS[rate.coerceIn(0, MeteorRates.LEVELS - 1)]
            val slot = floor(t / slotLen).toInt()
            val start = slot * slotLen + slotLen * (0.06f + 0.56f * hash(slot * 3))
            val dur = 0.4f + 0.4f * hash(slot * 5 + 1)
            val u = (t - start) / dur
            return u in 0f..1.3f
        }

        private fun hash(n: Int): Float {
            var x = n * 1103515245 + 12345
            x = (x xor (x ushr 15)) * 2246822519.toInt()
            return ((x xor (x ushr 13)) and 0xFFFFFF) / 16777216f
        }
    }

    fun draw(scope: DrawScope, t: Float, home: Boolean, rate: Int) = with(scope) {
        val slotLen = MeteorRates.SLOT_SECONDS[rate.coerceIn(0, MeteorRates.LEVELS - 1)]
        val slot = floor(t / slotLen).toInt()
        val start = slot * slotLen + slotLen * (0.06f + 0.56f * hash(slot * 3))
        val dur = 0.4f + 0.4f * hash(slot * 5 + 1)
        val u = (t - start) / dur
        if (u < 0f || u > 1.3f) return@with
        val w = size.width
        val fromLeft = hash(slot * 7 + 2) < 0.5f
        val angle = (15f + 25f * hash(slot * 11 + 3)) * PI.toFloat() / 180f
        val len = w * (0.22f + 0.16f * hash(slot * 13 + 4))
        val yMax = if (home) 0.40f else 0.62f
        val sx = w * (0.08f + 0.84f * hash(slot * 17 + 5))
        val sy = w * (0.06f + (yMax - 0.06f) * hash(slot * 19 + 6))
        val dx = cos(angle) * (if (fromLeft) 1f else -1f)
        val dy = sin(angle)
        val head = Offset(sx + dx * len * min(u, 1f), sy + dy * len * min(u, 1f))
        val tail = len * 0.45f * min(1f, u * 2.2f)
        val fade = if (u <= 1f) 1f else 1f - (u - 1f) / 0.3f
        val end = Offset(head.x - dx * tail, head.y - dy * tail)
        val white = Color(0xFFEAF0FF)
        drawLine(
            Brush.linearGradient(listOf(white.copy(alpha = 0.85f * fade), white.copy(alpha = 0f)), head, end),
            head, end, strokeWidth = 1.4f * density, cap = StrokeCap.Round,
        )
        drawCircle(Brush.radialGradient(listOf(white.copy(alpha = 0.55f * fade), Color.Transparent), head, 5f * density), 5f * density, head)
        drawCircle(white.copy(alpha = fade), 1.3f * density, head)
    }

}

// ---- The Player -----------------------------------------------------------------------------------

/**
 * What the music is doing, for the Player's disk: the app writes [energy] (0..1, smoothed) from its
 * audio level and [tint] from the album art. Plain fields, read only in draw.
 */
object SpaceAudio {
    @Volatile var energy: Float = 0f
    @Volatile var tint: Color = Color.Transparent
}

/**
 * Where the Player's album card is on screen (root coordinates), written by the card as it is
 * placed and read by the backdrop in draw: the hole sits exactly behind the art, and follows it.
 */
val SpacePlayerArtFrame = mutableStateOf(androidx.compose.ui.geometry.Rect.Zero)

/** The Player's plate and LUT, for [drawPlayerHole]. */
@Immutable
class SpacePlayerArt(val plate: ImageBitmap, val disk: SpaceDiskArt)

@Composable
fun rememberSpacePlayerArt(): SpacePlayerArt {
    val plate = imageResource(Res.drawable.space_player)
    val disk = rememberDiskArt(Res.drawable.space_player_lut_a, Res.drawable.space_player_lut_b)
    return remember(plate, disk) { SpacePlayerArt(plate, disk) }
}

/**
 * The Player's scene: the void, then the hole centred behind the album art, [artSide] px across —
 * the art covers the shadow and the lensed band arcs over it, the ring under it. The disk takes
 * the album's colour faintly ([SpaceAudio.tint]) and, with [ThemeEffects.audioReactive], brightens
 * gently with the music.
 */
fun DrawScope.drawPlayerHole(
    art: SpacePlayerArt, renderer: DiskRenderer, centre: Offset, artSide: Float, effects: ThemeEffects,
    t: Float, layer: GraphicsLayer?, shader: BlackHoleShader,
) {
    drawRect(SPACE_FLOOR)
    val unit = artSide / PLAYER_ART_M
    drawImage(
        art.plate,
        dstOffset = IntOffset((centre.x + PLAYER_X0 * unit).toInt(), (centre.y + PLAYER_Y0 * unit).toInt()),
        dstSize = IntSize((PLAYER_W * unit).toInt(), (PLAYER_H * unit).toInt()),
        filterQuality = FilterQuality.Medium,
    )
    val tint = SpaceAudio.tint.let { if (it.alpha > 0f) it.copy(alpha = 1f) else it }
    renderer.draw(this, DiskRenderer.Player, centre, unit, effects, t, layer, shader, SpaceAudio.energy, tint)
}

// ---- Glass ----------------------------------------------------------------------------------------

/**
 * Space's touch on a glass bar: a crisp specular line along the top edge, brightest in the middle
 * and gone at the ends. The glass itself is the app's frosted backdrop, which samples the scene —
 * starlight and the disk's glow come through it ([ThemeEffects.glass], "Glass refraction").
 */
@Composable
fun Modifier.spaceBarGlow(shape: Shape): Modifier {
    if (LocalThemeTokens.current.id != ThemeId.SPACE) return this
    return this.then(spaceSpecular)
}

private val spaceSpecular: Modifier = Modifier.drawWithContent {
        drawContent()
        val y = 0.6f.dp.toPx()
        val inset = min(size.height * 0.5f, size.width * 0.2f)
        drawLine(
            Brush.horizontalGradient(
                0f to Color.Transparent,
                0.25f to Color.White.copy(alpha = 0.30f),
                0.5f to Color.White.copy(alpha = 0.42f),
                0.75f to Color.White.copy(alpha = 0.30f),
                1f to Color.Transparent,
                startX = inset,
                endX = size.width - inset,
            ),
            Offset(inset, y),
            Offset(size.width - inset, y),
            strokeWidth = 0.8f.dp.toPx(),
        )
    }

/** Space's empty-state mark, for callers outside this file (see [drawStarSpiral]). */
object SpaceSpiral {
    fun DrawScope.draw(t: Float, color: Color) = drawStarSpiral(t, color)
}

/** A small spiral of stars falling slowly into a point: Space's empty-state mark. [t] in seconds. */
fun DrawScope.drawStarSpiral(t: Float, color: Color) {
    val c = Offset(size.width / 2, size.height / 2)
    val rmax = min(size.width, size.height) / 2
    for (i in 0 until 14) {
        val p = ((t * 0.12f + i / 14f) % 1f)
        val r = rmax * (1f - p)
        val a = i * 2.39996f + p * 5f
        val pt = Offset(c.x + cos(a) * r, c.y + sin(a) * r)
        drawCircle(color.copy(alpha = (0.2f + 0.6f * p) * (1f - p * p)), max(1.0f, 2.2f * (1f - p)) * density, pt)
    }
    drawCircle(Color.Black, rmax * 0.16f, c)
    drawCircle(color.copy(alpha = 0.45f), rmax * 0.19f, c, style = androidx.compose.ui.graphics.drawscope.Stroke(1f * density))
}
