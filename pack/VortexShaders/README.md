# Vortex Shaders

A shader pack for Minecraft Java Edition **26.3**, built for Iris. Works on any
GPU that can run Iris, but the settings below assume a modest card.

## Install

1. Unzip the `VortexShaders` folder into your shaderpacks directory:

   ```
   C:\Users\<you>\AppData\Roaming\.minecraft\shaderpacks\
   ```

   `AppData` is hidden — paste that path into Explorer's address bar instead of
   browsing for it. The result must be
   `.minecraft\shaderpacks\VortexShaders\shaders\`, not
   `.minecraft\shaderpacks\shaders\`.

2. Launch Minecraft with a **Fabric** profile that has **Iris** and **Sodium**
   installed. Shaders need Iris; Sodium is a required dependency of Iris.

3. **Options → Video Settings → Shader Packs → VortexShaders → Apply**

   Iris ships with shaders *off*. Installing the pack does not switch them on.
   If you re-copy the folder, re-apply — Iris caches compiled programs.

## What it does

- Sun with real directional shadows (3x3 PCF, soft edges)
- Per-pixel lighting: warm sunlight, cool ambient, block light from torches
- Distance fog that follows the biome and dimension
- Water: three travelling swells that genuinely displace the surface up and
  down, deep-blue absorption that darkens at grazing angles, and a sun glint
- Reinhard tonemapping, so bright highlights roll off instead of clipping

Sky and fog take their colour from Minecraft's own `skyColor` / `fogColor`, so
the Nether and the End are correct rather than wearing an overworld blue.

## Performance

If the frame rate is poor, change these in order:

1. **Shadow resolution** — `shadowResolution=1.0` in `shaders/shaders.properties`.
   Lower it, or set `shadow.enabled=false` for the biggest single win.
2. **Shadow distance** — shorter means fewer blocks cast shadows.
3. **Render distance** — fog is cheap, geometry is not.

The pack does not read or write your Minecraft options. Everything it controls
is inside its own `shaders/` folder.

## Honest limits

- Written and compile-checked with `glslang`, but the lighting values were
  reasoned rather than measured against reference frames.
- The surface has no foam or whitecaps. Breaking water at wave crests looked
  like white streaks sliding over the surface, so it is deliberately absent.
- A true splash on entering water needs a game event a shader cannot receive;
  the ripples follow the player's position instead.
- Tested on Minecraft 26.3 with Iris 1.11.7 and Sodium 0.9.3. Other versions may
  need adjustments.

## Uninstall

Delete the `VortexShaders` folder from `shaderpacks\`, or pick `Off` in the
Shader Packs menu.

## License

MIT. Use it, change it, ship your own version.
