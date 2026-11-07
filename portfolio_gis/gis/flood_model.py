from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.features import rasterize
from rasterio.merge import merge
from rasterio.transform import from_origin
from scipy import ndimage
from scipy.spatial import cKDTree
from shapely import ops
from shapely.geometry import LineString, MultiLineString, Point, Polygon, mapping, shape
from shapely.ops import transform

from .common import GENERATED, RAW_DATA
from .flood_data import RAW_FLOOD, STUDY_BOUNDS, STUDY_CRS

UPSTREAM_POINT = Point(713758.2236, 734280.2794)
DOWNSTREAM_POINT = Point(718841.6771, 734794.2886)


def load_configuration() -> dict:
    path = Path.cwd() / "content" / "flood-scenarios.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _read_features(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["features"]


def _parts(geometry):
    if geometry.is_empty:
        return []
    if isinstance(geometry, LineString):
        return [geometry]
    if isinstance(geometry, MultiLineString):
        return list(geometry.geoms)
    return []


def prepare_terrain(tile_paths: list[Path], config: dict) -> dict:
    resolution = config["analysis_resolution_m"]
    output = RAW_FLOOD / f"terrain-{resolution}m.tif"
    if output.exists():
        with rasterio.open(output) as source:
            terrain = source.read(1, masked=True)
            transform = source.transform
            profile = source.profile
    else:
        terrain, transform = merge(
            tile_paths,
            bounds=STUDY_BOUNDS,
            res=resolution,
            nodata=-9999,
            resampling=rasterio.enums.Resampling.average,
            masked=True,
        )
        terrain = terrain[0].astype("float32")
        profile = {
            "driver": "GTiff",
            "height": terrain.shape[0],
            "width": terrain.shape[1],
            "count": 1,
            "dtype": "float32",
            "crs": STUDY_CRS,
            "transform": transform,
            "nodata": -9999,
            "compress": "deflate",
            "tiled": True,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(output, "w", **profile) as target:
            target.write(terrain.filled(-9999), 1)
    valid = np.ma.getmaskarray(terrain) == False
    if valid.mean() < 0.75:
        raise ValueError(f"Insufficient DTM coverage: {valid.mean():.1%}")
    values = terrain[valid]
    if not np.isfinite(values).all():
        raise ValueError("Non-finite terrain values in the active model grid")
    return {
        "array": terrain.filled(np.nan).astype("float32"),
        "valid": valid,
        "transform": transform,
        "profile": profile,
        "coverage": float(valid.mean()),
    }


def build_centerline(river_path: Path) -> LineString:
    lines = []
    bank_polygons = []
    for feature in _read_features(river_path):
        geometry = shape(feature["geometry"])
        if feature["properties"].get("waterway") == "riverbank":
            if geometry.is_closed:
                bank_polygons.append(Polygon(geometry.coords))
            continue
        lines.append(geometry)
    merged = ops.linemerge(ops.unary_union(lines))
    candidates = _parts(merged)
    if not candidates:
        raise ValueError("No connected River Liffey centreline could be built")
    def score(line):
        return (
            line.distance(UPSTREAM_POINT)
            + line.distance(DOWNSTREAM_POINT)
            - min(line.length, 12000) / 5000
        )
    line = min(candidates, key=score)
    start = line.project(UPSTREAM_POINT)
    end = line.project(DOWNSTREAM_POINT)
    if start > end:
        line = LineString(line.coords[::-1])
        start, end = line.project(UPSTREAM_POINT), line.project(DOWNSTREAM_POINT)
    reach = ops.substring(line, start, end)
    if reach.length < 4000:
        raise ValueError(f"Extracted Liffey reach is unexpectedly short: {reach.length:.0f} m")
    reach = reach.intersection(__import__("shapely").geometry.box(*STUDY_BOUNDS))
    return reach, bank_polygons


def _densify(line: LineString, spacing: float) -> np.ndarray:
    distances = np.arange(0, line.length, spacing)
    if distances.size == 0 or distances[-1] != line.length:
        distances = np.append(distances, line.length)
    points = [line.interpolate(float(distance)) for distance in distances]
    return np.array([(point.x, point.y) for point in points])


def _cell_indices(points: np.ndarray, transform, shape_) -> np.ndarray:
    rows, columns = rasterio.transform.rowcol(transform, points[:, 0], points[:, 1])
    rows = np.asarray(rows)
    columns = np.asarray(columns)
    inside = (rows >= 0) & (rows < shape_[0]) & (columns >= 0) & (columns < shape_[1])
    return np.unique(rows[inside] * shape_[1] + columns[inside])


def _prepare_roads(path: Path, transform, shape_) -> tuple[list[dict], list[dict]]:
    features = []
    samples = []
    bounds = STUDY_BOUNDS
    for feature in _read_features(path):
        geometry = shape(feature["geometry"]).intersection(
            __import__("shapely").geometry.box(*bounds)
        )
        parts = _parts(geometry)
        if not parts:
            continue
        properties = feature["properties"]
        road_id = str(properties["osm_id"])
        simplified = [mapping(part.simplify(5)) for part in parts]
        web_geometry = (
            simplified[0]
            if len(simplified) == 1
            else {"type": "MultiLineString", "coordinates": [item["coordinates"] for item in simplified]}
        )
        features.append(
            {
                "type": "Feature",
                "id": road_id,
                "properties": {
                    "id": road_id,
                    "name": properties.get("name", "Unnamed street"),
                    "highway": properties.get("highway", "road"),
                },
                "geometry": web_geometry,
            }
        )
        indices = []
        length = 0.0
        for part in parts:
            length += part.length
            indices.append(_cell_indices(_densify(part, 10), transform, shape_))
        if indices:
            samples.append(
                {
                    "id": road_id,
                    "indices": np.unique(np.concatenate(indices)),
                    "length": length,
                }
            )
    return features, samples


def _tide_series(path: Path, hours: np.ndarray, period: float, peak_hour: float) -> tuple[np.ndarray, dict]:
    with path.open(encoding="utf-8") as source:
        rows = list(csv.reader(source))[2:]
    levels = [float(row[3]) for row in rows if row and row[0] == "Dublin_Port"]
    if len(levels) < 8:
        raise ValueError("Insufficient Dublin Port high/low tide predictions")
    mean = (max(levels) + min(levels)) / 2
    amplitude = (max(levels) - min(levels)) / 2
    tide = mean + amplitude * np.cos(2 * np.pi * (hours - peak_hour) / period)
    return tide, {
        "mean_level_m": mean,
        "amplitude_m": amplitude,
        "prediction_min_m": min(levels),
        "prediction_max_m": max(levels),
    }


def _normal_depth(flow, width, slope, roughness):
    return np.power((flow * roughness) / (width * np.sqrt(slope)), 0.6)


def _design_hydrograph(hours: np.ndarray, config: dict, scenario: dict) -> tuple[np.ndarray, np.ndarray]:
    fraction_peak = np.power(
        (hours / config["hydrograph"]["peak_hour"]),
        config["hydrograph"]["shape"],
    ) * np.exp(
        config["hydrograph"]["shape"] * (1 - hours / config["hydrograph"]["peak_hour"])
    )
    upstream = config["upstream_node"]["qmed_m3s"] + (
        scenario["peak_upstream_flow_m3s"] - config["upstream_node"]["qmed_m3s"]
    ) * fraction_peak
    downstream = config["downstream_flow_node"]["qmed_m3s"] + (
        scenario["peak_downstream_flow_m3s"] - config["downstream_flow_node"]["qmed_m3s"]
    ) * fraction_peak
    return upstream, downstream


def _route_reservoir(inflow: np.ndarray, config: dict) -> tuple[np.ndarray, np.ndarray, dict]:
    settings = config["reservoir_experiment"]
    frame_seconds = config["frame_interval_minutes"] * 60
    substeps = round(frame_seconds / settings["routing_step_seconds"])
    if substeps < 1 or not np.isclose(substeps * settings["routing_step_seconds"], frame_seconds):
        raise ValueError("Reservoir routing step must divide the frame interval exactly")
    dt = settings["routing_step_seconds"]
    storage = float(settings["initial_storage_m3"])
    storage_values = np.empty_like(inflow)
    release_values = np.empty_like(inflow)
    storage_values[0] = storage
    total_inflow = 0.0
    total_release = 0.0

    def prescribed_release(level):
        return float(np.clip(
            settings["base_release_m3s"]
            + (level - settings["target_storage_m3"]) / settings["release_response_seconds"],
            settings["minimum_release_m3s"],
            settings["maximum_release_m3s"],
        ))

    release = prescribed_release(storage)
    release_values[0] = release
    for index in range(len(inflow) - 1):
        for substep in range(substeps):
            fraction = substep / substeps
            current_inflow = float(inflow[index] + fraction * (inflow[index + 1] - inflow[index]))
            next_storage = float(np.clip(
                storage + (current_inflow - release) * dt,
                0,
                settings["storage_capacity_m3"],
            ))
            actual_release = current_inflow - (next_storage - storage) / dt
            total_inflow += current_inflow * dt
            total_release += actual_release * dt
            storage = next_storage
        storage_values[index + 1] = storage
        release = prescribed_release(storage)
        release_values[index + 1] = release

    volume_error = abs(
        settings["initial_storage_m3"] + total_inflow - total_release - storage
    )
    if volume_error > 0.01:
        raise ValueError(f"Reservoir routing water balance failed: {volume_error:.6f} m³")
    return release_values, storage_values, {
        **settings,
        "final_storage_m3": round(storage, 3),
        "volume_conservation_error_m3": round(volume_error, 6),
    }


def _river_profile(centerline: LineString, terrain: dict, config: dict) -> dict:
    points = _densify(centerline, 10)
    chainage = np.concatenate(([0], np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))))
    rows, columns = rasterio.transform.rowcol(
        terrain["transform"], points[:, 0], points[:, 1]
    )
    rows = np.clip(np.asarray(rows), 0, terrain["array"].shape[0] - 1)
    columns = np.clip(np.asarray(columns), 0, terrain["array"].shape[1] - 1)
    sampled = terrain["array"][rows, columns]
    if not np.isfinite(sampled).all():
        sampled = np.where(np.isfinite(sampled), sampled, np.nanmedian(sampled))
    water = ndimage.median_filter(sampled, size=21, mode="nearest")
    water = ndimage.gaussian_filter1d(water, sigma=8, mode="nearest")
    water = np.minimum.accumulate(water)
    slope = np.maximum(config["channel"]["default_energy_slope"], -np.gradient(water, chainage + 1e-6))
    slope = np.clip(slope, config["channel"]["default_energy_slope"], 0.005)
    fraction = chainage / max(chainage[-1], 1)
    width = (
        config["channel"]["upstream_width_m"]
        + fraction * (config["channel"]["downstream_width_m"] - config["channel"]["upstream_width_m"])
    )
    qmed = (
        config["upstream_node"]["qmed_m3s"]
        + fraction * (config["downstream_flow_node"]["qmed_m3s"] - config["upstream_node"]["qmed_m3s"])
    )
    roughness = config["channel"]["manning_n"]
    base_depth = _normal_depth(qmed, width, slope, roughness)
    bed = water - base_depth
    return {
        "points": points,
        "chainage": chainage,
        "base_water": water,
        "bed": bed,
        "width": width,
        "slope": slope,
        "fraction": fraction,
        "qmed": qmed,
        "roughness": roughness,
    }


