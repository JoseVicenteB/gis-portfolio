from __future__ import annotations

import io
import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from PIL import Image

ROOT = Path.cwd()
RAW_DATA = ROOT / "data" / "raw"
GENERATED = ROOT / "static" / "generated"

COLORS = {
    "ink": "#18332F",
    "muted": "#63736E",
    "paper": "#F7F5EF",
    "ocean": "#DDEBE8",
    "land": "#F4F0E5",
    "boundary": "#829A93",
    "accent": "#D7794A",
    "green": "#286A57",
}


def configure_matplotlib() -> None:
    mpl.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "text.color": COLORS["ink"],
            "axes.labelcolor": COLORS["ink"],
            "xtick.color": COLORS["muted"],
            "ytick.color": COLORS["muted"],
            "figure.facecolor": COLORS["paper"],
            "axes.facecolor": COLORS["paper"],
            "savefig.facecolor": COLORS["paper"],
        }
    )


def save_webp(fig: plt.Figure, relative_path: str, width: int = 1800) -> Path:
    output = GENERATED / relative_path
    output.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=fig.dpi, bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)
    buffer.seek(0)
    with Image.open(buffer) as source:
        image = source.convert("RGB")
        if image.width > width:
            height = round(image.height * width / image.width)
            image = image.resize((width, height), Image.Resampling.LANCZOS)
        image.save(output, "WEBP", quality=91, method=6)
        if image.width > 960:
            preview = image.resize(
                (960, round(image.height * 960 / image.width)),
                Image.Resampling.LANCZOS,
            )
            preview.save(output.with_name(f"{output.stem}-960.webp"), "WEBP", quality=88, method=6)
    return output


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
