#!/usr/bin/env python3
"""Compile-check a Minecraft shader pack without running Minecraft.

Why this exists: a broken shader is invisible. Minecraft fails the program,
silently falls back to vanilla for that pass, and you see "it looks the same" -
which is exactly what happened before this script was written. The only cheap
way to catch it is to compile every program the way the driver would.

What it checks
  1. every .vsh/.fsh compiles (glslang), with Iris #include resolved first
  2. the pipeline files Iris requires are present
  3. DRAWBUFFERS / RENDERTARGETS declarations agree with what the program writes
  4. no GLSL builtin is used at a #version that predates it

    python verify_pack.py
"""
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
PACK = HERE / "pack" / "VortexShaders"
SH = PACK / "shaders"
GLSLANG = HERE / "tools" / "bin" / "glslang.exe"

# Passes Iris will not run the pack without. A missing one is not an error in
# itself, but these specific names are what every pack in the wild defines.
REQUIRED = [
    "gbuffers_basic", "gbuffers_textured", "gbuffers_textured_lit", "gbuffers_terrain",
    "gbuffers_water", "gbuffers_skybasic", "gbuffers_skytextured", "gbuffers_entities",
    "gbuffers_hand", "gbuffers_weather", "shadow", "shadow_solid", "shadow_cutout",
    "deferred", "composite", "final",
]

# GLSL builtins that only exist from a given version onwards. Using one in an
# older #version is the classic silent failure: the driver rejects the program.
VERSION_GATED = {
    "textureSize": 130, "texelFetch": 130, "textureLod": 130,
    "inverse": 140, "round": 130, "trunc": 130, "sinh": 130,
    "packHalf2x16": 420, "bitfieldExtract": 400,
    "gl_FragDepth": 110,
}


def read(p):
    return p.read_text(encoding="utf-8", errors="replace")


def resolve_includes(src, depth=0):
    """Inline Iris #include "/path" so a standalone compiler can see it."""
    if depth > 8:
        return src
    pattern = re.compile(r'^\s*#include\s+"([^"]+)"', re.M)

    def sub(m):
        rel = m.group(1).lstrip("/")
        target = SH / rel
        if not target.exists():
            raise FileNotFoundError("include not found: " + rel)
        return resolve_includes(read(target), depth + 1)

    return pattern.sub(sub, src)


def declared_buffers(src):
    """What the program says it writes: DRAWBUFFERS:012 or RENDERTARGETS."""
    m = re.search(r'/\*\s*(DRAWBUFFERS|RENDERTARGETS)\s*:\s*([0-9]+)\s*\*/', src)
    if not m:
        return None
    return sorted(set(int(c) for c in m.group(2)))


def written_buffers(src):
    """What it actually writes: gl_FragData[n] or layout(location=n) out."""
    out = set(int(i) for i in re.findall(r'gl_FragData\[(\d+)\]', src))
    out |= set(int(i) for i in re.findall(r'layout\s*\(\s*location\s*=\s*(\d+)', src))
    if re.search(r'\bgl_FragColor\b', src):
        out.add(0)
    return sorted(out)


def version_of(src):
    m = re.search(r'#version\s+(\d+)', src)
    return int(m.group(1)) if m else None


def strip_comments(src):
    """Remove // and /* */ comments.

    A version check that scans comments reports the very explanatory comment
    that documents the restriction. Strip first, then look for real usages.
    """
    src = re.sub(r'/\*.*?\*/', ' ', src, flags=re.S)
    src = re.sub(r'//[^\n]*', ' ', src)
    return src


def compile_one(path, stage):
    src = read(path)
    try:
        expanded = resolve_includes(src)
    except FileNotFoundError as e:
        return False, str(e)
    tmp = HERE / "_tmp_check.glsl"
    tmp.write_text(expanded, encoding="utf-8")
    try:
        r = subprocess.run([str(GLSLANG), "-S", stage, str(tmp)],
                           capture_output=True, text=True, timeout=90)
    except Exception as e:
        return False, "glslang failed to run: %s" % e
    finally:
        tmp.unlink(missing_ok=True)
    ok = r.returncode == 0
    msg = (r.stdout or "") + (r.stderr or "")
    return ok, msg.strip()


