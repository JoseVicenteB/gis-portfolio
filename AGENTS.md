# Project guidance

## Deployment strategy

This portfolio deploys **precomputed GIS web assets**. Routine deployments must not download raw geospatial data or rerun GIS analysis.

- `static/generated/` is intentionally version-controlled. Treat its map images, GeoJSON, statistics, and downloadable derivatives as reviewed build inputs.
- `data/raw/` remains local and ignored. Never require raw data in the deployment environment.
- `dist/` is generated during deployment and remains ignored.
- Do not add `portfolio-maps`, remote GIS downloads, or remote raster reads to `.github/workflows/deploy.yml` unless the user explicitly requests a data-refreshing deployment.
- Routine deployment runs `npm ci`, `npm run build`, installs the Python project, and runs `portfolio-build`. The workflow then publishes `dist/` to GitHub Pages.
- If a required generated asset is missing, regenerate it locally with `portfolio-maps`, inspect the output, and include it with the source changes. Do not silently make deployment fetch source data as a fallback.

## Changing maps

Run `portfolio-maps` locally only when source data, GIS code, cartography, or map content intentionally changes. Review the generated media and statistics, then commit the updated files under `static/generated/` together with the corresponding code/content changes. Preserve dataset attribution and limitations.

For content-only changes, run `portfolio-build` without regenerating maps. For changes to `web/projection-map.js`, run `npm ci` once if needed and `npm run build`; keep the bundled `static/js/projection-map.js` with the site.

## Verification

Before finishing changes, run the relevant JavaScript and Python builds and verify the generated site in the browser. Check map interactions after changing the renderer, and confirm internal links, generated assets, and GitHub Pages subpath URLs. Do not publish or commit unless the user asks.
