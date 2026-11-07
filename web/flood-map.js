import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const explorer = document.querySelector("[data-flood-explorer]");

if (explorer) {
  const assets = explorer.dataset.assetsUrl.replace(/\/$/, "");
  const map = explorer.querySelector("[data-flood-map]");
  const fallback = explorer.querySelector("[data-flood-fallback]");
  const loading = explorer.querySelector("[data-flood-loading]");
  const scenarioSelect = explorer.querySelector("[data-flood-scenario]");
  const scenarioNote = explorer.querySelector("[data-flood-scenario-note]");
  const storageRow = explorer.querySelector("[data-flood-storage-row]");
  const storageLabel = explorer.querySelector("[data-flood-storage]");
  const releaseRow = explorer.querySelector("[data-flood-release-row]");
  const releaseLabel = explorer.querySelector("[data-flood-release]");
  const playButton = explorer.querySelector('[data-flood-action="play"]');
  const timeline = explorer.querySelector("[data-flood-timeline]");
  const timeLabel = explorer.querySelector("[data-flood-time]");
  const speedSelect = explorer.querySelector("[data-flood-speed]");
  const areaLabel = explorer.querySelector("[data-flood-area]");
  const roadsLabel = explorer.querySelector("[data-flood-roads]");
  const depthLabel = explorer.querySelector("[data-flood-depth]");
  const status = explorer.querySelector("[data-flood-status]");
  const chart = explorer.querySelector("[data-flood-chart]");
  const labels = [];
  const textureCache = new Map();
  let manifest;
  let renderer;
  let scene;
  let camera;
  let controls;
  let water;
  let streets;
  let terrainGeometry;
  let elevations;
  let currentScenario;
  let currentFrame = 0;
  let playing = false;
  let speed = 1;
  let lastAdvance = 0;
  let updateToken = 0;
  let roadSegmentIds = [];
  let roadColors;
  let width = 0;
  let height = 0;

  const asset = path => `${assets}/${path}`;
  const scenario = () => manifest.scenarios.find(item => item.id === currentScenario);
  const frame = () => scenario().frames[currentFrame];

  const announce = message => {
    status.textContent = message;
  };

  const terrainHeight = (x, y) => {
    const [left, bottom, right, top] = manifest.bounds;
    const column = Math.max(0, Math.min(manifest.grid.columns - 1, Math.floor((x - left) / manifest.grid.resolution_m)));
    const row = Math.max(0, Math.min(manifest.grid.rows - 1, Math.floor((top - y) / manifest.grid.resolution_m)));
    const value = elevations[row * manifest.grid.columns + column];
    return (value / 65535 * (manifest.terrain.maximum_m - manifest.terrain.minimum_m) + manifest.terrain.minimum_m) * manifest.vertical_exaggeration;
  };

  const mapPosition = (x, y, offset = 0) => {
    const [left, bottom, right, top] = manifest.bounds;
    return new THREE.Vector3(
      x - (left + right) / 2,
      y - (bottom + top) / 2,
      terrainHeight(x, y) + offset,
    );
  };

  const loadDepthTexture = async (scenarioId, frameIndex) => {
    const key = `${scenarioId}/${frameIndex}`;
    if (textureCache.has(key)) return textureCache.get(key);
    const selected = manifest.scenarios.find(item => item.id === scenarioId);
    const record = selected.frames[frameIndex];
    const image = new Image();
    image.src = asset(record.file);
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = manifest.grid.columns;
    canvas.height = manifest.grid.rows;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    context.drawImage(image, 0, 0);
    const rgba = context.getImageData(0, 0, canvas.width, canvas.height).data;
    const values = new Uint8Array(canvas.width * canvas.height);
    for (let index = 0; index < values.length; index += 1) values[index] = rgba[index * 4];
    const texture = new THREE.DataTexture(
      values,
      canvas.width,
      canvas.height,
      THREE.RedFormat,
      THREE.UnsignedByteType,
    );
    texture.minFilter = THREE.LinearFilter;
    texture.magFilter = THREE.LinearFilter;
    texture.needsUpdate = true;
    textureCache.set(key, texture);
    return texture;
  };

  const updateRoadColors = () => {
    if (!streets || !roadColors) return;
    const affected = frame().road_depths;
    const base = new THREE.Color("#44635c");
    const shallow = new THREE.Color("#f2a65a");
    const deep = new THREE.Color("#d9573f");
    roadSegmentIds.forEach((id, index) => {
      const depth = affected[id] || 0;
      const color = depth ? shallow.clone().lerp(deep, Math.min(depth / 2.5, 1)) : base;
      roadColors[index * 3] = color.r;
      roadColors[index * 3 + 1] = color.g;
      roadColors[index * 3 + 2] = color.b;
    });
    streets.geometry.attributes.color.needsUpdate = true;
  };

  const drawChart = () => {
    const frames = scenario().frames;
    const svgNS = "http://www.w3.org/2000/svg";
    chart.replaceChildren();
    const make = (name, attributes) => {
      const element = document.createElementNS(svgNS, name);
      Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
      return element;
    };
    const x = hour => 30 + hour / 48 * 232;
    const maxFlow = Math.max(...frames.map(item => item.downstream_flow_m3s));
    const maxCoast = Math.max(...frames.map(item => item.coastal_level_m));
    const minCoast = Math.min(...frames.map(item => item.coastal_level_m));
    const flowY = value => 79 - value / maxFlow * 55;
    const coastY = value => 79 - (value - minCoast) / (maxCoast - minCoast) * 55;
    [24, 79].forEach(y => chart.append(make("line", { x1: 30, x2: 262, y1: y, y2: y, class: "flood-chart-grid" })));
    const path = (key, scale) => frames.map((item, index) => `${index ? "L" : "M"}${x(item.hour).toFixed(1)},${scale(item[key]).toFixed(1)}`).join(" ");
    chart.append(make("path", { d: path("downstream_flow_m3s", flowY), class: "flood-chart-flow" }));
    chart.append(make("path", { d: path("coastal_level_m", coastY), class: "flood-chart-coast" }));
    const addText = (attributes, value) => {
      const element = make("text", attributes);
      element.textContent = value;
      chart.append(element);
    };
    addText({ x: 30, y: 14, class: "flood-chart-label" }, `Flow 0–${Math.round(maxFlow)} m³/s`);
    addText({ x: 262, y: 14, "text-anchor": "end", class: "flood-chart-label" }, `Coast ${minCoast.toFixed(1)}–${maxCoast.toFixed(1)} m`);
    [0, 24, 48].forEach(hour => {
      addText({ x: x(hour), y: 98, "text-anchor": "middle", class: "flood-chart-label" }, `T+${hour}`);
    });
    const marker = make("line", { x1: x(frame().hour), x2: x(frame().hour), y1: 22, y2: 80, class: "flood-chart-marker" });
    marker.dataset.floodChartMarker = "";
    chart.append(marker);
  };

  const updateInterface = () => {
    const record = frame();
    const selected = scenario();
    timeline.value = String(currentFrame);
    timeLabel.textContent = `T+${String(record.hour).padStart(2, "0")}:00`;
    areaLabel.textContent = `${record.wet_area_km2.toFixed(2)} km²`;
    roadsLabel.textContent = `${record.affected_road_km.toFixed(1)} km`;
    depthLabel.textContent = `${record.max_depth_m.toFixed(2)} m`;
    scenarioNote.textContent = selected.description || `Baseline ${selected.label} design event with prescribed river and coastal peaks at the same scenario hour.`;
    const reservoir = selected.kind === "reservoir";
    storageRow.hidden = !reservoir;
    releaseRow.hidden = !reservoir;
    if (reservoir) {
      storageLabel.textContent = `${(record.reservoir_storage_m3 / 1000000).toFixed(2)} million m³`;
      releaseLabel.textContent = `${record.reservoir_release_m3s.toFixed(1)} m³/s`;
    }
    const marker = chart.querySelector("[data-flood-chart-marker]");
    if (marker) {
      const x = 30 + record.hour / 48 * 232;
      marker.setAttribute("x1", x);
      marker.setAttribute("x2", x);
    }
    updateRoadColors();
  };

  const setFrame = async index => {
    currentFrame = Math.max(0, Math.min(scenario().frames.length - 1, index));
    updateInterface();
    const token = ++updateToken;
    const texture = await loadDepthTexture(currentScenario, currentFrame);
    if (token !== updateToken || !water) return;
    water.material.uniforms.depthMap.value = texture;
    const next = (currentFrame + 1) % scenario().frames.length;
    loadDepthTexture(currentScenario, next).catch(() => {});
  };

  const setPlaying = value => {
    playing = value;
    playButton.textContent = playing ? "Pause" : "Play";
    playButton.setAttribute("aria-pressed", String(playing));
    announce(playing ? `${scenario().label} animation playing.` : `${scenario().label} animation paused at T+${frame().hour} hours.`);
    lastAdvance = performance.now();
  };

  const cameraView = top => {
    camera.position.set(top ? 0 : -6500, top ? -900 : -7600, top ? 14000 : 6500);
    controls.target.set(0, 0, 300);
    controls.update();
  };

  const createStreets = data => {
    const positions = [];
    roadSegmentIds = [];
    data.features.forEach(feature => {
      const geometry = feature.geometry;
      const lines = geometry.type === "LineString" ? [geometry.coordinates] : geometry.coordinates;
      lines.forEach(line => {
        for (let index = 1; index < line.length; index += 1) {
          const start = mapPosition(line[index - 1][0], line[index - 1][1], 1.4);
          const end = mapPosition(line[index][0], line[index][1], 1.4);
          positions.push(start.x, start.y, start.z, end.x, end.y, end.z);
          roadSegmentIds.push(feature.id, feature.id);
        }
      });
    });
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    roadColors = new Float32Array(roadSegmentIds.length * 3);
    geometry.setAttribute("color", new THREE.BufferAttribute(roadColors, 3));
    const material = new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.82 });
    streets = new THREE.LineSegments(geometry, material);
    scene.add(streets);
  };

  const createLabels = () => {
    const layer = explorer.querySelector("[data-flood-labels]");
    manifest.landmarks.forEach(landmark => {
      const element = document.createElement("span");
      element.textContent = landmark.name;
      element.className = "flood-map-label";
      layer.append(element);
      labels.push({ element, position: mapPosition(landmark.coordinates[0], landmark.coordinates[1], 30) });
    });
  };

  const updateLabels = () => {
    labels.forEach(label => {
      const point = label.position.clone().project(camera);
      const visible = point.z < 1 && point.x > -0.95 && point.x < 0.95 && point.y > -0.9 && point.y < 0.9;
      label.element.hidden = !visible;
      if (visible) {
        label.element.style.left = `${(point.x + 1) / 2 * width}px`;
        label.element.style.top = `${(-point.y + 1) / 2 * height}px`;
      }
    });
  };

  const resize = () => {
    if (!renderer || !camera) return;
    width = map.clientWidth;
    height = map.clientHeight;
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  };

  const initializeScene = async () => {
    scene = new THREE.Scene();
    scene.background = new THREE.Color("#dcebe7");
    camera = new THREE.PerspectiveCamera(38, 1, 2, 50000);
    camera.up.set(0, 0, 1);
    renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.domElement.tabIndex = 0;
    renderer.domElement.setAttribute("role", "img");
    renderer.domElement.setAttribute("aria-label", "Interactive 3D Lower Liffey terrain and simulated flooding. Use the nearby buttons and timeline to explore.");
    map.prepend(renderer.domElement);
    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.minDistance = 600;
    controls.maxDistance = 25000;
    controls.maxPolarAngle = Math.PI / 2.08;
    controls.listenToKeyEvents(renderer.domElement);
    cameraView(false);
    scene.add(new THREE.HemisphereLight("#f5f4df", "#4b675d", 2.1));
    const sunlight = new THREE.DirectionalLight("#fff4df", 2.4);
    sunlight.position.set(-5000, -6000, 10000);
    scene.add(sunlight);
    const [terrainBuffer, terrainTexture, streetData] = await Promise.all([
      fetch(asset(manifest.terrain.file)).then(response => {
        if (!response.ok) throw new Error("Terrain elevation could not be loaded");
        return response.arrayBuffer();
      }),
      new THREE.TextureLoader().loadAsync(asset(manifest.terrain.texture)),
      fetch(asset(manifest.streets_file)).then(response => {
        if (!response.ok) throw new Error("Street geometry could not be loaded");
        return response.json();
      }),
    ]);
    elevations = new Uint16Array(terrainBuffer);
    const { rows, columns } = manifest.grid;
    terrainGeometry = new THREE.PlaneGeometry(manifest.width_m, manifest.height_m, columns - 1, rows - 1);
    const positions = terrainGeometry.attributes.position;
    for (let index = 0; index < positions.count; index += 1) {
      positions.setZ(index, (elevations[index] / 65535 * (manifest.terrain.maximum_m - manifest.terrain.minimum_m) + manifest.terrain.minimum_m) * manifest.vertical_exaggeration);
    }
    terrainGeometry.computeVertexNormals();
    terrainTexture.colorSpace = THREE.SRGBColorSpace;
    terrainTexture.anisotropy = Math.min(renderer.capabilities.getMaxAnisotropy(), 8);
    const terrain = new THREE.Mesh(
      terrainGeometry,
      new THREE.MeshStandardMaterial({ map: terrainTexture, side: THREE.DoubleSide, alphaTest: 0.05 }),
    );
    scene.add(terrain);
    const waterMaterial = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      uniforms: {
        depthMap: { value: null },
        depthMaximum: { value: manifest.depth_encoding_max_m },
        exaggeration: { value: manifest.vertical_exaggeration },
      },
      vertexShader: `
        uniform sampler2D depthMap;
        uniform float depthMaximum;
        uniform float exaggeration;
        varying float vDepth;
        void main() {
          float depth = texture2D(depthMap, vec2(uv.x, 1.0 - uv.y)).r * depthMaximum;
          vDepth = depth;
          vec3 displaced = position;
          displaced.z += depth * exaggeration + 0.45;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(displaced, 1.0);
        }
      `,
      fragmentShader: `
        varying float vDepth;
        void main() {
          if (vDepth < 0.025) discard;
          float amount = clamp(vDepth / 3.5, 0.0, 1.0);
          vec3 shallow = vec3(0.35, 0.76, 0.86);
          vec3 deep = vec3(0.025, 0.16, 0.36);
          gl_FragColor = vec4(mix(shallow, deep, amount), mix(0.62, 0.88, amount));
        }
      `,
    });
    water = new THREE.Mesh(terrainGeometry.clone(), waterMaterial);
    water.renderOrder = 2;
    scene.add(water);
    createStreets(streetData);
    createLabels();
    currentScenario = manifest.default_scenario;
    currentFrame = scenario().peak_frame;
    drawChart();
    await setFrame(currentFrame);
    resize();
    new ResizeObserver(resize).observe(map);
    fallback.hidden = true;
    loading.hidden = true;
    explorer.classList.add("is-ready");
    updateInterface();
    const animate = now => {
      requestAnimationFrame(animate);
      if (!width || !height) {
        resize();
        return;
      }
      if (playing && now - lastAdvance > 1000 / speed) {
        const next = currentFrame + 1 >= scenario().frames.length ? 0 : currentFrame + 1;
        setFrame(next);
        lastAdvance = now;
      }
      controls.update();
      updateLabels();
      renderer.render(scene, camera);
    };
    requestAnimationFrame(animate);
  };

  scenarioSelect.addEventListener("change", async () => {
    currentScenario = scenarioSelect.value;
    currentFrame = Math.min(currentFrame, scenario().frames.length - 1);
    drawChart();
    await setFrame(currentFrame);
    announce(`${scenario().label} selected. ${scenario().description || `Approximately 1 in ${scenario().return_period_years} annual exceedance probability.`}`);
  });
  playButton.addEventListener("click", () => {
    if (!playing && currentFrame === scenario().frames.length - 1) setFrame(0);
    setPlaying(!playing);
  });
  timeline.addEventListener("input", () => {
    setPlaying(false);
    setFrame(Number(timeline.value));
  });
  speedSelect.addEventListener("change", () => { speed = Number(speedSelect.value); });
  explorer.querySelector('[data-flood-action="reset"]').addEventListener("click", () => cameraView(false));
  explorer.querySelector('[data-flood-action="top"]').addEventListener("click", () => cameraView(true));
  explorer.querySelector("[data-flood-water-toggle]").addEventListener("change", event => {
    if (water) water.visible = event.target.checked;
  });
  explorer.querySelector("[data-flood-streets-toggle]").addEventListener("change", event => {
    if (streets) streets.visible = event.target.checked;
  });
  document.querySelectorAll('[role="tab"]').forEach(tab => tab.addEventListener("click", () => setTimeout(resize, 50)));

  const initialize = async () => {
    try {
      const response = await fetch(asset("manifest.json"));
      if (!response.ok) throw new Error("Flood model manifest could not be loaded");
      manifest = await response.json();
      timeline.max = String(manifest.scenarios[0].frames.length - 1);
      await initializeScene();
    } catch (error) {
      fallback.hidden = false;
      loading.hidden = false;
      loading.textContent = "The 3D model could not load. The static peak-scenario map remains available.";
      explorer.classList.remove("is-ready");
      console.error("Flood explorer initialization failed", error);
    }
  };
  initialize();
}