def check_exposure():
    """Model the lighting pipeline numerically and refuse a blown-out pack.

    This exists because the first version of this pack summed to nearly 4x light
    and applied gamma twice, and the only symptom was "it makes it bright" - a
    bug no compiler can see. The constants are read back out of the shader so the
    test tracks the code instead of a copy of it that drifts.
    """
    src = read(SH / "deferred.fsh")
    fin = read(SH / "final.fsh")

    sun = re.search(r'\*\s*sun\s*\*\s*([0-9.]+)\s*;', src)
    amb = re.search(r'vec3\(([0-9.]+),\s*([0-9.]+),\s*([0-9.]+)\)\s*\*\s*light\.y\s*\*\s*([0-9.]+)', src)
    if not (sun and amb):
        return [("exposure", "could not read the light constants out of deferred.fsh")]

    sunK = float(sun.group(1))
    ambGreen = float(amb.group(2)) * float(amb.group(4))

    # The lighting must happen in linear space, or the gamma in final double-counts.
    problems = []
    if "pow(albedo" not in src:
        problems.append(("exposure", "deferred.fsh lights albedo without decoding it "
                                     "from sRGB first - this double-applies gamma"))
    if "pow(" not in fin:
        problems.append(("exposure", "final.fsh has no gamma encode"))

    def out(a, L):
        c = (a ** 2.2) * L
        t = c / (c + 1.0)                          # Reinhard
        return t ** (1.0 / 2.2)                    # gamma encode

    L_lit, L_shadow = sunK + ambGreen, ambGreen
    results = []
    for a in (0.20, 0.35, 0.50, 0.70, 0.90, 1.00):
        results.append((a, out(a, L_lit), out(a, L_shadow)))

    if any(lit >= 0.97 for _a, lit, _s in results):
        problems.append(("exposure", "a fully lit surface clips to white (%.3f)"
                         % max(lit for _a, lit, _s in results)))
    a50 = [r for r in results if r[0] == 0.50][0]
    if a50[1] / max(a50[2], 1e-6) < 1.7:
        problems.append(("exposure", "sunlit and shadowed faces are too close "
                                     "(%.2f vs %.2f) - the shadows will not read"
                         % (a50[1], a50[2])))
    if a50[2] < 0.06:
        problems.append(("exposure", "shade is crushed to black (%.3f)" % a50[2]))

    print("")
    print("  ---- exposure model (no GPU needed) ----")
    print("  sun factor %.2f, ambient green %.3f" % (sunK, ambGreen))
    print("  albedo   sunlit   shadowed")
    for a, lit, sh in results:
        print("   %.2f     %.3f    %.3f" % (a, lit, sh))
    for name, msg in problems:
        print("  FAIL  %s" % msg)
    if not problems:
        print("  PASS  nothing clips, shadows read, shade is not crushed")
    return problems


def check_varyings():
    """Every varying a fragment shader reads must be written by its vertex shader.

    A name that exists in the .fsh but not the .vsh is undefined data - the
    compiler will not complain, the value is just garbage.
    """
    problems = []
    print("")
    print("  ---- varyings match their vertex shader ----")
    for fsh in sorted(SH.glob("*.fsh")):
        vsh = fsh.with_suffix(".vsh")
        if not vsh.exists() or fsh.stem == "final":
            continue
        want = set(re.findall(r'^\s*varying\s+\w+\s+(\w+)\s*;', read(fsh), re.M))
        have = set(re.findall(r'^\s*varying\s+\w+\s+(\w+)\s*;', read(vsh), re.M))
        missing = want - have
        if missing:
            problems.append(("varyings", "%s reads %s, which %s never writes"
                             % (fsh.name, sorted(missing), vsh.name)))
    if problems:
        for _n, m in problems:
            print("  FAIL  %s" % m)
    else:
        print("  PASS  no fragment shader reads an unwritten varying")
    return problems


