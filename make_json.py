from pathlib import Path
from multiprocessing import Pool
import sys
import json

def process_single_png(png_image_name):

    s = {'original_size': png_image_name.stat().st_size,
         'compressed_size': None,
         'type': None}    
    
    png_sameness_confirmed = "confirmed" / Path(png_image_name.name)
    webp_sameness_confirmed = "confirmed" / Path(png_image_name.name + ".webp")
    
    if png_sameness_confirmed.exists():
        s['compressed_size']=png_sameness_confirmed.stat().st_size
        s['type']="PNG"
    
    if webp_sameness_confirmed.exists():
        s['compressed_size']=webp_sameness_confirmed.stat().st_size
        s['type']="WEBP"
    
    return s

if __name__ == '__main__':
    
    if len(sys.argv)<2:
        originals_dir = Path("originals")
    else:
        originals_dir = Path(sys.argv[1])
    
    comp_stats = []
    
    images = (x for x in originals_dir.iterdir() if x.match("*.png"))
    
    # start 4 worker processes
    with Pool(processes=10) as pool:
        for i in pool.imap_unordered(process_single_png, images):
            comp_stats.append(i)


    with open("result.json", "w", encoding="utf-8") as f:
        json.dump(comp_stats, f, indent=4)
    