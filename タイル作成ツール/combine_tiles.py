import os
import re
import numpy as np
from PIL import Image

# ---------------- GSI DEM PNG デコード/エンコード ----------------
U = 0.01

def rgb_to_elevation_arr(rgb):
    R = rgb[...,0].astype(np.uint32)
    G = rgb[...,1].astype(np.uint32)
    B = rgb[...,2].astype(np.uint32)
    x = (R << 16) + (G << 8) + B
    invalid = (R == 128) & (G == 0) & (B == 0)
    invalid = invalid | (x == (1 << 23))
    mask_neg = x > (1 << 23)
    x_signed = x.astype(np.int64)
    x_signed[mask_neg] = x_signed[mask_neg] - (1 << 24)
    h = x_signed.astype(np.float64) * U
    h[invalid] = np.nan
    return h

def elevation_to_rgb_arr(h):
    out_shape = h.shape + (3,)
    rgb = np.zeros(out_shape, dtype=np.uint8)
    nan_mask = np.isnan(h)
    # round to nearest integer count of u
    x = np.rint(h / U).astype(np.int64)
    neg_mask = x < 0
    x_enc = x.copy()
    x_enc[neg_mask] += (1 << 24)
    invalid_mask = (x_enc == (1 << 23))
    set_na = nan_mask | invalid_mask
    rgb[...,0][set_na] = 128
    rgb[...,1][set_na] = 0
    rgb[...,2][set_na] = 0
    valid_mask = ~set_na
    xe = x_enc.astype(np.uint32) & 0xFFFFFF
    rgb[...,0][valid_mask] = (xe[valid_mask] >> 16) & 0xFF
    rgb[...,1][valid_mask] = (xe[valid_mask] >> 8) & 0xFF
    rgb[...,2][valid_mask] = xe[valid_mask] & 0xFF
    return rgb

# ---------------- 入力ファイルの検出ユーティリティ ----------------
# 対応するファイル名パターン（フラット名）を扱う
flat_patterns = [
    re.compile(r".*?(\d+)[_\-](\d+)\.png$"),          # matches ..._X_Y.png or ...-X_Y.png
    re.compile(r".*?(\d+)\.(\d+)\.png$"),             # matches .../x/y.png saved as x.y.png (rare)
]

def detect_child_tiles(base_dir, z):
    """
    Return set of (x,y) for existing tiles.
    Handles both hierarchical (z/x/y.png) and flat (z/<files containing x_y.png>).
    """
    candidates = set()
    zoom_dir = os.path.join(base_dir, str(z))
    if not os.path.isdir(zoom_dir):
        return candidates

    # Case 1: hierarchical directories: zoom_dir/x/y.png
    for name in os.listdir(zoom_dir):
        path_x = os.path.join(zoom_dir, name)
        if os.path.isdir(path_x) and name.isdigit():
            x = int(name)
            for fname in os.listdir(path_x):
                if not fname.lower().endswith(".png"):
                    continue
                base = os.path.splitext(fname)[0]
                try:
                    y = int(base)
                    candidates.add((x, y))
                except:
                    # maybe fname is tile_x_y.png etc -> try parse
                    for pat in flat_patterns:
                        m = pat.match(fname)
                        if m:
                            candidates.add((int(m.group(1)), int(m.group(2))))
        elif os.path.isfile(path_x):
            # zoom_dir contains files directly (flat)
            fname = name
            for pat in flat_patterns:
                m = pat.match(fname)
                if m:
                    candidates.add((int(m.group(1)), int(m.group(2))))
    return candidates

# ---------------- 子4枚から親を作成 ----------------
def build_parent_from_children(base_dir, z_child, parent_x, parent_y, verbose=False):
    Hc, Wc = 256, 256
    comp = np.full((Hc*2, Wc*2), np.nan, dtype=np.float64)  # 512x512
    found_any = False

    for i in range(2):
        for j in range(2):
            cx = parent_x * 2 + i
            cy = parent_y * 2 + j

            # try hierarchical path first
            candidate_paths = [
                os.path.join(base_dir, str(z_child), str(cx), f"{cy}.png"),
                os.path.join(base_dir, str(z_child), f"tile_{cx}_{cy}.png"),
                os.path.join(base_dir, str(z_child), f"combined_{cx}_{cy}.png"),
                os.path.join(base_dir, str(z_child), f"{cx}_{cy}.png"),
                os.path.join(base_dir, str(z_child), f"{cx}.{cy}.png"),
            ]
            chosen = None
            for p in candidate_paths:
                if os.path.exists(p):
                    chosen = p
                    break

            if chosen is None:
                if verbose:
                    print(f" Child missing for ({cx},{cy})")
                continue

            if verbose:
                print(f" Reading child: {chosen}")
            try:
                img = Image.open(chosen).convert("RGB")
            except Exception as e:
                print("  Failed to open", chosen, ":", e)
                continue

            arr = np.array(img)
            elev = rgb_to_elevation_arr(arr)
            xoff = i * Wc
            yoff = j * Hc
            comp[yoff:yoff+Hc, xoff:xoff+Wc] = elev
            found_any = True

    if not found_any:
        # no children at all -> return full-NA rgb (invalid)
        return elevation_to_rgb_arr(np.full((256,256), np.nan))

    # vectorized block average 2x2 -> 256x256
    comp_reshaped = comp.reshape(256,2,256,2)  # (py,2,px,2)
    parent = np.nanmean(np.nanmean(comp_reshaped, axis=3), axis=1)  # (256,256)

    return elevation_to_rgb_arr(parent)

# ---------------- 全ズーム生成ループ ----------------
def generate_downscales(base_dir, z_start=18, z_end=14, verbose=False):
    for z in range(z_start, z_end, -1):
        print(f"Generating zoom {z-1} from zoom {z} ...")
        child_tiles = detect_child_tiles(base_dir, z)
        if verbose:
            print(" Detected child tiles count:", len(child_tiles))
        parent_candidates = set((x//2, y//2) for (x,y) in child_tiles)
        out_dir = os.path.join(base_dir, str(z-1))
        os.makedirs(out_dir, exist_ok=True)

        for (px, py) in sorted(parent_candidates):
            out_x_dir = os.path.join(out_dir, str(px))
            os.makedirs(out_x_dir, exist_ok=True)
            out_path = os.path.join(out_x_dir, f"{py}.png")
            if os.path.exists(out_path):
                continue
            rgb_parent = build_parent_from_children(base_dir, z, px, py, verbose=verbose)
            Image.fromarray(rgb_parent).save(out_path)
            print(f" Saved {z-1}/{px}/{py}.png")
    print("Done.")

# ---------------- 実行 ----------------
if __name__ == "__main__":
    base_dir = r"E:\building_tiles\work_space\combined_tiles"   # ← あなたのルートに合わせる
    generate_downscales(base_dir, z_start=18, z_end=14, verbose=True)
