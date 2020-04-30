import json
import numpy as np
import matplotlib.pyplot as p
import sys

with open("result.json","r", encoding="utf-8") as f:
    files = json.load(f)
    
hist_points_webp = 200
hist_points_png = 50

if len(sys.argv) >= 2:
    hist_points_webp = int(sys.argv[1])

if len(sys.argv) >= 3:
    hist_points_png = int(sys.argv[2])

ext_dict_percents={"WEBP":[], "PNG":[]}
ext_dict_sizes={"WEBP":[], "PNG":[]}
original_size=0
compressed_size=0
s_rate_compressed=0
for file in files:
    ext_dict_percents[file["type"]].append((1-file["compressed_size"]/file["original_size"])*100)
    ext_dict_sizes[file["type"]].append(file["compressed_size"])
    if (1-file["compressed_size"]/file["original_size"]) > 0.80:
        s_rate_compressed+=1
    original_size += file["original_size"]
    compressed_size += file["compressed_size"]

print(f"total files: {len(files)}")
print(f"original size: {original_size/2**30} GB")
print(f"compressed size: {compressed_size/2**30} GB")
print(f"total reduction: {(1-compressed_size/original_size)*100}%")
print(f"over 80% compression: {s_rate_compressed} ({s_rate_compressed/len(files)*100}%)")
    
for ext, sizes in ext_dict_sizes.items():
    sizes = np.array(sizes)/2**20
    print(f"{ext}: {np.sum(sizes)} MB in {len(sizes)} files")
    
for ext, sizes in ext_dict_percents.items():
    p.figure()
    p.title(ext)
    p.xlabel("reduction(%)")
    p.ylabel("files")
    p.hist(sizes, hist_points_webp if ext=="WEBP" else hist_points_png)
    
p.show()