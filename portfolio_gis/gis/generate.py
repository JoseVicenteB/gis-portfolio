from .flood_maps import generate_flood_assets


def main() -> None:
    print("Generating Lower Liffey flood scenarios…")
    generate_flood_assets()
    print("Map assets written to static/generated/")


if __name__ == "__main__":
    main()
