from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path.cwd()
CONTENT = ROOT / "content"
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"
DIST = ROOT / "dist"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_projects() -> list[dict]:
    projects = []
    required = {"slug", "title", "summary", "hero", "maps", "methods", "data", "tags"}
    for path in CONTENT.joinpath("projects").glob("*.json"):
        project = load_json(path)
        missing = required - project.keys()
        if missing:
            raise ValueError(f"{path.name} is missing: {', '.join(sorted(missing))}")
        for image in [project["hero"], *(item["image"] for item in project["maps"])]:
            if not STATIC.joinpath(image).is_file():
                raise FileNotFoundError(f"Generate the required map first: static/{image}")
        if project.get("viewer") == "flood":
            for asset in ("manifest.json", "summary.json", "terrain.bin", "terrain.webp", "streets.geojson"):
                if not STATIC.joinpath("generated", "flood", asset).is_file():
                    raise FileNotFoundError(f"Generate the required flood asset first: static/generated/flood/{asset}")
        projects.append(project)
    projects.sort(key=lambda item: item.get("order", 999))
    slugs = [project["slug"] for project in projects]
    if len(slugs) != len(set(slugs)):
        raise ValueError("Project slugs must be unique")
    return projects


def add_statistics(projects: list[dict]) -> None:
    for project in projects:
        if project["slug"] == "dublin-liffey-flood":
            summary = load_json(STATIC / "generated" / "flood" / "summary.json")
            project["stats"] = [
                {"value": f'{summary["default_peak_wet_area_km2"]:.2f} km²', "label": "Peak connected land inundation · 1% AEP"},
                {"value": f'{summary["default_peak_affected_road_km"]:.1f} km', "label": "Streets above 0.05 m · model maximum"},
                {"value": str(summary["frame_count"]), "label": "Hourly frames per design scenario"},
            ]


def build(base_path: str = "") -> None:
    base_path = f'/{base_path.strip("/")}' if base_path.strip("/") else ""

    def url(path: str = "") -> str:
        if path.startswith(("http://", "https://", "mailto:", "#")):
            return path
        return f'{base_path}/{path.lstrip("/")}'

    def srcset(path: str) -> str:
        source = Path(path)
        preview = source.with_name(f"{source.stem}-960{source.suffix}")
        if not STATIC.joinpath(preview).is_file():
            return url(path)
        return f"{url(str(preview))} 960w, {url(path)} 1800w"

    environment = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=True,
        undefined=StrictUndefined,
    )
    environment.globals.update(url=url, srcset=srcset)

    site = load_json(CONTENT / "site.json")
    projects = load_projects()
    add_statistics(projects)
    context = {
        "site": site,
        "projects": projects,
        "featured": [project for project in projects if project.get("featured")],
        "tag_counts": {tag: sum(tag in project["tags"] for project in projects) for tag in ("Remote Sensing", "Cartography", "Python")},
        "year": datetime.now().year,
    }

    if DIST.exists():
        shutil.rmtree(DIST)
    shutil.copytree(STATIC, DIST)

    pages = (
        ("about.html", "index.html", "About", "About the GIS and remote sensing master's student behind this portfolio."),
        ("projects.html", "projects/index.html", "Projects", "Explore GIS, remote sensing, and cartography projects."),
        ("contact.html", "contact/index.html", "Contact", "Get in touch about GIS, remote sensing, and spatial analysis."),
    )
    for template_name, output_name, title, description in pages:
        output = DIST / output_name
        output.parent.mkdir(parents=True, exist_ok=True)
        html = environment.get_template(template_name).render(
            **context,
            page_title=title,
            page_description=description,
            active_page=title,
        )
        output.write_text(html, encoding="utf-8")

    project_template = environment.get_template("project.html")
    for project in projects:
        output = DIST / "projects" / project["slug"] / "index.html"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            project_template.render(
                **context,
                project=project,
                page_title=project["title"],
                page_description=project["summary"],
                active_page="Projects",
            ),
            encoding="utf-8",
        )
    print(f"Built {len(pages)} pages and {len(projects)} projects in dist/")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the static GIS portfolio")
    parser.add_argument("--base-path", default="", help="URL prefix, for example /repository-name")
    arguments = parser.parse_args()
    build(arguments.base_path)


if __name__ == "__main__":
    main()
