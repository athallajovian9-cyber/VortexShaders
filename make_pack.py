#!/usr/bin/env python3
"""Generate the Vortex shader pack.

A shader pack is a folder of GLSL programs. Minecraft hands each render pass to a
program by filename (gbuffers_terrain, shadow, deferred, composite, final...), so
the file names ARE the API - a typo means Minecraft silently falls back to
vanilla for that pass and the feature just does not appear.

Emitted from templates because most passes differ only in which buffers they
write; hand-writing 40 near-identical files guarantees a typo somewhere.

    python make_pack.py
"""
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
PACK = HERE / "pack" / "VortexShaders"
SH = PACK / "shaders"

SHADER_FILES = {}

# ---------------------------------------------------------------- shared lib
SHADER_FILES["lib/common.glsl"] = """
// Shared uniforms and helpers. Included by every other program via
// #include "/lib/common.glsl".
#ifndef COMMON_GLSL
#define COMMON_GLSL

uniform mat4 gbufferModelView;
uniform mat4 gbufferModelViewInverse;
uniform mat4 gbufferProjection;
uniform mat4 gbufferProjectionInverse;
uniform mat4 shadowModelView;
uniform mat4 shadowProjection;
uniform vec3 cameraPosition;
uniform vec3 sunPosition;
uniform vec3 moonPosition;
uniform vec3 skyColor;      // Minecraft's own, per biome and dimension
uniform vec3 fogColor;      // ditto - using these keeps the Nether and the End correct
uniform int isEyeInWater;   // 0 dry, 1 water, 2 lava
uniform float frameTimeCounter;
uniform float rainStrength;
uniform int worldTime;

const float PI = 3.14159265359;

// World position of the pixel, rebuilt from the depth buffer.
vec3 worldPosFromDepth(vec2 texcoord, float depth) {
    vec4 clip = vec4(texcoord * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
    vec4 view = gbufferProjectionInverse * clip;
    view /= view.w;
    return (gbufferModelViewInverse * view).xyz + cameraPosition;
}

// Position in shadow-map clip space, for looking up the sun's depth.
vec3 toShadowClip(vec3 worldPos) {
    vec4 clip = shadowProjection * (shadowModelView * vec4(worldPos - cameraPosition, 1.0));
    return clip.xyz / clip.w * 0.5 + 0.5;
}

float luma(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }

// Shadow map texel size, as a constant rather than textureSize() - that builtin
// does not exist until GLSL 1.30 and silently kills the whole pass at 120.
// This assumes roughly a 2K shadow map (see shadowResolution in
// shaders.properties). A mismatch only changes the PCF blur radius, not
// whether the shadow is in the right place.
const float SHADOW_TEXEL = 1.0 / 2048.0;
#endif
"""

# ------------------------------------------------------- gbuffer programs
# Every gbuffer pass shares one vertex shader. They differ only in what the
# fragment stage writes, so the vertex is a constant.
GBUF_VSH = """
#version 120
#include "/lib/common.glsl"

varying vec4 vColor;
varying vec2 vTex;
varying vec2 vLight;
varying vec3 vNormal;

void main() {
    vColor  = gl_Color;
    vTex    = (gl_TextureMatrix[0] * gl_MultiTexCoord0).xy;
    vLight  = (gl_TextureMatrix[1] * gl_MultiTexCoord1).xy;
    vNormal = normalize(gl_NormalMatrix * gl_Normal);
    gl_Position = ftransform();
}
"""

# Writes albedo, view-space normal and the lightmap.
# The normal buffer's ALPHA is a material mask: 0.0 ordinary, 1.0 water. The
# deferred pass needs to know where water is, because water needs a specular
# highlight and everything else must not get one.
GBUF_FSH = """
#version 120
/* DRAWBUFFERS:012 */
#include "/lib/common.glsl"

uniform sampler2D texture;

varying vec4 vColor;
varying vec2 vTex;
varying vec2 vLight;
varying vec3 vNormal;

void main() {
    vec4 albedo = texture2D(texture, vTex) * vColor;
    if (albedo.a < 0.1) discard;

    gl_FragData[0] = vec4(albedo.rgb, 1.0);
    gl_FragData[1] = vec4(normalize(vNormal) * 0.5 + 0.5, 0.0);
    gl_FragData[2] = vec4(vLight, 0.0, 1.0);
}
"""

