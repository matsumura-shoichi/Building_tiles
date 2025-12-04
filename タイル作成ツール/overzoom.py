import requests
from io import BytesIO
from PIL import Image

def fetch_elevation_tile(tile_x, tile_y, zoom_level):
    url = f"https://cyberjapandata.gsi.go.jp/xyz/dem5a_png/{zoom_level}/{tile_x}/{tile_y}.png"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return Image.open(BytesIO(response.content))
    else:
        print(f"Error fetching tile: {response.status_code} for URL: {url}")
        return None

def save_split_tiles(enlarged_image, tile_x, tile_y):
    tile_size = 256
    num_tiles = enlarged_image.width // tile_size  # 2048 / 256 = 8

    for i in range(num_tiles):  # 8タイル分
        for j in range(num_tiles):  # 8タイル分
            # タイルを切り出す
            left = i * tile_size
            upper = j * tile_size
            right = left + tile_size
            lower = upper + tile_size
            
            tile = enlarged_image.crop((left, upper, right, lower))
            
            # WEBメルカトルのタイル座標に基づいてファイル名を生成
            tile_x_18 = tile_x * 8 + i  # ズームレベル15からズームレベル18への計算
            tile_y_18 = tile_y * 8 + j  # ズームレベル15からズームレベル18への計算
            
            output_filename = f"tile_{tile_x_18}_{tile_y_18}.png"
            tile.save(output_filename)
            print(f"Saved {output_filename}")
tile_list = []

# Zoom13 → Zoom15 は ×4
for tx13 in [7126, 7127]:
    for i in range(4):  # 0〜3
        tile_list.append(tx13 * 4 + i)

tile_y_list = []
ty13 = 3260
for j in range(4):
    tile_y_list.append(ty13 * 4 + j)

zoom_level = 15

# 8倍して Zoom18 タイル作成（以前と同じ）
for tile_x in tile_list:
    for tile_y in tile_y_list:

        elevation_tile = fetch_elevation_tile(tile_x, tile_y, zoom_level)

        if elevation_tile is not None:
            enlarged_tile = elevation_tile.resize((2048, 2048), Image.NEAREST)
            save_split_tiles(enlarged_tile, tile_x, tile_y)

# 標高タイルを取得して8倍に拡大
elevation_tile = fetch_elevation_tile(tile_x, tile_y, zoom_level)

if elevation_tile is not None:
    # 8倍に拡大
    enlarged_tile = elevation_tile.resize((2048, 2048), Image.NEAREST)
    
    # タイルを分割して保存（WEBメルカトルのタイル座標をファイル名に使用）
    save_split_tiles(enlarged_tile, tile_x, tile_y)
