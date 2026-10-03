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
