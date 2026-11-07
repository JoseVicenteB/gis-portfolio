from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap, LightSource, Normalize
from matplotlib.collections import LineCollection
from PIL import Image
from scipy import ndimage
from shapely.geometry import mapping

from .common import COLORS, GENERATED, configure_matplotlib, save_webp, write_json
from .flood_data import (
    HYDROLOGY_URL,
    HYDRAULICS_URL,
    LIDAR_CATALOGUE_URL,
    STUDY_BOUNDS,
    prepare_flood_sources,
)
from .flood_model import generate_flood_model, load_configuration

FLOOD_CMAP = LinearSegmentedColormap.from_list(
    "flood", ["#b9e4ec", "#70c2d4", "#318ab5", "#175b8c", "#08365f"]
)
LANDMARKS = {
    "Islandbridge": (713758.2236, 734280.2794),
    "Custom House": (716317.3865, 734509.1955),
    "Dublin Port": (718841.6771, 734794.2886),
}


def _round_coordinates(coordinates):
    if isinstance(coordinates[0], (float, int)):
        return [round(float(value), 1) for value in coordinates]
    return [_round_coordinates(item) for item in coordinates]


def _terrain_texture(result: dict) -> Image.Image:
    elevation = result["display_terrain"]
    valid = result["display_valid"]
    if not valid.all():
        indices = ndimage.distance_transform_edt(~valid, return_distances=False, return_indices=True)
        filled = elevation[tuple(indices)]
    else:
        filled = elevation
    cmap = LinearSegmentedColormap.from_list(
        "liffey-terrain", ["#d6e4d7", "#dce2c9", "#e8d7b5", "#c9b493", "#a28d7c"]
    )
    light = LightSource(azdeg=315, altdeg=38)
    rgb = light.shade(
        filled,
        cmap=cmap,
        norm=Normalize(-2, max(25, float(np.nanmax(filled)))),
        blend_mode="soft",
        vert_exag=1.2,
        dx=20,
        dy=20,
    )
    factor = result["display_factor"]
    water = result["permanent_water"]
    water = water[: water.shape[0] // factor * factor, : water.shape[1] // factor * factor]
    water = water.reshape(water.shape[0] // factor, factor, water.shape[1] // factor, factor).max(axis=(1, 3))
    rgb[water] = [0.55, 0.73, 0.75, 1]
    rgb[~valid] = [0.76, 0.81, 0.80, 0]
    return Image.fromarray(np.clip(rgb * 255, 0, 255).astype("uint8"), mode="RGBA")


def _read_depth(path: Path, maximum: float) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image, dtype="float32") / 255 * maximum


def _road_segments(features: list[dict]) -> list[list]:
    major = {"motorway", "trunk", "primary", "secondary", "tertiary"}
    segments = []
    for feature in features:
        if feature["properties"]["highway"] not in major:
            continue
        geometry = feature["geometry"]
        lines = [geometry["coordinates"]] if geometry["type"] == "LineString" else geometry["coordinates"]
        segments.extend(lines)
    return segments


def _style_map_axis(ax, bounds=STUDY_BOUNDS) -> None:
    left, bottom, right, top = bounds
    ax.set_xlim(left, right)
    ax.set_ylim(bottom, top)
    ax.set_aspect("equal")
    ax.axis("off")
    width = right - left
    height = top - bottom
    x = left + width * 0.035
    y = bottom + height * 0.045
    ax.plot([x, x + 2000], [y, y], color=COLORS["ink"], linewidth=2, solid_capstyle="butt")
    ax.text(x + 1000, y + height * 0.018, "2 km", ha="center", fontsize=8, color=COLORS["ink"])
    nx = right - width * 0.04
    ny = top - height * 0.12
    ax.annotate(
        "N",
        xy=(nx, ny + height * 0.065),
        xytext=(nx, ny),
        ha="center",
        fontsize=9,
        fontweight="bold",
        color=COLORS["ink"],
        arrowprops={"arrowstyle": "-|>", "color": COLORS["ink"], "lw": 1.1},
    )


def _draw_flood_map(ax, result: dict, scenario: dict, frame_index: int, labels: bool = True) -> None:
    output = GENERATED / "flood"
    left, bottom, right, top = STUDY_BOUNDS
    texture = _terrain_texture(result)
    ax.imshow(texture, extent=(left, right, bottom, top), interpolation="bilinear")
    depth = _read_depth(output / scenario["frames"][frame_index]["file"], result["depth_encoding_max_m"])
    masked = np.ma.masked_less(depth, 0.05)
    image = ax.imshow(
        masked,
        extent=(left, right, bottom, top),
        cmap=FLOOD_CMAP,
        norm=Normalize(0, 3.5),
        interpolation="nearest",
    )
    segments = _road_segments(result["road_features"])
    ax.add_collection(LineCollection(segments, colors="#324c47", linewidths=0.25, alpha=0.38))
    river = result["centerline"]
    ax.plot(*river.xy, color="#c4f1f2", linewidth=0.8, alpha=0.8)
    if labels:
        for name, (x, y) in LANDMARKS.items():
            ax.plot(x, y, marker="o", markersize=3, color=COLORS["paper"], markeredgecolor=COLORS["ink"], linewidth=0.6)
            ax.text(
                x + 90,
                y + 110,
                name,
                fontsize=8,
                color=COLORS["ink"],
                bbox={"facecolor": "#F7F5EFCC", "edgecolor": "none", "pad": 1.8},
            )
    _style_map_axis(ax)
    return image


def _static_figures(result: dict) -> None:
    configure_matplotlib()
    scenarios = result["scenarios"]
    default = next(item for item in scenarios if item["id"] == "aep1")
    fig, ax = plt.subplots(figsize=(12, 7.2), dpi=150)
    image = _draw_flood_map(ax, result, default, default["peak_frame"])
    colorbar = fig.colorbar(image, ax=ax, orientation="horizontal", fraction=0.045, pad=0.02, shrink=0.55)
    colorbar.set_label("Modelled water depth (m)", fontsize=9)
    colorbar.set_ticks([0, 0.5, 1, 2, 3.5])
    colorbar.set_ticklabels(["0", "0.5", "1", "2", "≥3.5"])
    colorbar.outline.set_visible(False)
    fig.text(0.02, 0.96, "1% AEP design scenario · peak connected inundation", fontsize=13, fontweight="bold")
    fig.text(
        0.02,
        0.015,
        "Educational reduced model · Terrain: GSI/OPW (2011) · Streets: © OpenStreetMap contributors",
        fontsize=7,
        color=COLORS["muted"],
    )
    save_webp(fig, "flood/liffey-flood-hero.webp", width=1800)

    fig, axes = plt.subplots(3, 1, figsize=(12, 15), dpi=150)
    for ax, scenario in zip(axes, scenarios):
        _draw_flood_map(ax, result, scenario, scenario["peak_frame"], labels=False)
        ax.set_title(
            f"{scenario['label']} · approximately 1 in {scenario['return_period_years']} annual chance",
            loc="left",
            fontsize=13,
            pad=8,
        )
    fig.suptitle("Peak connected inundation under three design scenarios", x=0.04, ha="left", fontsize=17)
    fig.text(
        0.04,
        0.01,
        "Connected inundation at each scenario's peak boundary hour. Not an official OPW flood map or a property-level assessment.",
        fontsize=8,
        color=COLORS["muted"],
    )
    fig.subplots_adjust(hspace=0.12)
    save_webp(fig, "flood/liffey-scenario-comparison.webp", width=1800)

    fig, axes = plt.subplots(2, 1, figsize=(11, 7.5), dpi=150)
    colors = ["#6c9a8b", "#d7794a", "#175b8c"]
    for scenario, color in zip(scenarios, colors):
        hours = [frame["hour"] for frame in scenario["frames"]]
        axes[0].plot(
            hours,
            [frame["downstream_flow_m3s"] for frame in scenario["frames"]],
            label=scenario["label"],
            color=color,
            linewidth=2,
        )
        axes[1].plot(
            hours,
            [frame["coastal_level_m"] for frame in scenario["frames"]],
            label=scenario["label"],
            color=color,
            linewidth=2,
        )
    axes[0].set_ylabel("Flow at 09_631_D (m³/s)")
    axes[1].set_ylabel("Coastal boundary (m OD Malin)")
    axes[1].set_xlabel("Scenario time (hours)")
    axes[0].set_title("Prescribed fluvial and coastal boundary conditions", loc="left", fontsize=16, pad=14)
    for ax in axes:
        ax.set_xlim(0, 48)
        ax.grid(color="#DDE2DC", linewidth=0.7)
        ax.set_axisbelow(True)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.legend(frameon=False, loc="upper left")
    axes[0].text(
        0,
        -0.25,
        "Hydrographs are normalised design inputs. Coastal peaks use published OPW extreme levels; they are not observed event measurements.",
        transform=axes[0].transAxes,
        fontsize=8,
        color=COLORS["muted"],
    )
    fig.subplots_adjust(hspace=0.4)
    save_webp(fig, "flood/liffey-boundary-conditions.webp", width=1600)


def _export_web(result: dict, config: dict, sources: dict) -> dict:
    output = GENERATED / "flood"
    elevation = result["display_terrain"]
    valid = result["display_valid"]
    if not valid.all():
        indices = ndimage.distance_transform_edt(~valid, return_distances=False, return_indices=True)
        filled = elevation[tuple(indices)]
    else:
        filled = elevation.copy()
    minimum = math.floor(float(np.nanmin(filled)) * 10) / 10
    maximum = math.ceil(float(np.nanmax(filled)) * 10) / 10
    encoded = np.rint((filled - minimum) / (maximum - minimum) * 65535).astype("<u2")
    encoded.tofile(output / "terrain.bin")
    Image.fromarray((valid * 255).astype("uint8"), mode="L").save(output / "valid-mask.png", optimize=True)
    _terrain_texture(result).save(output / "terrain.webp", "WEBP", quality=91, method=6)

    road_features = []
    for feature in result["road_features"]:
        if feature["properties"]["highway"] == "service" and feature["properties"]["name"] == "Unnamed street":
            continue
        feature["geometry"]["coordinates"] = _round_coordinates(feature["geometry"]["coordinates"])
        road_features.append(feature)
    (output / "streets.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": road_features}, separators=(",", ":")),
        encoding="utf-8",
    )
    river_feature = {
        "type": "Feature",
        "properties": {"name": "River Liffey"},
        "geometry": mapping(result["centerline"]),
    }
    river_feature["geometry"]["coordinates"] = _round_coordinates(river_feature["geometry"]["coordinates"])
    (output / "river.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": [river_feature]}, separators=(",", ":")),
        encoding="utf-8",
    )
    default = next(item for item in result["scenarios"] if item["id"] == "aep1")
    peak = default["frames"][default["peak_frame"]]
    left, bottom, right, top = STUDY_BOUNDS
    summary = {
        "model_version": config["model_version"],
        "river_length_km": round(result["centerline"].length / 1000, 2),
        "analysis_resolution_m": config["analysis_resolution_m"],
        "display_resolution_m": config["display_resolution_m"],
        "source_tile_count": len(sources["tiles"]),
        "dtm_coverage_percentage": round(result["terrain"]["coverage"] * 100, 1),
        "frame_count": len(default["frames"]),
        "default_peak_wet_area_km2": peak["wet_area_km2"],
        "default_peak_affected_road_km": max(frame["affected_road_km"] for frame in default["frames"]),
        "default_max_depth_m": max(frame["max_depth_m"] for frame in default["frames"]),
        "scenarios": result["summary_scenarios"],
    }
    write_json(output / "summary.json", summary)
    manifest = {
        "model_version": config["model_version"],
        "crs": "EPSG:2157",
        "vertical_datum": "OD Malin",
        "bounds": STUDY_BOUNDS,
        "width_m": right - left,
        "height_m": top - bottom,
        "grid": {
            "rows": elevation.shape[0],
            "columns": elevation.shape[1],
            "resolution_m": config["display_resolution_m"],
        },
        "terrain": {
            "file": "terrain.bin",
            "texture": "terrain.webp",
            "valid_mask": "valid-mask.png",
            "minimum_m": minimum,
            "maximum_m": maximum,
            "encoding": "uint16-le",
        },
        "streets_file": "streets.geojson",
        "river_file": "river.geojson",
        "depth_encoding_max_m": result["depth_encoding_max_m"],
        "vertical_exaggeration": config["vertical_exaggeration"],
        "minimum_mapped_depth_m": config["minimum_mapped_depth_m"],
        "street_depth_threshold_m": config["street_depth_threshold_m"],
        "default_scenario": "aep1",
        "scenarios": result["scenarios"],
        "summary": summary,
        "configuration": config,
        "tide_metadata": result["tide_metadata"],
        "landmarks": [{"name": name, "coordinates": coordinates} for name, coordinates in LANDMARKS.items()],
        "sources": [
            {
                "name": "OPW NASC 2 m DTM via GSI Open Topographic Data",
                "url": LIDAR_CATALOGUE_URL,
                "licence": "CC BY 4.0",
                "attribution": "Contains Irish Public Sector Data (Geological Survey Ireland & the Office of Public Works) licensed under CC BY 4.0",
            },
            {
                "name": "Eastern CFRAM Liffey Hydrology Report",
                "url": HYDROLOGY_URL,
                "usage": "Published Qmed and design peak flows, Appendix D Model 2C",
            },
            {
                "name": "Eastern CFRAM Liffey Hydraulics Report",
                "url": HYDRAULICS_URL,
                "usage": "Lower Liffey model scope, Manning n and NE_19 extreme coastal levels, Table 4.7.2",
            },
            {
                "name": "Marine Institute Dublin Port tide predictions",
                "url": "https://erddap.marine.ie/erddap/tabledap/IMI_TidePrediction_HighLow.html",
                "licence": "CC BY 4.0",
            },
            {
                "name": "OpenStreetMap contributors",
                "url": "https://www.openstreetmap.org/copyright",
                "licence": "ODbL 1.0",
            },
        ],
        "limitations": [
            "Educational design scenarios, not live forecasts or official flood maps.",
            "Stage-driven equilibrium surfaces with connected flood spread; no momentum, velocity, or calibrated floodplain storage.",
            "Reduced channel geometry and linear tidal attenuation are assumptions, not surveyed hydraulic structures.",
            "Reservoir routing and compound-event timing are hypothetical sensitivity experiments with prescribed settings, not operator decisions or surge forecasts.",
            "No calibrated 2D hydrodynamics, dynamic sewer, culvert blockage, groundwater, defence breach, observed reservoir-operation, wave, or storm-surge model.",
            "The 2011 DTM and resampled outputs must not be used for individual property or road-safety decisions.",
        ],
    }
    write_json(output / "manifest.json", manifest)
    return summary


def generate_flood_assets() -> None:
    config = load_configuration()
    output = GENERATED / "flood"
    if output.exists():
        shutil.rmtree(output)
    sources = prepare_flood_sources()
    result = generate_flood_model(sources, config)
    _export_web(result, config, sources)
    _static_figures(result)
    print(f"Flood project assets written to {output}")


if __name__ == "__main__":
    generate_flood_assets()