# ---------------------------------------------------------------- water
# Water gets its own program, not the terrain one.
#
# Two things make water read as water, and the terrain shader does neither: the
# alpha must survive (it is translucent - forcing 1.0 renders an opaque slab),
# and the surface needs movement. A flat normal looks like blue concrete.
WATER_VSH = """
#version 120
#include "/lib/common.glsl"

varying vec4 vColor;
varying vec2 vTex;
varying vec2 vLight;
varying vec3 vNormal;
varying vec3 vWorld;

// How far the surface rises and falls, in blocks. Small: the water in Minecraft
// is a one-block plane, so a large displacement tears it away from its edges.
const float WAVE_AMPLITUDE = 0.055;

void main() {
    vColor  = gl_Color;
    vTex    = (gl_TextureMatrix[0] * gl_MultiTexCoord0).xy;
    vLight  = (gl_TextureMatrix[1] * gl_MultiTexCoord1).xy;
    vNormal = normalize(gl_NormalMatrix * gl_Normal);

    // Absolute world position, so the swell travels through the world instead of
    // moving with the camera.
    vec3 world = (gbufferModelViewInverse * (gl_ModelViewMatrix * gl_Vertex)).xyz
        + cameraPosition;
    vWorld = world;

    // Three swells at different speeds and directions. The surface genuinely
    // moves up and down - this is real displacement, not a shading illusion.
    float t = frameTimeCounter;
    float h = sin(world.x * 0.55 + t * 1.30) * 0.50
            + sin(world.z * 0.62 - t * 1.05) * 0.50
            + sin((world.x + world.z) * 0.31 + t * 0.75) * 0.35;
    h *= WAVE_AMPLITUDE;

    gl_Position = ftransform();

    // Shift in view space by going through the projection's Y scale. Adding to
    // clip-space y directly (rather than to w) keeps the perspective divide
    // untouched, so the surface moves without changing its apparent distance.
    gl_Position.y += gbufferProjection[1][1] * h;
}
"""

WATER_FSH = """
#version 120
/* DRAWBUFFERS:012 */
#include "/lib/common.glsl"

uniform sampler2D texture;

varying vec4 vColor;
varying vec2 vTex;
varying vec2 vLight;
varying vec3 vNormal;
varying vec3 vWorld;

void main() {
    vec4 albedo = texture2D(texture, vTex) * vColor;
    // Discard only what is genuinely invisible. Minecraft's water texture is
    // partially transparent and must NOT be thrown away.
    if (albedo.a < 0.02) discard;

    // The same three swells the vertex shader displaces, so the shading rolls
    // with the surface instead of sliding across a flat plane.
    float t = frameTimeCounter;
    vec2 p = vWorld.xz;
    float w1 = sin(p.x * 0.55 + t * 1.30) * 0.50;
    float w2 = sin(p.y * 0.62 - t * 1.05) * 0.50;
    float w3 = sin((p.x + p.y) * 0.31 + t * 0.75) * 0.35;

    vec3 n = normalize(vNormal + vec3(w1 * 0.05 + w3 * 0.03, 0.0,
                                      w2 * 0.05 + w3 * 0.03));

    // Deep blue, not cyan.
    //
    // Water absorbs the red end of the spectrum first, so what survives with
    // depth is blue. The previous version barely tinted at all, which is why the
    // surface came out pale cyan - it was mostly reflected sky and ambient light.
    vec3 deepBlue = vec3(0.012, 0.065, 0.22);

    // Grazing angles look through more water than angles looking straight down,
    // so they should read darker and bluer. This is the cheap stand-in for a
    // depth-based absorption term, which a gbuffer pass has no way to measure.
    vec3 viewDir = normalize(vWorld - cameraPosition);
    float pathLen = clamp(1.0 - abs(dot(viewDir, n)), 0.0, 1.0);
    vec3 waterCol = mix(albedo.rgb, deepBlue, mix(0.55, 0.95, pathLen));

    // A touch more opaque than vanilla, so the blue reads as depth rather than
    // as a thin sheet with the sky showing through it.
    float alpha = clamp(albedo.a + 0.18, 0.0, 0.88);

    gl_FragData[0] = vec4(waterCol, alpha);        // translucent, never opaque
    gl_FragData[1] = vec4(n * 0.5 + 0.5, 1.0);     // alpha 1.0 marks this pixel as water
    gl_FragData[2] = vec4(vLight, 0.0, 1.0);
}
"""

