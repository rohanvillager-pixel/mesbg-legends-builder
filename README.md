# MESBG Legends of Middle-earth builder data

This project keeps the current [Now For Wrath](https://nowforwrath.github.io/data2024.json)
MESBG data and merges in the fan-made army lists from *Legends of Middle-earth 1.2*.

The merged game data adds a separate **Legends of Middle-earth** checkbox beside
Tabletop Admiral's **Include Legacy** option. The custom armies are hidden unless
that checkbox is enabled.

## Open the army builder

[Open Tabletop Admiral with Legends of Middle-earth](https://modular.tabletopadmiral.com/?gameUrl=https%3A%2F%2Fraw.githubusercontent.com%2Frohanvillager-pixel%2Fmesbg-legends-builder%2Fmain%2Fdata2024-legends.json)

## Updates

The GitHub Actions workflow runs once per day. It downloads the latest official
data, reapplies the Legends army layer, validates all faction and unit references,
and commits the generated files only when the upstream data has changed.

The builder link remains the same after updates.

## Files

- `custom/legends.json` - the persistent custom faction layer.
- `scripts/build.py` - deterministic merge and validation script.
- `data2024-legends.json` - generated Tabletop Admiral game data.
- `data2024-legends.update.json` - update manifest used by the builder.

## Source credit

Official game-builder data is provided by Now For Wrath. The additional fan lists
come from *Legends of Middle-earth 1.2* by Antonio Andrino (2 August 2026).
