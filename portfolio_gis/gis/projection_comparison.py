from __future__ import annotations

import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import LineString, box

from .common import COLORS, GENERATED, configure_matplotlib, save_webp, write_json
from .data import prepare_natural_earth

PROJECTIONS = (
    {"id": "equal-earth", "crs": "EPSG:8857", "name": "Equal Earth", "property": "Equal-area"},
    {"id": "web-mercator", "crs": "EPSG:3857", "name": "Web Mercator", "property": "Conformal"},
    {"id": "robinson", "crs": "ESRI:54030", "name": "Robinson", "property": "Compromise"},
)


def _graticule() -> gpd.GeoDataFrame:
    geometries = []
    for longitude in range(-180, 181, 30):
        geometries.append(LineString((longitude, latitude) for latitude in range(-80, 81, 2)))
    for latitude in range(-60, 61, 30):
        geometries.append(LineString((longitude, latitude) for longitude in range(-180, 181, 2)))
    return gpd.GeoDataFrame(geometry=geometries, crs="EPSG:4326")


def generate_projection_maps() -> None:
    configure_matplotlib()
    countries = gpd.read_file(prepare_natural_earth())
    if countries.crs is None:
        raise ValueError("Natural Earth source has no CRS")
    countries = countries.to_crs("EPSG:4326")
    graticule = _graticule()
    web_countries = countries[["ADMIN", "geometry"]].rename(columns={"ADMIN": "name"})
    geojson_path = GENERATED / "projections" / "countries.geojson"
    geojson_path.write_text(web_countries.to_json(drop_id=True), encoding="utf-8")

    for projection in PROJECTIONS:
        source = countries
        lines = graticule
        if projection["id"] == "web-mercator":
            clipping_bounds = box(-180, -85.06, 180, 85.06)
            source = countries.copy()
            source["geometry"] = countries.geometry.intersection(clipping_bounds)
            source = source[~source.geometry.is_empty]

        mapped = source.to_crs(projection["crs"])
        mapped_lines = lines.to_crs(projection["crs"])
        fig, ax = plt.subplots(figsize=(12, 7.2), dpi=150)
        ax.set_facecolor(COLORS["ocean"])
        mapped_lines.plot(ax=ax, color="#A9C4BE", linewidth=0.55, linestyle=(0, (2, 4)), zorder=1)
        mapped.plot(
            ax=ax,
            facecolor=COLORS["land"],
            edgecolor=COLORS["boundary"],
            linewidth=0.32,
            zorder=2,
        )
        left, bottom, right, top = mapped.total_bounds
        x_pad = (right - left) * 0.025
        y_pad = (top - bottom) * 0.035
        ax.set_xlim(left - x_pad, right + x_pad)
        ax.set_ylim(bottom - y_pad, top + y_pad)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.text(
            0.025,
            0.965,
            projection["name"],
            transform=ax.transAxes,
            fontsize=22,
            fontweight="bold",
            va="top",
        )
        ax.text(
            0.026,
            0.91,
            f'{projection["property"]}  /  {projection["crs"]}',
            transform=ax.transAxes,
            fontsize=10,
            color=COLORS["muted"],
            va="top",
        )
        fig.text(
            0.985,
            0.025,
            "Natural Earth · 1:110m",
            ha="right",
            fontsize=8,
            color=COLORS["muted"],
        )
        save_webp(fig, f'projections/{projection["id"]}.webp')

    write_json(
        GENERATED / "projections" / "summary.json",
        {"projection_count": len(PROJECTIONS), "country_count": len(countries), "source_crs": "EPSG:4326"},
    )
