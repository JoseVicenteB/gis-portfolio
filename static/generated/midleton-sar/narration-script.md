# Midleton SAR Flood Response — 2:30 narration script

Target: approximately 120–125 words per minute. Record each segment separately and place it at the stated timecode. The edited MP4 is silent; add the voice-over later without changing the visual timings.

## 0:00–0:15 — Storm Babet context

Storm Babet brought prolonged heavy rain to Cork on 17 and 18 October 2023. In Midleton, the Dungourney and Owenacurra rivers overtopped, flooding homes and businesses and forcing evacuations. The N25 station recorded 103.2 millimetres.

## 0:15–0:25 — Project result

This project maps the late-stage event using Sentinel-1 and rainfall radar, reporting 3.409 square kilometres of detected new inundation in 803 regions.

## 0:25–0:45 — SAR processing and timing

I compared an 18 October acquisition, at 18:15 UTC, with a same-orbit median baseline from 19 August, 24 September and 6 October. After orbit and noise correction, calibration, Refined Lee filtering and terrain correction, I calculated event-minus-baseline VV change. This is a receding-stage snapshot.

## 0:45–1:00 — Rainfall analysis

The rainfall workflow checks 42 complete hourly Met Éireann accumulations. The study-area mean is 33.1 millimetres. That radar average is deliberately not forced to agree with the 103.2 millimetre point-gauge total.

## 1:00–1:20 — Detection and candidate review

Candidates require event VV of minus 14 decibels or less, and a VV drop of at least four decibels. Permanent water, steep slopes, invalid geometry and layover or shadow are excluded, followed by an eight-pixel minimum-region cleanup. Candidate review then examines plausible false positives and missed flooding.

## 1:20–1:35 — Sensitivity and validation

Sensitivity experiments vary thresholds, masks, region size, baseline composition and Lee filter windows. Because there is no independent open reference extent, this remains qualitative evaluation: precision, recall and IoU are not claimed.

## 1:35–1:55 — Interactive web GIS

The native Leaflet viewer makes the evidence inspectable. Switch between terrain, baseline, event and change, then compare permanent water, candidates and cleaned detections. Popups report area, backscatter, slope and subcatchment rainfall with explicit units.

## 1:55–2:10 — Precomputed delivery

All web assets are precomputed and local. The portfolio makes no live GIS-service calls, works at a GitHub Pages subpath, and keeps attribution and limitations beside the map.

## 2:10–2:30 — Reproducibility and responsible use

The GeoPackage, event card, source manifest and QA summaries provide reproducible evidence. This is historical research: a later-stage radar response, not a validated extent, depth product or official warning map, and not for emergency or property-level decisions.

## Context sources

- Cork County Council / Arup, *Midleton Flood Relief Scheme — Storm Babet Flood Event Report, Draft 2* (22 December 2023): https://www.floodinfo.ie/frs/media/filer_public/5b/1f/5b1f191c-52a2-428b-b419-6704c3940628/252803_storm_babet_flood_event_report_draft_v2_part1.pdf
- RTÉ News, *Midleton firms count the cost of Babet one month on* (19 November 2023): https://www.rte.ie/news/regional/2023/1119/1417314-midleton-flooding/
