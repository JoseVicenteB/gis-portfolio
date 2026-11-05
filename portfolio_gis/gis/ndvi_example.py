from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.colors import LinearSegmentedColormap, Normalize
from pyproj import Transformer

from .common import COLORS, GENERATED, configure_matplotlib, save_webp, write_json
from .data import prepare_sentinel

INVALID_SCL = (0, 1, 3, 8, 9, 10, 11)


def _calculate_ndvi(paths: dict) -> tuple[np.ndarray, dict, dict]:
    with rasterio.open(paths["red"]) as source:
        red_dn = source.read(1)
        profile = source.profile.copy()
        bounds = source.bounds
    with rasterio.open(paths["nir"]) as source:
        nir_dn = source.read(1)
    with rasterio.open(paths["scl"]) as source:
        scl = source.read(1)

    red_band = paths["item"]["assets"]["red"]["raster:bands"][0]
    nir_band = paths["item"]["assets"]["nir"]["raster:bands"][0]
    harmonized = paths["item"]["properties"].get("earthsearch:boa_offset_applied", False)
    red_offset = 0 if harmonized else red_band.get("offset", 0)
    nir_offset = 0 if harmonized else nir_band.get("offset", 0)
    red = red_dn.astype("float32") * red_band.get("scale", 1) + red_offset
    nir = nir_dn.astype("float32") * nir_band.get("scale", 1) + nir_offset

    valid = (
        (red_dn != 0)
        & (nir_dn != 0)
        & ~np.isin(scl, INVALID_SCL)
        & np.isfinite(red)
        & np.isfinite(nir)
    )
    denominator = nir + red
    valid &= np.abs(denominator) > 1e-6
    ndvi = np.full(red.shape, np.nan, dtype="float32")
    np.divide(nir - red, denominator, out=ndvi, where=valid)
    ndvi = np.clip(ndvi, -1, 1)
    ndvi[~valid] = np.nan
    return ndvi, profile, {"bounds": bounds, "scl": scl}


def _ndvi_colormap() -> LinearSegmentedColormap:
    colors = [
        (0.00, "#315E72"),
        (0.32, "#8FB9BA"),
        (0.48, "#D6C6A5"),
        (0.55, "#E8DFB9"),
        (0.65, "#A8C88B"),
        (0.80, "#4D9567"),
        (1.00, "#165840"),
    ]
    cmap = LinearSegmentedColormap.from_list("ndvi", colors)
    cmap.set_bad("#E5E3DC")
    return cmap


def _add_scale_and_north(ax, bounds) -> None:
    width = bounds.right - bounds.left
    height = bounds.top - bounds.bottom
    x = bounds.left + width * 0.055
    y = bounds.bottom + height * 0.065
    length = 5000
    ax.plot([x, x + length], [y, y], color=COLORS["ink"], linewidth=2.4, solid_capstyle="butt")
    ax.plot([x, x], [y - height * 0.006, y + height * 0.006], color=COLORS["ink"], linewidth=1)
    ax.plot([x + length, x + length], [y - height * 0.006, y + height * 0.006], color=COLORS["ink"], linewidth=1)
    ax.text(x + length / 2, y + height * 0.012, "5 km", ha="center", fontsize=9, color=COLORS["ink"])
    nx = bounds.right - width * 0.06
    ny = bounds.top - height * 0.08
    ax.annotate(
        "N",
        xy=(nx, ny + height * 0.035),
        xytext=(nx, ny - height * 0.025),
        ha="center",
        fontsize=10,
        fontweight="bold",
        arrowprops={"arrowstyle": "-|>", "color": COLORS["ink"], "lw": 1.3},
    )


def generate_ndvi_maps() -> None:
    configure_matplotlib()
    paths = prepare_sentinel()
    ndvi, profile, extra = _calculate_ndvi(paths)
    bounds = extra["bounds"]
    values = ndvi[np.isfinite(ndvi)]
    if values.size == 0:
        raise ValueError("No valid NDVI observations in study area")

    fig, ax = plt.subplots(figsize=(10.5, 10), dpi=160)
    image = ax.imshow(
        np.ma.masked_invalid(ndvi),
        cmap=_ndvi_colormap(),
        norm=Normalize(-1, 1),
        extent=(bounds.left, bounds.right, bounds.bottom, bounds.top),
        interpolation="nearest",
    )
    ax.set_aspect("equal")
    ax.axis("off")
    _add_scale_and_north(ax, bounds)
    transformer = Transformer.from_crs("EPSG:4326", profile["crs"], always_xy=True)
    dublin_x, dublin_y = transformer.transform(-6.2603, 53.3498)
    ax.plot(dublin_x, dublin_y, marker="o", markersize=4.5, color="#FFFFFF", markeredgecolor=COLORS["ink"])
    ax.text(
        dublin_x + (bounds.right - bounds.left) * 0.015,
        dublin_y,
        "Dublin",
        fontsize=10,
        fontweight="bold",
        color=COLORS["ink"],
        va="center",
        bbox={"facecolor": "#FFFFFFCC", "edgecolor": "none", "pad": 2.5},
    )
    colorbar = fig.colorbar(image, ax=ax, orientation="horizontal", fraction=0.035, pad=0.025, shrink=0.72)
    colorbar.set_label("Normalized Difference Vegetation Index (NDVI)", fontsize=10, labelpad=8)
    colorbar.set_ticks([-1, -0.5, 0, 0.5, 1])
    colorbar.outline.set_visible(False)
    fig.text(
        0.98,
        0.015,
        "Contains modified Copernicus Sentinel data (2024) · 21 Apr 2024",
        ha="right",
        fontsize=8,
        color=COLORS["muted"],
    )
    save_webp(fig, "ndvi/dublin-ndvi.webp", width=1600)

    fig, ax = plt.subplots(figsize=(11, 5.4), dpi=150)
    ax.hist(values, bins=np.linspace(-1, 1, 101), color="#548E70", edgecolor="#F7F5EF", linewidth=0.25)
    median = float(np.median(values))
    ax.axvline(median, color=COLORS["accent"], linewidth=2, label=f"Median: {median:.2f}")
    ax.set_xlim(-1, 1)
    ax.set_xlabel("NDVI")
    ax.set_ylabel("Valid pixels")
    ax.set_title("Distribution of valid observations", loc="left", fontsize=17, fontweight="bold", pad=16)
    ax.legend(frameon=False, loc="upper left")
    ax.grid(axis="y", color="#DDE2DC", linewidth=0.7)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    save_webp(fig, "ndvi/ndvi-histogram.webp", width=1600)

    summary = {
        "valid_pixels": int(values.size),
        "valid_percentage": round(float(values.size / ndvi.size * 100), 1),
        "median_ndvi": round(median, 3),
        "mean_ndvi": round(float(np.mean(values)), 3),
        "vegetated_percentage": round(float(np.mean(values >= 0.4) * 100), 1),
        "source_shape": list(ndvi.shape),
        "bounds_utm": [bounds.left, bounds.bottom, bounds.right, bounds.top],
    }
    write_json(GENERATED / "ndvi" / "summary.json", summary)

    ndvi_profile = {
        **profile,
        "dtype": "float32",
        "nodata": float("nan"),
        "compress": "deflate",
    }
    output = GENERATED / "ndvi" / "dublin-ndvi.tif"
    with rasterio.open(output, "w", **ndvi_profile) as target:
        target.write(ndvi, 1)