# Same, but the lightmap is not applied - for things that light themselves.
GBUF_UNLIT_FSH = """
#version 120
/* DRAWBUFFERS:012 */
#include "/lib/common.glsl"

uniform sampler2D texture;

varying vec4 vColor;
varying vec2 vTex;
varying vec2 vLight;
varying vec3 vNormal;

void main() {
    vec4 albedo = texture2D(texture, vTex) * vColor;
    if (albedo.a < 0.1) discard;

    gl_FragData[0] = vec4(albedo.rgb, 1.0);
    gl_FragData[1] = vec4(normalize(vNormal) * 0.5 + 0.5, 0.0);
    gl_FragData[2] = vec4(1.0, 1.0, 0.0, 1.0);
}
"""

# ------------------------------------------------------------ sky programs
SKY_VSH = """
#version 120
varying vec4 vColor;
void main() {
    vColor = gl_Color;
    gl_Position = ftransform();
}
"""

SKY_FSH = """
#version 120
/* DRAWBUFFERS:0 */
#include "/lib/common.glsl"
varying vec4 vColor;
void main() {
    // Sky is emitted raw; the deferred pass lights it and applies fog.
    gl_FragData[0] = vec4(vColor.rgb, 1.0);
}
"""

# ----------------------------------------------------------- shadow pass
# Shadow programs write nothing but depth. The vertex stage is the whole job -
# it must use the same transform Minecraft expects so the shadow map lines up.
SHADOW_VSH = """
#version 120
#include "/lib/common.glsl"
void main() {
    gl_Position = ftransform();
}
"""

SHADOW_FSH = """
#version 120
void main() {
    gl_FragColor = vec4(1.0);
}
"""

# ------------------------------------------------------- deferred lighting
FULLSCREEN_VSH = """
#version 120
varying vec2 texcoord;
void main() {
    texcoord = gl_MultiTexCoord0.xy;
    gl_Position = ftransform();
}
"""

