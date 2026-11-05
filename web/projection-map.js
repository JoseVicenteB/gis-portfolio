import {
  geoEqualEarth,
  geoGraticule10,
  geoMercator,
  geoPath,
  json,
  select,
  zoom,
  zoomIdentity,
} from "d3";
import { geoRobinson } from "d3-geo-projection";

const explorer = document.querySelector("[data-projection-explorer]");

if (explorer) {
  const map = explorer.querySelector("[data-live-map]");
  const svg = select(explorer.querySelector("svg"));
  const fallback = explorer.querySelector("[data-map-fallback]");
  const loading = explorer.querySelector("[data-map-loading]");
  const controls = explorer.querySelector("[data-map-controls]");
  const tooltip = explorer.querySelector("[data-country-tooltip]");
  const status = explorer.querySelector("[data-projection-status]");
  const mapTitle = explorer.querySelector("[data-map-title]");
  const mapCode = explorer.querySelector("[data-map-code]");
  const zoomLevel = explorer.querySelector("[data-zoom-level]");
  const tabs = Array.from(explorer.querySelectorAll('[role="tab"]'));
  const notes = Array.from(explorer.querySelectorAll("[data-projection-note]"));
  const configurations = JSON.parse(explorer.querySelector("[data-projection-config]").textContent);
  const factories = {
    "equal-earth": geoEqualEarth,
    "web-mercator": geoMercator,
    robinson: geoRobinson,
  };
  const sphere = { type: "Sphere" };
  let countries;
  let projection;
  let path;
  let currentId = configurations[0].id;
  let currentTransform = zoomIdentity;
  let width = 0;
  let height = 0;

  const mapLayer = svg.append("g").attr("class", "live-map-layer");
  const spherePath = mapLayer.append("path").attr("class", "live-map-sphere");
  const graticulePath = mapLayer.append("path").attr("class", "live-map-graticule");
  const countryLayer = mapLayer.append("g").attr("class", "live-map-countries");

  const zoomBehavior = zoom()
    .scaleExtent([1, 10])
    .on("zoom", event => {
      currentTransform = event.transform;
      mapLayer.attr("transform", currentTransform);
      zoomLevel.textContent = `${currentTransform.k.toFixed(1)}×`;
    });

  svg.call(zoomBehavior);

  const hideTooltip = () => {
    tooltip.hidden = true;
  };

  const drawCountries = () => {
    const paths = countryLayer
      .selectAll("path")
      .data(countries.features, feature => feature.properties.name)
      .join("path")
      .attr("class", "live-map-country")
      .attr("d", path)
      .attr("aria-hidden", "true");

    paths
      .on("pointerenter", (event, feature) => {
        tooltip.textContent = feature.properties.name;
        tooltip.hidden = false;
      })
      .on("pointermove", event => {
        const bounds = map.getBoundingClientRect();
        const x = Math.min(Math.max(event.clientX - bounds.left + 14, 8), bounds.width - 170);
        const y = Math.min(Math.max(event.clientY - bounds.top + 14, 8), bounds.height - 45);
        tooltip.style.left = `${x}px`;
        tooltip.style.top = `${y}px`;
      })
      .on("pointerleave", hideTooltip);
  };

  const render = (resetZoom = false) => {
    width = map.clientWidth;
    height = map.clientHeight;
    if (!width || !height || !countries) return;

    projection = factories[currentId]();
    projection.fitExtent([[18, 18], [width - 18, height - 18]], sphere);
    path = geoPath(projection);
    svg.attr("viewBox", `0 0 ${width} ${height}`);
    zoomBehavior
      .extent([[0, 0], [width, height]])
      .translateExtent([[0, 0], [width, height]]);

    spherePath.datum(sphere).attr("d", path);
    graticulePath.datum(geoGraticule10()).attr("d", path);
    drawCountries();
    if (resetZoom) svg.call(zoomBehavior.transform, zoomIdentity);
  };

  const activateProjection = (id, options = {}) => {
    const configuration = configurations.find(item => item.id === id);
    if (!configuration || !factories[id]) return;
    currentId = id;
    tabs.forEach(tab => {
      const selected = tab.dataset.projection === id;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
    });
    notes.forEach(note => {
      note.hidden = note.dataset.projectionNote !== id;
    });
    mapTitle.textContent = configuration.name;
    mapCode.textContent = `${configuration.property} · ${configuration.code}`;
    svg.select("title").text(`Interactive world map in the ${configuration.name} projection`);
    svg.select("desc").text("Drag to pan, scroll or pinch to zoom, or use the zoom buttons. Arrow keys pan and plus or minus zoom when the map is focused.");
    status.textContent = `${configuration.name} projection selected. ${configuration.property}.`;
    render(true);
    hideTooltip();
    if (options.focus) explorer.querySelector(`[data-projection="${id}"]`).focus();
    if (options.hash) history.replaceState(null, "", `#projection-${id}`);
  };

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activateProjection(tab.dataset.projection, { hash: true }));
    tab.addEventListener("keydown", event => {
      let nextIndex;
      if (event.key === "ArrowRight") nextIndex = (index + 1) % tabs.length;
      if (event.key === "ArrowLeft") nextIndex = (index - 1 + tabs.length) % tabs.length;
      if (event.key === "Home") nextIndex = 0;
      if (event.key === "End") nextIndex = tabs.length - 1;
      if (nextIndex !== undefined) {
        event.preventDefault();
        activateProjection(tabs[nextIndex].dataset.projection, { focus: true, hash: true });
      }
    });
  });

  explorer.querySelector('[data-map-action="in"]').addEventListener("click", () => {
    svg.call(zoomBehavior.scaleBy, 1.6);
  });
  explorer.querySelector('[data-map-action="out"]').addEventListener("click", () => {
    svg.call(zoomBehavior.scaleBy, 1 / 1.6);
  });
  explorer.querySelector('[data-map-action="reset"]').addEventListener("click", () => {
    svg.call(zoomBehavior.transform, zoomIdentity);
    status.textContent = "Map zoom and position reset.";
  });

  svg.on("keydown", event => {
    const actions = {
      "+": () => svg.call(zoomBehavior.scaleBy, 1.4),
      "=": () => svg.call(zoomBehavior.scaleBy, 1.4),
      "-": () => svg.call(zoomBehavior.scaleBy, 1 / 1.4),
      "0": () => svg.call(zoomBehavior.transform, zoomIdentity),
      ArrowLeft: () => svg.call(zoomBehavior.translateBy, 40 / currentTransform.k, 0),
      ArrowRight: () => svg.call(zoomBehavior.translateBy, -40 / currentTransform.k, 0),
      ArrowUp: () => svg.call(zoomBehavior.translateBy, 0, 40 / currentTransform.k),
      ArrowDown: () => svg.call(zoomBehavior.translateBy, 0, -40 / currentTransform.k),
    };
    if (actions[event.key]) {
      event.preventDefault();
      actions[event.key]();
    }
  });

  const initialize = async () => {
    try {
      countries = await json(map.dataset.geojsonUrl);
      fallback.hidden = true;
      explorer.querySelector("svg").removeAttribute("hidden");
      controls.hidden = false;
      loading.hidden = true;
      explorer.classList.add("is-ready");
      const requested = window.location.hash.replace("#projection-", "");
      activateProjection(configurations.some(item => item.id === requested) ? requested : currentId);
      new ResizeObserver(() => render(false)).observe(map);
    } catch (error) {
      fallback.hidden = false;
      explorer.querySelector("svg").setAttribute("hidden", "");
      controls.hidden = true;
      explorer.classList.remove("is-ready");
      loading.textContent = "The interactive map could not load. The static map remains available.";
      loading.hidden = false;
      console.error("Projection map initialization failed", error);
    }
  };

  initialize();
}
