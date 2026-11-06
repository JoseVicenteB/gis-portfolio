from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import requests
from pyproj import Transformer

from .common import RAW_DATA

STUDY_BOUNDS = (712000.0, 731500.0, 722000.0, 737500.0)
STUDY_CRS = "EPSG:2157"
LIDAR_COVERAGE_URL = (
    "https://gsi.geodata.gov.ie/server/rest/services/Lidar/"
    "IE_GSI_LiDAR_Coverage_OPW_NASC_IE26_ITM/MapServer/3/query"
)
LIDAR_CATALOGUE_URL = "https://www.arcgis.com/home/item.html?id=0cf979c135744df5bf51b11df9a6d820"
HYDROLOGY_URL = (
    "https://s3-eu-west-1.amazonaws.com/docs.floodinfo.opw/floodinfo_docs/"
    "Eastern_CFRAM/_UOM09/01_Hydrology/Liffey_Hydrology_Report_HA09.pdf"
)
HYDRAULICS_URL = (
    "https://s3-eu-west-1.amazonaws.com/docs.floodinfo.opw/floodinfo_docs/"
    "Eastern_CFRAM/_UOM09/02_Hydraulics/IBE0600Rp0027_HA09_Hydraulics_Report_F06.pdf"
)
TIDE_URL = "https://erddap.marine.ie/erddap/tabledap/IMI_TidePrediction_HighLow.csv"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
RAW_FLOOD = RAW_DATA / "flood"


def _download(url: str, destination: Path) -> Path:
    if destination.exists() and destination.stat().st_size > 0:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, timeout=(20, 180), stream=True) as response:
        response.raise_for_status()
        with destination.open("wb") as target:
            for chunk in response.iter_content(1024 * 1024):
                target.write(chunk)
    return destination


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_metadata(records: list[dict]) -> None:
    path = RAW_FLOOD / "sources.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2), encoding="utf-8")


def _read_cached_metadata(name: str) -> list[dict]:
    path = RAW_FLOOD / "sources.json"
    if not path.exists():
        return []
    records = json.loads(path.read_text(encoding="utf-8"))
    return [record for record in records if record.get("dataset") != name]


