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