def check_sky_and_fog():
    """Sky and fog must follow the dimension, and fog distance must be real.

    Hand-picked sky constants paint an overworld blue over the Nether, and
    linearizeDepth() hardcodes the projection's near/far planes so its idea of
    distance is wrong wherever those differ.
    """
    problems = []
    # Strip comments first: the comment explaining why linearizeDepth() is gone
    # would otherwise trip the check that looks for its absence.
    src = strip_comments(read(SH / "deferred.fsh"))

    if "skyColor" not in src:
        problems.append(("sky", "deferred.fsh ignores Minecraft's skyColor, so the "
                                "Nether and the End will render as overworld sky"))
    if "fogColor" not in src:
        problems.append(("sky", "deferred.fsh ignores Minecraft's fogColor"))
    if re.search(r'linearizeDepth\s*\(', src):
        problems.append(("sky", "deferred.fsh measures fog with linearizeDepth(), "
                                "which hardcodes near/far - use the real distance"))
    if not re.search(r'length\s*\(\s*worldPos\s*-\s*cameraPosition\s*\)', src):
        problems.append(("sky", "deferred.fsh does not compute true fog distance"))

    print("")
    print("  ---- sky and fog follow the dimension ----")
    if problems:
        for _n, m in problems:
            print("  FAIL  %s" % m)
    else:
        print("  PASS  dimension-aware sky and fog, real distance")
    return problems


def check_water():
    """Water must stay translucent and must not be the terrain shader.

    The first version of this pack pointed gbuffers_water at the terrain
    program, which forces albedo alpha to 1.0 - so translucent water rendered as
    an opaque slab. Nothing about that is a compile error, so it needs its own
    check.
    """
    problems = []
    wf = SH / "gbuffers_water.fsh"
    wv = SH / "gbuffers_water.vsh"
    if not wf.exists() or not wv.exists():
        return [("water", "gbuffers_water is missing")]

    fsh, vsh = read(wf), read(wv)

    if re.search(r'vec4\(\s*albedo\.rgb\s*,\s*1\.0\s*\)', fsh):
        problems.append(("water", "gbuffers_water forces alpha to 1.0 - water will "
                                  "render opaque"))
    if "albedo.a" not in fsh:
        problems.append(("water", "gbuffers_water discards albedo's alpha"))

    # The surface must genuinely move up and down, not just be shaded as if it did.
    if "gl_Position.y +=" not in vsh:
        problems.append(("water", "gbuffers_water.vsh does not displace the surface "
                                  "vertically - the water will look flat"))
    if "gbufferProjection[1][1]" not in vsh:
        problems.append(("water", "vertical displacement must go through the "
                                  "projection's Y scale"))

    if "frameTimeCounter" not in fsh:
        problems.append(("water", "gbuffers_water has no animated ripple"))

    # Deep blue, not pale cyan. The tint must be strongly blue-dominant.
    m = re.search(r'vec3\s+deepBlue\s*=\s*vec3\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)', fsh)
    if not m:
        problems.append(("water", "gbuffers_water has no deep-blue tint constant"))
    else:
        r, g, b = (float(x) for x in m.groups())
        if not (b > g > r):
            problems.append(("water", "the water tint is not blue-dominant"))
        if r > 0.20:
            problems.append(("water", "the water tint has too much red for deep blue"))
        if b < 0.15:
            problems.append(("water", "the water tint is too weak to read as deep blue"))
        if b > 0.55:
            # Ordering alone does not separate deep blue from pale cyan - cyan is
            # also blue-dominant. Deep water is DARK.
            problems.append(("water", "the water tint is too bright (b=%.2f) - that "
                                      "reads as pale cyan, not deep blue" % b))

    # White foam was the "white thingy moving" - it must not come back.
    if "0.92, 0.96, 1.0" in fsh or "crest" in fsh:
        problems.append(("water", "gbuffers_water has white crest foam again - the "
                                  "surface should move, not show white streaks"))

    if "vWorld" not in vsh:
        problems.append(("water", "gbuffers_water.vsh does not pass world position, "
                                  "so ripples cannot move in world space"))

    # The terrain shader must NOT mask itself as water, or every block sparkles.
    if "vec4(normalize(vNormal) * 0.5 + 0.5, 1.0)" in read(SH / "gbuffers_terrain.fsh"):
        problems.append(("water", "gbuffers_terrain marks its normals as water - "
                                  "the specular would apply everywhere"))

    # The mask is only useful if the deferred pass reads it.
    if "colortex1, texcoord).a" not in read(SH / "deferred.fsh"):
        problems.append(("water", "deferred.fsh never reads the water mask"))

    print("")
    print("  ---- water is translucent and moving ----")
    if problems:
        for _n, m in problems:
            print("  FAIL  %s" % m)
    else:
        print("  PASS  alpha preserved, ripples animated, mask only on water")
    return problems