def prepare_lidar() -> list[Path]:
    directory = RAW_FLOOD / "lidar"
    metadata_path = directory / "tiles.json"
    if metadata_path.exists():
        features = json.loads(metadata_path.read_text(encoding="utf-8"))["features"]
    else:
        response = requests.get(
            LIDAR_COVERAGE_URL,
            params={
                "geometry": ",".join(str(int(value)) for value in STUDY_BOUNDS),
                "geometryType": "esriGeometryEnvelope",
                "inSR": 2157,
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "DATA_NAME,DATA_URL,LOCATION,LICENCE,RESOLUTION,DATECAPTUR,OWNER",
                "returnGeometry": "false",
                "f": "json",
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        features = payload["features"]
        directory.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if not features:
        raise RuntimeError("No OPW NASC LiDAR tiles intersect the Lower Liffey study area")

    paths = []
    source_records = _read_cached_metadata("lidar")
    for feature in sorted(features, key=lambda item: item["attributes"]["DATA_NAME"]):
        attributes = feature["attributes"]
        name = attributes["DATA_NAME"]
        archive = _download(attributes["DATA_URL"], directory / f"{name}.zip")
        tile_directory = directory / name
        tile_path = tile_directory / f"{name}_DTM.tif"
        if not tile_path.exists():
            with zipfile.ZipFile(archive) as bundle:
                for member in (f"{name}_DTM.tif", "Copyright_and_Licence.txt"):
                    bundle.extract(member, tile_directory)
        paths.append(tile_path)
        source_records.append(
            {
                "dataset": "lidar",
                "name": name,
                "url": attributes["DATA_URL"],
                "capture_date": attributes["DATECAPTUR"],
                "resolution_m": attributes["RESOLUTION"],
                "licence": attributes["LICENCE"],
                "sha256": _sha256(archive),
            }
        )
    _write_metadata(source_records)
    return paths


def _overpass(query: str, destination: Path) -> dict:
    if destination.exists():
        return json.loads(destination.read_text(encoding="utf-8"))
    errors = []
    for endpoint in (OVERPASS_URL, "https://overpass.kumi.systems/api/interpreter"):
        try:
            response = requests.get(
                endpoint,
                params={"data": query},
                headers={"User-Agent": "portfolio-gis-research/1.0"},
                timeout=(20, 300),
            )
            response.raise_for_status()
            payload = response.json()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(payload), encoding="utf-8")
            return payload
        except (requests.RequestException, ValueError) as error:
            errors.append(f"{endpoint}: {error}")
    raise RuntimeError("OpenStreetMap extract failed; " + "; ".join(errors))


def _osm_features(payload: dict, include: callable) -> list[dict]:
    transformer = Transformer.from_crs(4326, STUDY_CRS, always_xy=True)
    features = []
    for element in payload["elements"]:
        tags = element.get("tags", {})
        geometry = element.get("geometry")
        if element.get("type") != "way" or not geometry or not include(tags):
            continue
        coordinates = [
            transformer.transform(point["lon"], point["lat"])
            for point in geometry
        ]
        features.append(
            {
                "type": "Feature",
                "id": str(element["id"]),
                "properties": {**tags, "osm_id": str(element["id"])},
                "geometry": {"type": "LineString", "coordinates": coordinates},
            }
        )
    return features


def prepare_osm() -> dict[str, Path]:
    directory = RAW_FLOOD / "osm"
    south, west = 53.3218995805, -6.3188762298
    north, east = 53.3735847716, -6.1665450253
    bbox = f"{south},{west},{north},{east}"
    queries = {
        "river": (
            f'[out:json][timeout:180];way["waterway"~"river|riverbank"]'
            f'["name"~"Liffey",i]({bbox});out tags geom;'
        ),
        "streets": (
            f'[out:json][timeout:180];way["highway"~"motorway|trunk|primary|'
            f'secondary|tertiary|unclassified|residential|living_street|pedestrian|service"]'
            f'({bbox});out tags geom;'
        ),
    }
    outputs = {}
    for name, query in queries.items():
        payload = _overpass(query, directory / f"{name}-response.json")
        if name == "river":
            predicate = lambda tags: tags.get("waterway") in {"river", "riverbank"}
        else:
            predicate = lambda tags: bool(tags.get("highway"))
        features = _osm_features(payload, predicate)
        output = directory / f"{name}.geojson"
        output.write_text(
            json.dumps({"type": "FeatureCollection", "features": features}, indent=2),
            encoding="utf-8",
        )
        outputs[name] = output
    return outputs


def prepare_tide() -> Path:
    destination = RAW_FLOOD / "tide" / "dublin-port-2027-01.csv"
    if destination.exists():
        return destination
    query = (
        f"{TIDE_URL}?stationID,time,tide_time_category,Water_Level_ODMalin"
        "&stationID=%22Dublin_Port%22"
        "&time%3E=2027-01-14T00%3A00%3A00Z"
        "&time%3C=2027-01-18T00%3A00%3A00Z"
    )
    response = requests.get(query, timeout=60)
    response.raise_for_status()
    if "Dublin_Port" not in response.text:
        raise RuntimeError("Dublin Port tide predictions were not returned")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(response.text, encoding="utf-8")
    return destination


def prepare_reports() -> list[Path]:
    return [
        _download(HYDROLOGY_URL, RAW_FLOOD / "reports" / "liffey-hydrology.pdf"),
        _download(HYDRAULICS_URL, RAW_FLOOD / "reports" / "liffey-hydraulics.pdf"),
    ]


def prepare_flood_sources() -> dict:
    tiles = prepare_lidar()
    osm = prepare_osm()
    tide = prepare_tide()
    reports = prepare_reports()
    return {"tiles": tiles, "osm": osm, "tide": tide, "reports": reports}
