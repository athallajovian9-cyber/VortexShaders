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
