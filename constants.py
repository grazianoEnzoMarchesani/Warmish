"""Defines constants for the application, specifically for color palettes.

This module centralizes the mapping between user-friendly palette names
and their corresponding matplotlib colormap objects. This allows for easy
management and extension of available color schemes.
"""

import matplotlib.cm as cm

# PALETTE_MAP: A dictionary mapping human-readable names to matplotlib colormaps.
#
# This constant provides a centralized registry of available color palettes.
# The keys are strings (e.g., "Iron", "Rainbow") that can be displayed in a UI,
# and the values are the actual colormap objects from the `matplotlib.cm` module.
#
# Note: Some colormaps use the `_r` suffix (e.g., `cm.spring_r`). This denotes
# the "reversed" version of that specific colormap.
PALETTE_MAP = {
    "Iron": cm.inferno,
    "Rainbow": cm.nipy_spectral,
    "Grayscale": cm.gray,
    "Lava": cm.hot,
    "Arctic": cm.cool,
    "Glowbow": cm.gist_rainbow,
    "Amber": cm.YlOrBr,
    "Sepia": cm.copper,
    "Plasma": cm.plasma,
    "Viridis": cm.viridis,
    "Magma": cm.magma,
    "Cividis": cm.cividis,
    "Turbo": cm.turbo,
    "Ocean": cm.ocean,
    "Terrain": cm.terrain,
    "Jet": cm.jet,
    "Fire": cm.afmhot,
    "Ice": cm.winter,
    "Spring": cm.spring_r,
    "Summer": cm.summer,
    "Autumn": cm.autumn,
    "Bone": cm.bone,
    "Pink": cm.pink,
    "Coolwarm": cm.coolwarm,
    "RdYlBu": cm.RdYlBu_r,
    "Spectral": cm.Spectral_r,
    "BrBG": cm.BrBG_r,
    "PiYG": cm.PiYG_r,
    "PRGn": cm.PRGn_r,
    "RdBu": cm.RdBu_r,
    "RdGy": cm.RdGy_r,
    "Purples": cm.Purples,
    "Blues": cm.Blues,
    "Greens": cm.Greens,
    "Oranges": cm.Oranges,
    "Reds": cm.Reds,
}