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
