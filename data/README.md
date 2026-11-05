# Data sources

## Natural Earth

- Dataset: Admin 0 — Countries, 1:110m cultural vectors.
- Source: https://www.naturalearthdata.com/
- Download: https://naturalearth.s3.amazonaws.com/110m_cultural/ne_110m_admin_0_countries.zip
- License: public domain (https://www.naturalearthdata.com/about/terms-of-use/).
- Use: global projection comparison; transformed from EPSG:4326 for static maps and exported as name-only GeoJSON for the live D3 map. The interactive map recomputes Equal Earth, Web Mercator, and Robinson paths in the browser from the same source geometries.

## Copernicus Sentinel-2

- Item: `S2A_29UPV_20240421_0_L2A`.
- Acquisition: 21 April 2024, 11:36:33 UTC.
- Scene cloud cover: 2.81041%; cloud cover is scene-level, not a measurement for the Dublin crop.
- Bands: B04 (red), B08 (near infrared), and SCL (scene classification).
- STAC record: https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a/items/S2A_29UPV_20240421_0_L2A
- Hosting: Sentinel-2 L2A cloud-optimized GeoTIFFs on AWS, accessed through Element 84 Earth Search.
- Data policy: https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice
- Attribution: contains modified Copernicus Sentinel data (2024).
- Radiometry: the legacy collection’s COGs are already harmonized when `earthsearch:boa_offset_applied` is true. The workflow applies the 0.0001 scale without subtracting the advertised offset a second time; see https://github.com/Element84/earth-search/issues/71.
- Use: Dublin NDVI demonstration. The workflow masks nodata and SCL classes 0, 1, 3, 8, 9, 10, and 11 (no data, defective, shadow, cloud, cirrus, and snow/ice). It is not a validated vegetation or land-cover assessment.

`portfolio-maps` downloads or remotely windows these inputs and caches the smaller study-area bands in `data/raw/sentinel/`. Raw data are ignored by Git. An internet connection is needed on the first run or after clearing the cache.
