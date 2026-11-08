# Data sources

## OPW / GSI Open Topographic LiDAR — Lower Liffey

- Dataset: OPW National Aerial Survey Contract (NASC) bare-earth DTM, distributed through the GSI Open Topographic Data catalogue.
- Catalogue: https://www.arcgis.com/home/item.html?id=0cf979c135744df5bf51b11df9a6d820
- Coverage service: https://gsi.geodata.gov.ie/server/rest/services/Lidar/IE_GSI_LiDAR_Coverage_OPW_NASC_IE26_ITM/MapServer/3
- Capture/resolution: 2011, 2 m; 23 intersecting 2 km tiles for the 10 × 6 km study window.
- CRS/vertical reference: ITM (EPSG:2157) and OD Malin. The source GeoTIFF projection parameters are checked and the analysis CRS is written explicitly as EPSG:2157.
- Licence: CC BY 4.0. Attribution: “Contains Irish Public Sector Data (Geological Survey Ireland & the Office of Public Works) licensed under a Creative Commons Attribution 4.0 International (CC BY 4.0) licence.”
- Use: 5 m terrain-connected inundation model and 20 m browser terrain. Raw tiles and mosaics remain in ignored `data/raw/flood/`; tile URLs and SHA-256 checksums are recorded in the local `sources.json`.

## OPW Eastern CFRAM technical reports

- Hydrology: https://s3-eu-west-1.amazonaws.com/docs.floodinfo.opw/floodinfo_docs/Eastern_CFRAM/_UOM09/01_Hydrology/Liffey_Hydrology_Report_HA09.pdf
- Hydraulics: https://s3-eu-west-1.amazonaws.com/docs.floodinfo.opw/floodinfo_docs/Eastern_CFRAM/_UOM09/02_Hydraulics/IBE0600Rp0027_HA09_Hydraulics_Report_F06.pdf
- Use: Lower Liffey model context, Qmed and design flows from Appendix D Model 2C, in-bank Manning n=0.04, and NE_19 coastal design levels from Table 4.7.2. Exact values and assumptions are in `content/flood-scenarios.json` and the generated manifest.
- Restriction: the OPW catalogue lists CFRAM/NIFM river extent and depth datasets as CC BY-NC-ND. This project does not copy, alter, or redistribute those layers. It links to official information and independently computes reduced-model scenarios from cited boundary parameters.

## Marine Institute tide predictions

- Dataset: `IMI_TidePrediction_HighLow`, station `Dublin_Port`, 14–18 January 2027 high/low predictions in OD Malin.
- Source: https://erddap.marine.ie/erddap/tabledap/IMI_TidePrediction_HighLow.html
- Licence: CC BY 4.0.
- Use: representative 12.42-hour tidal cycle for the scenario boundary. A prescribed residual matches published OPW extreme coastal peaks; the model does not independently predict surge or seiching.

## OpenStreetMap — Liffey and streets

- Source: OpenStreetMap ways obtained through Overpass API and transformed to ITM.
- Licence/credit: © OpenStreetMap contributors, ODbL 1.0; https://www.openstreetmap.org/copyright
- Use: Liffey centreline and street context/exposure. The distributed `static/generated/flood/streets.geojson` and `river.geojson` derivatives remain under ODbL. Street summaries use a 0.05 m modelled-depth threshold and are not observed closures.

The flood outputs are educational design scenarios, not live forecasts, official flood zones, formal validation products, or property-level risk assessments. The model simplifies channel geometry, tidal attenuation, momentum, floodplain storage, drainage, structures, and defences. Version 1.1 adds a conceptual volume-conserving reservoir router and prescribed coastal-timing sensitivity experiments using the same open inputs. Their dimensions, release rules, and time shifts are hypothetical: they do not represent ESB operations, observed reservoir releases, or storm-surge forecasts. Future extensions and their data requirements are listed on the project page.
