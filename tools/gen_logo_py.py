#!/usr/bin/env python3
"""Gera airscope/logo_data.py a partir de tools/logo_grid.png (1 px = 1 bloco)."""
import sys
from PIL import Image

def is_empty(px):
    if len(px) == 4 and px[3] < 128: return True
    return max(px[:3]) < 45

def quant(c, step=12):
    return tuple(min(255, int(round(v/step)*step)) for v in c[:3])

def main(src, dst):
    im = Image.open(src).convert("RGBA")
    w, h = im.size
    grid = [[None if is_empty(im.getpixel((x,y))) else quant(im.getpixel((x,y)))
             for x in range(w)] for y in range(h)]
    used = [x for x in range(w) if any(grid[y][x] for y in range(h))]
    x0, x1 = min(used), max(used)
    grid = [r[x0:x1+1] for r in grid]; w = x1-x0+1
    palette = sorted({c for r in grid for c in r if c})
    index = {c:i for i,c in enumerate(palette)}
    blank = [all(c is None for c in r) for r in grid]
    split = next((y for y in range(h) if blank[y]), h)
    word_start = next((y for y in range(split,h) if not blank[y]), 0)
    with open(dst,"w") as f:
        f.write('"""Gerado por tools/gen_logo_py.py — nao edite a mao."""\n')
        f.write(f"W = {w}\nH = {h}\nICON_END = {split}\nWORD_START = {word_start}\nSOLUTIONS_COL = {19-x0}\n\n")
        f.write("PALETTE = [\n")
        for i in range(0,len(palette),6):
            f.write("    "+", ".join(f"0x{r:02X}{g:02X}{b:02X}" for r,g,b in palette[i:i+6])+",\n")
        f.write("]\n\n# cada linha: tupla de indices na PALETTE, -1 = vazio\nROWS = [\n")
        for r in grid:
            f.write("    ("+",".join(str(index[c]) if c else "-1" for c in r)+"),\n")
        f.write("]\n")
    print(f"{dst}: {w}x{h}, paleta {len(palette)}, icone<{split}, word>={word_start}")

main("tools/logo_grid.png","airscope/logo_data.py")