def _chainage_grid(river: dict, terrain: dict) -> np.ndarray:
    cache = RAW_FLOOD / "chainage-indices.npy"
    if cache.exists() and np.load(cache, mmap_mode="r").shape == terrain["array"].shape:
        return np.load(cache)
    rows, columns = np.indices(terrain["array"].shape)
    transform = terrain["transform"]
    x = transform.c + (columns.ravel() + 0.5) * transform.a
    y = transform.f + (rows.ravel() + 0.5) * transform.e
    tree = cKDTree(river["points"])
    _, nearest = tree.query(np.column_stack((x, y)), workers=-1)
    nearest = nearest.astype("int32").reshape(terrain["array"].shape)
    np.save(cache, nearest)
    return nearest


def _display_terrain(terrain: np.ndarray, valid: np.ndarray, factor: int) -> tuple[np.ndarray, np.ndarray]:
    rows, columns = terrain.shape
    array = terrain[: rows // factor * factor, : columns // factor * factor]
    mask = valid[: array.shape[0], : array.shape[1]]
    display_rows = array.shape[0] // factor
    display_columns = array.shape[1] // factor
    array = array.reshape(display_rows, factor, display_columns, factor)
    mask = mask.reshape(display_rows, factor, display_columns, factor)
    total = np.sum(np.where(mask, np.nan_to_num(array), 0), axis=(1, 3))
    count = np.sum(mask, axis=(1, 3))
    display = np.divide(total, count, out=np.full(total.shape, np.nan), where=count > 0)
    return display.astype("float32"), count > 0


def _save_depth_png(path: Path, depth: np.ndarray, maximum: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = np.clip(np.rint(depth / maximum * 255), 0, 255).astype("uint8")
    Image.fromarray(encoded, mode="L").save(path, optimize=True)


def generate_flood_model(sources: dict, config: dict) -> dict:
    terrain = prepare_terrain(sources["tiles"], config)
    centerline, bank_polygons = build_centerline(sources["osm"]["river"])
    river = _river_profile(centerline, terrain, config)
    nearest = _chainage_grid(river, terrain)
    hours = np.arange(
        0,
        config["duration_hours"] + config["frame_interval_minutes"] / 60,
        config["frame_interval_minutes"] / 60,
    )
    tide, tide_metadata = _tide_series(
        sources["tide"], hours, config["tide"]["period_hours"], config["hydrograph"]["peak_hour"]
    )
    height, width = terrain["array"].shape
    transform = terrain["transform"]
    source_geometries = [centerline.buffer(35)] + bank_polygons
    river_mask = rasterize(
        [(geometry, 1) for geometry in source_geometries if not geometry.is_empty],
        out_shape=(height, width),
        transform=transform,
        fill=0,
        dtype="uint8",
    ).astype(bool)
    rows, columns = np.indices((height, width))
    x = transform.c + (columns + 0.5) * transform.a
    estuary = (x > 719500) & (terrain["array"] < 1.2)
    permanent_water = river_mask | estuary
    source_mask = permanent_water.copy()
    road_features, road_samples = _prepare_roads(sources["osm"]["streets"], transform, (height, width))
    factor = round(config["display_resolution_m"] / config["analysis_resolution_m"])
    display_terrain, display_valid = _display_terrain(terrain["array"], terrain["valid"], factor)
    display_permanent = _display_terrain(
        permanent_water.astype("float32"), np.ones_like(permanent_water, dtype=bool), factor
    )[0] > 0.2
    output = GENERATED / "flood"
    output.mkdir(parents=True, exist_ok=True)
    depth_maximum = 8.0
    attenuation = river["fraction"]
    scenario_definitions = [dict(scenario) for scenario in config["scenarios"]]
    for experiment in config.get("scenario_experiments", []):
        base = next(item for item in config["scenarios"] if item["id"] == experiment["base_scenario"])
        scenario_definitions.append({**base, **experiment})
    scenario_outputs = []
    summary_scenarios = []
    for scenario in scenario_definitions:
        upstream_flow, downstream_flow = _design_hydrograph(hours, config, scenario)
        reservoir_storage = None
        reservoir_metadata = None
        if scenario.get("kind") == "reservoir":
            design_upstream = upstream_flow.copy()
            upstream_flow, reservoir_storage, reservoir_metadata = _route_reservoir(upstream_flow, config)
            downstream_flow = np.maximum(0, downstream_flow + upstream_flow - design_upstream)
        coastal_peak_hour = config["hydrograph"]["peak_hour"] + scenario.get("coastal_peak_shift_hours", 0)
        scenario_tide = tide
        if coastal_peak_hour != config["hydrograph"]["peak_hour"]:
            scenario_tide, _ = _tide_series(
                sources["tide"], hours, config["tide"]["period_hours"], coastal_peak_hour
            )
        residual = np.maximum(scenario["coastal_peak_m"] - scenario_tide.max(), 0)
        surge = residual * np.exp(-0.5 * ((hours - coastal_peak_hour) / 6) ** 2)
        coastal = scenario_tide + surge
        frames = []
        peak_depth = np.zeros_like(terrain["array"], dtype="float32")
        peak_wet = np.zeros_like(terrain["valid"])
        peak_area = -1.0
        peak_index = 0
        for index, hour in enumerate(hours):
            flow_profile = river["qmed"] + (
                (upstream_flow[index] + river["fraction"] * (downstream_flow[index] - upstream_flow[index]))
                - river["qmed"]
            )
            depth_profile = _normal_depth(flow_profile, river["width"], river["slope"], river["roughness"])
            fluvial_surface = river["bed"] + depth_profile
            tidal_surface = river["base_water"] * (1 - attenuation) + coastal[index] * attenuation
            water_surface = np.maximum(fluvial_surface, tidal_surface)
            candidate = water_surface[nearest] - terrain["array"]
            candidate[~terrain["valid"]] = np.nan
            candidate = np.nan_to_num(candidate, nan=-9999).astype("float32")
            candidate[source_mask] = np.maximum(candidate[source_mask], 0.1)
            possible = candidate >= config["minimum_mapped_depth_m"]
            labels, _ = ndimage.label(possible, structure=np.ones((3, 3), dtype="uint8"))
            source_labels = np.unique(labels[source_mask & possible])
            source_labels = source_labels[source_labels > 0]
            wet = np.isin(labels, source_labels)
            depth = np.where(wet, candidate, 0).astype("float32")
            depth[depth < config["minimum_mapped_depth_m"]] = 0
            if not np.isfinite(depth).all() or (depth < 0).any():
                raise ValueError("Invalid model depth encountered")
            floodplain_wet = wet & ~permanent_water & terrain["valid"]
            wet_area = float(floodplain_wet.sum() * config["analysis_resolution_m"] ** 2 / 1e6)
            road_depths = {}
            affected_length = 0.0
            for road in road_samples:
                values = depth.reshape(-1)[road["indices"]]
                maximum = float(values.max(initial=0))
                if maximum >= config["street_depth_threshold_m"]:
                    road_depths[road["id"]] = round(maximum, 2)
                    affected_length += min(road["length"], np.count_nonzero(values >= config["street_depth_threshold_m"]) * 10)
            display_depth = depth[: depth.shape[0] // factor * factor, : depth.shape[1] // factor * factor]
            display_depth = display_depth.reshape(
                display_depth.shape[0] // factor,
                factor,
                display_depth.shape[1] // factor,
                factor,
            ).max(axis=(1, 3))
            display_depth[display_permanent & (display_depth < 0.1)] = 0.1
            relative = f"depths/{scenario['id']}/{index:02d}.png"
            _save_depth_png(output / relative, display_depth, depth_maximum)
            frame_record = {
                "index": index,
                "hour": float(hour),
                "file": relative,
                "wet_area_km2": round(wet_area, 4),
                "affected_road_km": round(affected_length / 1000, 3),
                "max_depth_m": round(float(depth[~permanent_water].max(initial=0)), 3),
                "upstream_flow_m3s": round(float(upstream_flow[index]), 2),
                "downstream_flow_m3s": round(float(downstream_flow[index]), 2),
                "coastal_level_m": round(float(coastal[index]), 3),
                "road_depths": road_depths,
            }
            if reservoir_storage is not None:
                frame_record["reservoir_storage_m3"] = round(float(reservoir_storage[index]), 0)
                frame_record["reservoir_release_m3s"] = round(float(upstream_flow[index]), 2)
            frames.append(frame_record)
            np.maximum(peak_depth, depth, out=peak_depth)
            peak_wet |= floodplain_wet
            if wet_area > peak_area:
                peak_area = wet_area
                peak_index = index
        scenario_output = {**scenario, "peak_frame": peak_index, "frames": frames}
        if reservoir_metadata:
            scenario_output["reservoir"] = reservoir_metadata
        scenario_outputs.append(scenario_output)
        summary_scenarios.append(
            {
                "id": scenario["id"],
                "label": scenario["label"],
                "kind": scenario.get("kind", "design"),
                "peak_wet_area_km2": round(float(peak_wet.sum() * config["analysis_resolution_m"] ** 2 / 1e6), 3),
                "max_depth_m": round(float(peak_depth[~permanent_water].max(initial=0)), 3),
                "peak_frame": peak_index,
            }
        )
        print(
            f"{scenario['label']}: {summary_scenarios[-1]['peak_wet_area_km2']:.2f} km² maximum connected inundation"
        )
    return {
        "terrain": terrain,
        "centerline": centerline,
        "river": river,
        "display_terrain": display_terrain,
        "display_valid": display_valid,
        "permanent_water": permanent_water,
        "road_features": road_features,
        "scenarios": scenario_outputs,
        "summary_scenarios": summary_scenarios,
        "tide_metadata": tide_metadata,
        "depth_encoding_max_m": depth_maximum,
        "display_factor": factor,
    }
