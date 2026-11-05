from .ndvi_example import generate_ndvi_maps
from .projection_comparison import generate_projection_maps


def main() -> None:
    print("Generating projection maps…")
    generate_projection_maps()
    print("Generating Sentinel-2 NDVI maps…")
    generate_ndvi_maps()
    print("Map assets written to static/generated/")


if __name__ == "__main__":
    main()
