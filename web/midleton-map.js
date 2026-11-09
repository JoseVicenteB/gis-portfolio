import * as L from "leaflet";
import "leaflet/dist/leaflet.css";

const explorer = document.querySelector("[data-midleton-explorer]");

if (explorer) {
  const assets = explorer.dataset.assetsUrl.replace(/\/$/, "");
  const container = explorer.querySelector("[data-midleton-map]");
  const mapFrame = explorer.querySelector("[data-midleton-map-frame]");
  const fallback = explorer.querySelector("[data-midleton-fallback]");
  const loading = explorer.querySelector("[data-midleton-loading]");
  const status = explorer.querySelector("[data-midleton-status]");
  const asset = path => `${assets}/${path}`;
  const number = (value, digits = 2) => value === null || value === undefined ? "Not computed" : Number(value).toFixed(digits);

  const loadJson = async path => {
    const response = await fetch(asset(path));
    if (!response.ok) throw new Error(`Map asset could not be loaded: HTTP ${response.status}`);
    return response.json();
  };

  const popup = (properties, fields) => {
    const table = document.createElement("table");
    fields.filter(([, key]) => properties[key] !== null && properties[key] !== undefined).forEach(([label, key, digits]) => {
      const row = table.insertRow();
      const name = row.insertCell();
      const value = row.insertCell();
      name.textContent = label;
      const strong = document.createElement("strong");
      strong.textContent = digits === undefined ? String(properties[key]) : number(properties[key], digits);
      value.append(strong);
    });
    return table;
  };

  const initialize = async () => {
    try {
      const overlays = await loadJson("assets/overlays.json");
      const map = L.map(container, {
        preferCanvas: true,
        zoomControl: true,
        attributionControl: false,
        maxZoom: 17,
        zoomSnap: 0.25,
        zoomDelta: 0.5,
      });
      map.createPane("midleton-rasters");
      map.getPane("midleton-rasters").style.zIndex = 350;
      map.createPane("midleton-rainfall");
      map.getPane("midleton-rainfall").style.zIndex = 360;
      map.createPane("midleton-vectors");
      map.getPane("midleton-vectors").style.zIndex = 450;
      const vectorRenderer = L.canvas({ pane: "midleton-vectors", padding: 0.2 });
      const bounds = key => [overlays[key].bounds.slice(0, 2), overlays[key].bounds.slice(2, 4)];
      const image = key => L.imageOverlay(asset(overlays[key].file), bounds(key), {
        pane: key === "rainfall" ? "midleton-rainfall" : "midleton-rasters",
      });
      const baseLayers = {
        "Terrain / hillshade": image("terrain").addTo(map),
        "SAR baseline VV": image("baseline"),
        "SAR event VV": image("event"),
        "SAR event − baseline (dB)": image("delta"),
      };
      const styles = {
        flood: { color: "#075ca8", weight: 1.5, fillColor: "#075ca8", fillOpacity: 0.68 },
        candidates: { color: "#d7794a", weight: 0.7, fillColor: "#d7794a", fillOpacity: 0.3 },
        water: { color: "#397f98", weight: 0.5, fillColor: "#8bc6d9", fillOpacity: 0.7 },
        catchments: { color: "#56796d", weight: 1, dashArray: "5 4", fill: false },
        review: { color: "#d7794a", weight: 2, fillColor: "#d7794a", fillOpacity: 0.05 },
        roads: { color: "#354a45", weight: 1.2, opacity: 0.65 },
        study: { color: "#18332f", weight: 1.2, fill: false, dashArray: "3 3" },
      };
      const vector = async (name, style, fields) => {
        const data = await loadJson(`assets/${name}.geojson`);
        return L.geoJSON(data, {
          pane: "midleton-vectors",
          renderer: vectorRenderer,
          style: styles[style],
          onEachFeature: (feature, layer) => {
            if (fields) layer.bindPopup(popup(feature.properties, fields), { maxWidth: 360 });
          },
        });
      };
      const [flood, candidates, water, catchments, review, roads, study] = await Promise.all([
        vector("flood_extent", "flood", [["Area (ha)", "area_ha", 3], ["Mean ΔVV (dB)", "mean_delta_vv_db", 2], ["Mean event VV (dB)", "mean_event_vv_db", 2], ["Mean baseline VV (dB)", "mean_baseline_vv_db", 2], ["Evidence", "evidence"], ["Mean slope (degrees)", "mean_slope_degrees", 1]]),
        vector("flood_candidates", "candidates", [["Candidate area (ha)", "area_ha", 3]]),
        vector("permanent_water", "water", [["Name", "name"], ["Type", "feature_class"], ["Source", "source"]]),
        vector("subcatchments", "catchments", [["Subcatchment", "Name"], ["Subcatchment ID", "Subcatchment_Id"], ["Radar mean (mm)", "radar_event_mean_mm", 1], ["Radar maximum (mm)", "radar_event_max_mm", 1], ["Peak hourly maximum (mm)", "radar_peak_1h_max_mm", 1], ["Radar provider", "radar_provider"]]),
        vector("error_analysis", "review", [["Candidate", "candidate_id"], ["Status", "status"], ["Evidence", "evidence"], ["Review", "notes"]]),
        vector("roads", "roads", [["Road", "name"], ["Road class", "feature_class"], ["OpenStreetMap ID", "osm_id"]]),
        vector("study_area", "study", [["Study area", "name"], ["Area (km²)", "area_km2", 1]]),
      ]);
      const rainfall = image("rainfall");
      const overlayLayers = {
        "Detected new inundation": flood.addTo(map),
        "Rainfall accumulation (mm)": rainfall,
        "Permanent water": water.addTo(map),
        "EPA subcatchments / rainfall": catchments.addTo(map),
        "Unfiltered candidates": candidates,
        "Qualitative review polygons": review,
        "Major roads": roads.addTo(map),
        "Study boundary": study,
      };
      L.control.layers(baseLayers, overlayLayers, { collapsed: mapFrame.clientWidth < 600 }).addTo(map);
      L.control.scale({ imperial: false, position: "bottomleft" }).addTo(map);
      const legend = L.control({ position: "bottomright" });
      legend.onAdd = () => {
        const element = L.DomUtil.create("div", "midleton-legend");
        element.innerHTML = '<h3>MAP KEY</h3><div><span class="midleton-swatch flood"></span>Detected new inundation</div><div><span class="midleton-swatch candidates"></span>Unfiltered candidate / review</div><div><span class="midleton-swatch water"></span>Permanent water</div><div><span class="midleton-line catchments"></span>EPA subcatchment</div><div><span class="midleton-line roads"></span>Major road</div><p data-midleton-raster-key></p>';
        return element;
      };
      legend.addTo(map);
      let activeBase = "Terrain / hillshade";
      const rasterKey = explorer.querySelector("[data-midleton-raster-key]");
      const updateRasterKey = () => {
        const descriptions = {
          "Terrain / hillshade": "Terrain: LiDAR-priority elevation blend with GLO-30 gap filling.",
          "SAR baseline VV": `Baseline σ⁰ VV (dB): three-scene median; display ${number(overlays.baseline.vmin, 2)} to ${number(overlays.baseline.vmax, 2)}.`,
          "SAR event VV": `Event σ⁰ VV (dB): 18 Oct 2023, 18:15 UTC; display ${number(overlays.event.vmin, 2)} to ${number(overlays.event.vmax, 2)}.`,
          "SAR event − baseline (dB)": `ΔVV = event − baseline (dB); display ${number(overlays.delta.vmin, 0)} to +${number(overlays.delta.vmax, 0)}.`,
        };
        const rainfallNote = map.hasLayer(rainfall) ? ` Rainfall overlay: accumulated precipitation (mm); display 0–${number(overlays.rainfall.vmax, 2)}.` : "";
        rasterKey.textContent = `${descriptions[activeBase]}${rainfallNote}`;
      };
      map.on("baselayerchange", event => {
        activeBase = event.name;
        updateRasterKey();
        status.textContent = `${event.name} base layer selected.`;
      });
      map.on("overlayadd overlayremove", event => {
        updateRasterKey();
        status.textContent = `${event.name} ${event.type === "overlayadd" ? "shown" : "hidden"}.`;
      });
      updateRasterKey();

      let hasVisibleFit = false;
      const resize = () => {
        map.invalidateSize({ pan: false });
        if (container.clientWidth && container.clientHeight && !hasVisibleFit) {
          map.fitBounds(bounds("terrain"), { padding: [8, 8] });
          hasVisibleFit = true;
        }
      };
      new ResizeObserver(resize).observe(mapFrame);
      document.querySelectorAll('[role="tab"]').forEach(tab => tab.addEventListener("click", () => {
        if (tab.getAttribute("aria-controls") === "maps") setTimeout(resize, 60);
      }));
      resize();
      fallback.hidden = true;
      loading.hidden = true;
      explorer.classList.add("is-ready");
      status.textContent = "Interactive Midleton map loaded with terrain, detected inundation, permanent water, EPA subcatchments, and major roads.";
      window.midletonMap = map;
      window.midletonLayers = { baseLayers, overlayLayers };
    } catch (error) {
      fallback.hidden = false;
      loading.hidden = false;
      loading.textContent = "The interactive map could not load. The static detected-extent map remains available.";
      explorer.classList.remove("is-ready");
      console.error("Midleton explorer initialization failed", error);
    }
  };

  initialize();
}
