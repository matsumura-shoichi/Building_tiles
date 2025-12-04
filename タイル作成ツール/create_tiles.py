import numpy as np
from shapely.geometry import Point, Polygon 
from lxml import etree 
from PIL import Image

# -------------------------------
# タイル境界計算（WebMercator）
# -------------------------------
def calculate_tile_bounds(tile_x, tile_y, zoom_level):
    n = 2 ** zoom_level
    min_lon = tile_x / n * 360.0 - 180.0
    max_lon = (tile_x + 1) / n * 360.0 - 180.0
    min_lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * tile_y / n))))
    max_lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * (tile_y + 1) / n))))
    return Polygon([(min_lon, min_lat), (max_lon, min_lat), (max_lon, max_lat), (min_lon, max_lat)])

# -------------------------------
# GML読み込み & ポリゴン抽出
# -------------------------------
def parse_gml_and_check_polygons(gml_file, tile_polygon):
    selected_polygons = []
    max_elevations = []

    with open(gml_file, 'rb') as file:
        tree = etree.parse(file)

    namespace = {
        'gml': 'http://www.opengis.net/gml/3.2',
        'dkgd3d': 'http://dkgd.gsi.go.jp/spec/2025/DKGD3D_GMLSchema'
    }

    for bld in tree.xpath('//dkgd3d:BldA3d', namespaces=namespace):
        max_elv_list = bld.xpath('./dkgd3d:maxElv/text()', namespaces=namespace)
        if not max_elv_list:
            continue

        max_elv = float(max_elv_list[0])

        coords = bld.xpath('.//gml:posList/text()', namespaces=namespace)
        if coords:
            coords = list(map(float, coords[0].split()))
            points = list(zip(coords[1::2], coords[0::2]))  # (lon, lat)
            polygon = Polygon(points)

            if tile_polygon.intersects(polygon):
                selected_polygons.append(polygon)
                max_elevations.append(max_elv)

    return selected_polygons, max_elevations

# -------------------------------
# 標高 → RGB（地理院タイル方式）
# -------------------------------
def elevation_to_rgb(elevation):
    if elevation is None or elevation < 0:
        return (128, 0, 0)

    x = int(100 * elevation)
    if x >= 2**23:
        return (128, 0, 0)

    R = (x >> 16) & 0xFF
    G = (x >> 8) & 0xFF
    B = x & 0xFF
    return (R, G, B)

# -------------------------------
# 1タイル生成
# -------------------------------
def create_elevation_tile(tile_x, tile_y, zoom_level, gml_file):
    tile_polygon = calculate_tile_bounds(tile_x, tile_y, zoom_level)
    selected_polygons, max_elevations = parse_gml_and_check_polygons(gml_file, tile_polygon)

    tile_size = 256
    elevation_tile = np.zeros((tile_size, tile_size, 3), dtype=np.uint8)

    min_lon, min_lat, max_lon, max_lat = tile_polygon.bounds

    for px in range(tile_size):
        for py in range(tile_size):
            lon = min_lon + (max_lon - min_lon) * (px / tile_size)
            lat = min_lat + (max_lat - min_lat) * (1 - py / tile_size)
            point = Point(lon, lat)

            elevation = 0
            for polygon, max_elv in zip(selected_polygons, max_elevations):
                if polygon.contains(point):
                    elevation = max_elv
                    break

            elevation_tile[py, px] = elevation_to_rgb(elevation)

    output_filename = f"elevation_z{zoom_level}_{tile_x}_{tile_y}.png"
    Image.fromarray(elevation_tile).save(output_filename)
    print(f"Saved: {output_filename}")

# -------------------------------
# ズーム13 → ズーム18 タイル生成
# -------------------------------
def generate_zoom18_tiles(base_tiles, gml_file):
    base_zoom = 13
    target_zoom = 18
    diff = target_zoom - base_zoom  # =5
    scale = 2 ** diff               # =32

    print(f"Generating {scale} × {scale} per base tile (total 1024 each)...")

    for base_x, base_y in base_tiles:
        for dx in range(scale):
            for dy in range(scale):
                child_x = base_x * scale + dx
                child_y = base_y * scale + dy

                create_elevation_tile(child_x, child_y, target_zoom, gml_file)

# -------------------------------
# 実行：ズーム13 → 全ズーム18（32×32=1024タイル × 2枚）
# -------------------------------
gml_file = r"C:\Users\matsu\Downloads\000268432\建物\DKG-GML-513351-BldA3d-20231031-0001.xml"

# 対象ズーム13のタイル
base_tiles = [
    (7126, 3260),
    (7127, 3260)
]

generate_zoom18_tiles(base_tiles, gml_file)
