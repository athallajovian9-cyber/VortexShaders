#version 120
/* DRAWBUFFERS:0 */
#include "/lib/common.glsl"
varying vec4 vColor;
void main() {
    // Sky is emitted raw; the deferred pass lights it and applies fog.
    gl_FragData[0] = vec4(vColor.rgb, 1.0);
}
