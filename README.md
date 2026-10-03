# Vortex Shaders

A Minecraft shader pack for Java Edition 26.3, built to be **verifiable without
launching the game**.

## Why this exists

A broken shader is invisible. Minecraft fails the program, silently falls back to
vanilla for that pass, and the user sees *"it looks the same"* with no error on
screen. That is the whole difficulty of this project, and it is why nothing here
is written by hand without a compiler checking it.

## The commands

```bash
python make_pack.py      # regenerate the pack from templates -> pack/VortexShaders/
python verify_pack.py    # compile-check every program; non-zero exit means broken
```

Always run both. `make_pack.py` is the source of truth: 60 files are emitted from
templates so the near-identical passes cannot drift apart.

## What the pack does

| Pass | Effect |
|---|---|
| `gbuffers_*` | Writes albedo, view-space normal and lightmap into `colortex0/1/2` |
| `shadow*` | Renders the sun's depth map for shadow lookup |
| `deferred` | The lighting: sun with 3x3 PCF shadows, warm sun / cool ambient, block light, distance fog matched to the sky colour |
| `composite*` | Pass-through (room for bloom and effects) |
| `final` | Reinhard tonemap + gamma + mild contrast |

## Verify, don't trust

`verify_pack.py` checks four things:

1. **every `.vsh`/`.fsh` compiles** with real `glslang`, after resolving Iris
   `#include` paths — this is the closest thing to a test suite a shader pack can have
2. **the pipeline Iris needs is present** (`deferred`, `shadow*`, `final`, the
   `gbuffers_*` set)
3. **`DRAWBUFFERS`/`RENDERTARGETS` agree with what the program actually writes**
4. **no GLSL builtin is used before the version that introduced it**

### What it has already caught

`textureSize()` in `deferred.fsh` at `#version 120`. That builtin arrived in GLSL
1.30. On a real driver the program fails to compile, Iris drops the pass, and the
world renders vanilla — **the exact silent-failure mode this script exists to
prevent.** It is now a constant (`SHADOW_TEXEL`) instead.

### What it cannot check

Whether it *looks* right, and what it costs on a specific GPU. Those need the
game. On a GTX 1650 at 1080p, shadow resolution and the fog distance are the two
settings to lower first if frames drop.

## The limit of my confidence, stated plainly

This was written without ever launching Minecraft, so the parts that are proven
are: it compiles, the pipeline is complete, the buffer contracts are consistent,
and the API versions are legal. The parts that are **not** proven:

- whether the uniform names (`sunPosition`, `shadow`, `colortex*`, `depthtex0`)
  are all bound by Iris on this version
- whether the lighting values look good — they are reasoned, not measured
- the frame cost

If it loads and does nothing, `logs/latest.log` will name the failing program.
If it loads but shadows are entirely black or entirely absent, the first suspect
is the `shadow` sampler binding; `shadowtex0` is the modern name.