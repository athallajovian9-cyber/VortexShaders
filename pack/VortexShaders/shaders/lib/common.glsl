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