DEFERRED_FSH = """
#version 120
/* DRAWBUFFERS:0 */
#include "/lib/common.glsl"

uniform sampler2D colortex0;   // albedo
uniform sampler2D colortex1;   // normal
uniform sampler2D colortex2;   // lightmap
uniform sampler2D depthtex0;
uniform sampler2D shadow;

varying vec2 texcoord;

// How much of the sun reaches this pixel.
float sunVisibility(vec3 worldPos, vec3 normal) {
    if (worldPos.y < 0.0) return 0.0;

    vec3 shadowClip = toShadowClip(worldPos);
    // Outside the sun's frustum: assume lit rather than punch a black hole.
    if (any(lessThan(shadowClip.xy, vec2(0.0))) || any(greaterThan(shadowClip.xy, vec2(1.0))))
        return 1.0;
    if (shadowClip.z > 1.0) return 1.0;

    // Small offset along the normal kills the shadow acne you get when the
    // surface shadows itself.
    vec3 offsetPos = worldPos + normal * 0.05;
    vec3 occluderClip = toShadowClip(offsetPos);
    if (any(lessThan(occluderClip.xy, vec2(0.0))) || any(greaterThan(occluderClip.xy, vec2(1.0))))
        return 1.0;

    float occluderDepth = texture2D(shadow, occluderClip.xy).r;

    // 3x3 PCF: a single tap looks like a staircase at this resolution.
    float lit = 0.0;
    vec2 texel = vec2(SHADOW_TEXEL);
    for (int x = -1; x <= 1; x++) {
        for (int y = -1; y <= 1; y++) {
            float d = texture2D(shadow, occluderClip.xy + vec2(x, y) * texel).r;
            lit += (occluderClip.z - 0.00035 <= d) ? 1.0 : 0.0;
        }
    }
    return lit / 9.0;
}

void main() {
    vec4 albedo = texture2D(colortex0, texcoord);
    vec3 normal = normalize(texture2D(colortex1, texcoord).xyz * 2.0 - 1.0);
    vec2 light  = texture2D(colortex2, texcoord).xy;

    float depth = texture2D(depthtex0, texcoord).r;
    vec3 worldPos = worldPosFromDepth(texcoord, depth);
    vec3 viewDir = normalize(worldPos - cameraPosition);

    // TEXTURES ARE sRGB; LIGHTING MUST BE LINEAR.
    // Skipping this decode is what makes a naive pack look washed out and too
    // bright: light gets multiplied into gamma-encoded colour, and the gamma in
    // final.fsh then brightens it a SECOND time.
    vec3 albedoLin = pow(albedo.rgb, vec3(2.2));

    // Sun direction, kept in step with the shadow pass.
    vec3 sunDir = normalize(sunPosition);
    float sunDot = max(dot(normal, sunDir), 0.0);

    float shadowFactor = sunVisibility(worldPos, normal);
    float sun = sunDot * shadowFactor;

    // In linear space 1.0 means fully lit. These are deliberately modest - the
    // first version summed to nearly 4x and clipped the whole frame to white.
    vec3 sunColor   = vec3(1.00, 0.94, 0.82) * sun * 1.35;
    vec3 skyAmbient = vec3(0.52, 0.62, 0.82) * light.y * 0.22;
    vec3 blocklight = vec3(1.00, 0.62, 0.30) * light.x * 0.85;

    vec3 color = albedoLin * (sunColor + skyAmbient + blocklight);

    // Water sparkle. The mask rides in the normal buffer's alpha, so only water
    // catches the highlight - otherwise every surface would look wet.
    float isWater = texture2D(colortex1, texcoord).a;
    if (isWater > 0.5) {
        vec3 viewToCam = normalize(cameraPosition - worldPos);
        vec3 halfway   = normalize(sunDir + viewToCam);
        float spec = pow(max(dot(normal, halfway), 0.0), 180.0) * shadowFactor;
        color += vec3(1.00, 0.95, 0.85) * spec * 0.95;
    }

    // Minecraft supplies sky and fog colour per biome and dimension. Using those
    // keeps the Nether and the End correct for free - hand-picked constants
    // would paint an overworld blue sky over lava.
    vec3 skyLin = pow(skyColor, vec3(2.2));
    vec3 fogLin = pow(fogColor, vec3(2.2));

    if (depth >= 1.0) {
        // Darken towards the zenith so the sky has depth instead of a flat fill.
        float horizonMix = clamp(viewDir.y * 1.6, 0.0, 1.0);
        gl_FragData[0] = vec4(skyLin * mix(1.0, 0.45, horizonMix), 1.0);
        return;
    }

    // Real distance from the reconstructed position. linearizeDepth() hardcodes
    // the projection's near and far planes, so its idea of distance is wrong at
    // any render distance other than the one it assumed.
    float dist = length(worldPos - cameraPosition);
    float fogAmount = clamp(1.0 - exp(-pow(dist * 0.0075, 1.8)), 0.0, 1.0);
    // Warm the fog towards the sun, so haze reads as scattered sunlight.
    vec3 fogTint = mix(fogLin, fogLin + vec3(0.35, 0.22, 0.05),
                       pow(clamp(sunDot, 0.0, 1.0), 4.0));
    color = mix(color, fogTint, fogAmount);

    gl_FragData[0] = vec4(color, 1.0);
}
"""

