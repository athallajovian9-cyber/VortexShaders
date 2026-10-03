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