def main():
    fails = []
    checks = 0

    if not GLSLANG.exists():
        print("  glslang not found at", GLSLANG)
        return 1

    # --- 1. required pipeline files
    print("")
    print("  ---- the pipeline Iris needs ----")
    extra = list(SH.glob("*.vsh")) + list(SH.glob("*.fsh"))
    have = set(p.stem for p in extra)
    for name in REQUIRED:
        ok = name in have
        checks += 1
        print("  %s  %s" % ("PASS" if ok else "FAIL", name))
        if not ok:
            fails.append("missing pass: " + name)

    # --- 2. every program compiles
    print("")
    print("  ---- every program compiles ----")
    progs = sorted(list(SH.glob("*.vsh")) + list(SH.glob("*.fsh")))
    for p in progs:
        stage = "vert" if p.suffix == ".vsh" else "frag"
        ok, msg = compile_one(p, stage)
        checks += 1
        if ok:
            print("  PASS  %s" % p.name)
        else:
            print("  FAIL  %s" % p.name)
            for line in msg.splitlines()[:6]:
                print("          " + line)
            fails.append("%s does not compile" % p.name)

    # --- 3. buffer declarations agree with what is written
    print("")
    print("  ---- buffer declarations match what is written ----")
    for p in progs:
        if p.suffix != ".fsh":
            continue
        src = read(p)
        decl = declared_buffers(src)
        wrote = written_buffers(src)
        name = p.stem
        # Shadow programs write depth only, and `final` blits to the screen -
        # neither takes a DRAWBUFFERS directive.
        if name.startswith("shadow") or name == "final":
            continue
        checks += 1
        if decl is None and wrote:
            # Previously skipped entirely, which is how an undeclared write sat
            # in gbuffers_skybasic unnoticed. Writing a buffer without saying
            # which one is undefined behaviour.
            print("  FAIL  %-28s writes %s but declares no DRAWBUFFERS" % (p.name, wrote))
            fails.append("%s writes a buffer without declaring DRAWBUFFERS" % p.name)
            continue
        if decl is None:
            continue
        ok = set(wrote).issubset(set(decl))
        print("  %s  %-28s declares %s, writes %s"
              % ("PASS" if ok else "FAIL", p.name, decl, wrote))
        if not ok:
            fails.append("%s writes an undeclared buffer" % p.name)

    # --- 4. no builtin used before its version
    print("")
    print("  ---- no builtin used before its GLSL version ----")
    for p in progs:
        src = strip_comments(resolve_includes(read(p)))
        ver = version_of(src)
        if ver is None:
            continue
        for builtin, minver in VERSION_GATED.items():
            if re.search(r'\b%s\s*\(' % re.escape(builtin), src) and ver < minver:
                checks += 1
                print("  FAIL  %s uses %s at #version %d (needs %d)"
                      % (p.name, builtin, ver, minver))
                fails.append("%s: %s needs #version %d" % (p.name, builtin, minver))
    checks += 1
    print("  PASS  version check completed")

    # --- 5. the image is not blown out (the "it makes it bright" bug)
    exp_problems = check_exposure()
    checks += 1
    for _name, msg in exp_problems:
        fails.append(msg)

    # --- 6. water is translucent and animated (the "water looks terrible" bug)
    water_problems = check_water()
    checks += 1
    for _name, msg in water_problems:
        fails.append(msg)

    # --- 7. varyings resolve, sky/fog follow the dimension
    for extra in (check_varyings, check_sky_and_fog):
        probs = extra()
        checks += 1
        for _name, msg in probs:
            fails.append(msg)

    print("")
    print("  RESULT  checks=%d  fails=%d" % (checks, len(fails)))
    if fails:
        for f in fails[:20]:
            print("    - " + f)
    print("")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())