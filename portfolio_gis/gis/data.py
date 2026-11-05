from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
import rasterio
import requests
from pyproj import Transformer
from rasterio.warp import reproject
from rasterio.windows import from_bounds

from .common import RAW_DATA

NATURAL_EARTH_URL = (
    "https://naturalearth.s3.amazonaws.com/110m_cultural/"
    "ne_110m_admin_0_countries.zip"
)
SENTINEL_ITEM_URL = (
    "https://earth-search.aws.element84.com/v1/collections/"
    "sentinel-2-l2a/items/S2A_29UPV_20240421_0_L2A"
)
DUBLIN_BOUNDS = (-6.40, 53.25, -6.10, 53.42)


def download(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, timeout=90)
    response.raise_for_status()
    destination.write_bytes(response.content)
    return destination


def prepare_natural_earth() -> Path:
    directory = RAW_DATA / "natural_earth"
    shapefile = directory / "ne_110m_admin_0_countries.shp"
    if shapefile.exists():
        return shapefile
    archive = download(NATURAL_EARTH_URL, directory / "countries.zip")
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(directory)
    return shapefile


def _read_window(asset: dict, bounds: tuple[float, float, float, float]):
    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
    ):
        with rasterio.open(asset["href"]) as source:
            window = from_bounds(*bounds, transform=source.transform)
            array = source.read(1, window=window, masked=True)
            transform = source.window_transform(window)
            profile = source.profile.copy()
            profile.update(
                height=array.shape[0],
                width=array.shape[1],
                transform=transform,
                driver="GTiff",
                compress="deflate",
                tiled=True,
            )
            return array, profile


def _write_array(path: Path, array, profile: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **profile) as target:
        target.write(array.filled(0) if np.ma.isMaskedArray(array) else array, 1)


def prepare_sentinel() -> dict[str, Path | dict]:
    directory = RAW_DATA / "sentinel"
    paths = {name: directory / f"{name}.tif" for name in ("red", "nir", "scl")}
    metadata_path = directory / "item.json"
    if all(path.exists() for path in paths.values()) and metadata_path.exists():
        return {**paths, "item": json.loads(metadata_path.read_text(encoding="utf-8"))}

    response = requests.get(SENTINEL_ITEM_URL, timeout=60)
    response.raise_for_status()
    item = response.json()
    transformer = Transformer.from_crs("EPSG:4326", item["properties"]["proj:epsg"], always_xy=True)
    left, bottom = transformer.transform(DUBLIN_BOUNDS[0], DUBLIN_BOUNDS[1])
    right, top = transformer.transform(DUBLIN_BOUNDS[2], DUBLIN_BOUNDS[3])
    bounds = (left, bottom, right, top)

    arrays = {}
    profiles = {}
    for name in ("red", "nir", "scl"):
        arrays[name], profiles[name] = _read_window(item["assets"][name], bounds)

    aligned_scl = np.zeros(arrays["red"].shape, dtype=np.uint8)
    reproject(
        source=np.ma.filled(arrays["scl"], 0),
        destination=aligned_scl,
        src_transform=profiles["scl"]["transform"],
        src_crs=profiles["scl"]["crs"],
        src_nodata=0,
        dst_transform=profiles["red"]["transform"],
        dst_crs=profiles["red"]["crs"],
        dst_nodata=0,
        resampling=rasterio.enums.Resampling.nearest,
    )
    arrays["scl"] = aligned_scl
    profiles["scl"] = {
        **profiles["red"],
        "dtype": "uint8",
        "nodata": 0,
        "count": 1,
    }

    for name in paths:
        _write_array(paths[name], arrays[name], profiles[name])
    metadata_path.write_text(json.dumps(item, indent=2), encoding="utf-8")
    return {**paths, "item": item}