# ------------------------------------------------------------------ final
FINAL_FSH = """
#version 120
#include "/lib/common.glsl"

uniform sampler2D colortex0;
varying vec2 texcoord;

void main() {
    vec3 color = texture2D(colortex0, texcoord).rgb;

    // Submerged: water absorbs the red end of the spectrum first. Applied in
    // linear space before the tonemap, so it behaves like absorption rather than
    // a colour filter laid over the finished image.
    if (isEyeInWater > 0) {
        color *= vec3(0.35, 0.58, 0.90);
    }

    // Reinhard tonemap, then gamma. Without this the highlights clip to white.
    color = color / (color + vec3(1.0));
    color = pow(color, vec3(1.0 / 2.2));

    // A little contrast, following the tonemap so it does not clip again.
    color = mix(vec3(0.5), color, 1.10);

    gl_FragColor = vec4(clamp(color, 0.0, 1.0), 1.0);
}
"""


def main():
    SH.mkdir(parents=True, exist_ok=True)
    (SH / "lib").mkdir(parents=True, exist_ok=True)

    files = dict(SHADER_FILES)

    # Load-time settings. Deliberately minimal: only keys whose names are well
    # established, because a misspelt key is ignored silently - worse than not
    # setting it at all.
    files["shaders.properties"] = """
# Vortex Shaders - settings Iris reads when it loads the pack.
#
# shadowResolution scales the sun's shadow map (1.0 = the default). The shaders
# assume roughly a 2K map when they blur shadow edges, so changing this changes
# how soft shadows look, not whether they are in the right place.
shadowResolution=1.0
"""

    # Every program Minecraft may request. Missing ones make it fall back to
    # vanilla for that pass, so the full set is emitted rather than a subset.
    gbuf = ["basic", "textured", "textured_lit", "terrain", "water", "skybasic",
            "skytextured", "clouds", "entities", "hand", "weather", "block",
            "damagedblock", "beaconbeam", "armor_glint", "spider", "spidereyes"]
    for name in gbuf:
        files["gbuffers_%s.vsh" % name] = GBUF_VSH
        if name == "water":
            # Water is translucency plus movement - see WATER_FSH.
            files["gbuffers_%s.vsh" % name] = WATER_VSH
            files["gbuffers_%s.fsh" % name] = WATER_FSH
        elif name in ("skybasic", "spidereyes"):
            files["gbuffers_%s.fsh" % name] = SKY_FSH
        elif name in ("skytextured", "beaconbeam", "armor_glint"):
            files["gbuffers_%s.fsh" % name] = GBUF_UNLIT_FSH
        else:
            files["gbuffers_%s.fsh" % name] = GBUF_FSH

    for name in ("shadow", "shadow_solid", "shadow_cutout", "shadow_translucent"):
        files["%s.vsh" % name] = SHADOW_VSH
        files["%s.fsh" % name] = SHADOW_FSH

    for name in ("deferred", "composite", "composite1", "composite2",
                 "composite3", "composite4", "composite5"):
        files["%s.vsh" % name] = FULLSCREEN_VSH
        files["%s.fsh" % name] = DEFERRED_FSH if name == "deferred" else """
#version 120
/* DRAWBUFFERS:0 */
uniform sampler2D colortex0;
varying vec2 texcoord;
void main() { gl_FragData[0] = texture2D(colortex0, texcoord); }
"""

    files["final.vsh"] = FULLSCREEN_VSH
    files["final.fsh"] = FINAL_FSH

    for rel, body in files.items():
        p = SH / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body.lstrip("\n"), encoding="utf-8")

    print("  wrote %d shader files" % len(files))


if __name__ == "__main__":
    main()
