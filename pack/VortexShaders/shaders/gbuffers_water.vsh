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
