import io
import sys
import os

from traceback import format_exc
from multiprocessing import Pool, cpu_count
from subprocess import run, DEVNULL
from shutil import copy2
from array import array
from pathlib import Path

import png

import numpy as np          # pip install numpy

from PIL import ImageFile
# allows invalid crc or size in chunks with Pillow
ImageFile.LOAD_TRUNCATED_IMAGES = True

from PIL.PngImagePlugin import PngImageFile
from PIL.ImageCms import ImageCmsProfile
from PIL import Image       # pip install pillow
from PIL import ImageChops

COMPRESSED_DIR = Path("compressed")
CONFIRMED_DIR = Path("confirmed")
PATH_TO_ECT = Path("bin/ect.exe")
PATH_TO_CWEBP = Path("bin/cwebp.exe")

def convert_to_rgb_if_no_transparency(image):
    alpha = image.getchannel('A')
    alpha_arr = np.asarray(alpha)
    if alpha_arr.max() == alpha_arr.min() == 255:
        image = image.convert("RGB")

    return image

# Making fully transparent pixels
# to have same value


def nulling_transparent(image):
    image = image.copy()
    alpha = image.getchannel('A')
    a = np.asarray(alpha)
    transparent_pixels = a == 0
    if transparent_pixels.any():
        r = np.array(image.getchannel('R'))
        g = np.array(image.getchannel('G'))
        b = np.array(image.getchannel('B'))


        r[transparent_pixels] = 0
        g[transparent_pixels] = 0
        b[transparent_pixels] = 0

        rgbArray = np.zeros((a.shape[0], a.shape[1], 4), 'uint8')
        rgbArray[..., 0] = r
        rgbArray[..., 1] = g
        rgbArray[..., 2] = b
        rgbArray[..., 3] = a

        image = Image.fromarray(rgbArray)
    return image


def is_same(png_image_name, webp_image_name):

    png_image = Image.open(png_image_name).convert("RGBA")
    webp_image = Image.open(webp_image_name).convert("RGBA")

    png_image = nulling_transparent(png_image)
    webp_image = nulling_transparent(webp_image)

    png_image = convert_to_rgb_if_no_transparency(png_image)
    webp_image = convert_to_rgb_if_no_transparency(webp_image)
    return not ImageChops.difference(png_image, webp_image).getbbox()


def size_differense(png_image_name, webp_image_name):
    png_image_size = os.stat(png_image_name).st_size
    webp_image_size = os.stat(webp_image_name).st_size
    return png_image_size - webp_image_size


def check_actually_16_bit(rr):
    dims_orig = rr[3]['size']
    planes_orig = rr[3]['planes']
    
    # check out lodepng_get_color_profile function
    # from lodepng.cpp in ECT
    # some 16-bit images are really have same
    # lower and higher bytes, that is
    # 42 42 33 33 instead of just 42 33
    # Why? I have no idea
    for row_orig in rr[2]:
        row_orig = np.array(row_orig)
        for i in range(planes_orig):
            if not min(row_orig[i::planes_orig]//256 == row_orig[i::planes_orig]%256):
                return True
    
    return False
    
def check_depth_more_8_or_gamma(png_image_name):
    r = png.Reader(str(png_image_name))
    keys = []
    gamma = False

    while True:
        # I used custom version that allows
        # invalid lenth of chunks in addition to invalid CRC
        key, value = r.chunk(lenient=True)
        

        if key == b'iCCP':
            try:
                f = io.BytesIO(value)
                prf = ImageCmsProfile(f)  # ICC profile could be invalid
                keys.append(key)
            except OSError:
                pass
        else:
            keys.append(key)

        if key == b'IEND':
            break

    if b'gAMA' in keys and b'sRGB' not in keys and b'iCCP' not in keys:
        gamma = True

    r = png.Reader(str(png_image_name))
    rr = r.read(lenient=True)
    
    return ( rr[3]["bitdepth"] > 8 and check_actually_16_bit(rr) ), gamma


def is_same_16_bit_pngs(original, compressed):
    read_orig = png.Reader(str(original)).read(lenient=True)
    read_comp = png.Reader(str(compressed)).read(lenient=True)

    dims_orig = read_orig[3]['size']
    dims_comp = read_comp[3]['size']

    if dims_orig != dims_comp:
        return False

    is_gray_orig = read_orig[3]['greyscale']
    is_gray_comp = read_comp[3]['greyscale']
    
    has_alpha_orig = read_orig[3]['alpha']
    has_alpha_comp = read_comp[3]['alpha']
    
    planes_orig = read_orig[3]['planes']
    planes_comp = read_comp[3]['planes']

    # if compressed image has no alpha channel, creating fully opaque alpha
    if not has_alpha_orig:
        a_orig = np.asarray(array('H', [65535] * dims_orig[0]))

    # if compressed image has no alpha channel, creating fully opaque alpha
    if not has_alpha_comp:
        a_comp = np.asarray(array('H', [65535] * dims_comp[0]))

    a_ind_orig = None if planes_orig == 1 else planes_orig - 1
    a_ind_comp = None if planes_comp == 1 else planes_comp - 1

    for row_orig, row_comp in zip(read_orig[2], read_comp[2]):
        if is_gray_orig:
            r_orig = g_orig = b_orig = np.asarray(row_orig[::planes_orig])
        else:
            r_orig = np.asarray(row_orig[::planes_orig])
            g_orig = np.asarray(row_orig[1::planes_orig])
            b_orig = np.asarray(row_orig[2::planes_orig])

        if is_gray_comp:
            r_comp = g_comp = b_comp = np.asarray(row_comp[::planes_comp])
        else:
            r_comp = np.asarray(row_comp[::planes_comp])
            g_comp = np.asarray(row_comp[1::planes_comp])
            b_comp = np.asarray(row_comp[2::planes_comp])

        if has_alpha_orig:
            a_orig = np.asarray(row_orig[a_ind_orig::planes_orig])

        if has_alpha_comp:
            a_comp = np.asarray(row_comp[a_ind_comp::planes_comp])

        # Making fully transparent pixels
        # to have same value
        trasparent_orig = a_orig == 0
        r_orig[trasparent_orig] = 0
        g_orig[trasparent_orig] = 0
        b_orig[trasparent_orig] = 0

        trasparent_comp = a_comp == 0
        r_comp[trasparent_comp] = 0
        g_comp[trasparent_comp] = 0
        b_comp[trasparent_comp] = 0

        if (not np.array_equal(r_orig, r_comp)
            or not np.array_equal(g_orig, g_comp)
            or not np.array_equal(b_orig, b_comp)
            or not np.array_equal(a_orig, a_comp)
           ):
            return False

    return True


def prepare_ect(original, compressed, ect):
    # ect always replaces a file
    copy2(original, compressed)

    # commented line means one picture per hour
    # return [str(etc), '-9', '--allfilters', '--pal_sort=120', 
    #         str(compressed)]
    return [str(ect), '-9', str(compressed)]


def prepare_cwepb(original, compressed, cwebp):
    return [
        str(cwebp),
        '-z',
        '9',
        '-m',
        '6',
        '-lossless',
        '-metadata',
        'all',
        str(original),
        '-o',
        str(compressed)]


def print_size_difference(original, compressed):
    size_diff = size_differense(original, compressed)
    s = []
    if size_diff > 0:
        s.append(f"space saved: {size_diff}")
        s.append(f"approximately: {size_diff/2**20} MB")
    else:
        s.append(f"space wasted: {-size_diff}")
        s.append(f"approximately: {-size_diff/2**20} MB")
    return s


def mute():
    sys.stdout = open(os.devnull, 'w')
    sys.stderr = open(os.devnull, 'w')


def process_single_png(png_image_name):
    s = []
    s.append(f"Processing {png_image_name}")

    png_sameness_confirmed = CONFIRMED_DIR / Path(png_image_name.name)
    webp_sameness_confirmed = CONFIRMED_DIR / Path(png_image_name.name + ".webp")

    if webp_sameness_confirmed.exists() or png_sameness_confirmed.exists():
        return ""

    try:
        is_16_bit, has_gamma = check_depth_more_8_or_gamma(png_image_name)
    except BaseException:
        s.append(
            f"Error with parsing {png_image_name} in 'check_depth_more_8_or_gamma'")
        s.append(format_exc())
        return '\n'.join(s)

    if is_16_bit or has_gamma:
        s.append(f"File {png_image_name} has more than 8 bit per pixel and/or non-standard gamma")
        png_compressed = COMPRESSED_DIR / Path(png_image_name.name)

        same = False

        if png_compressed.exists():
            try:
                if is_16_bit:
                    same = is_same_16_bit_pngs(png_image_name, png_compressed)
                else:
                    same = is_same(png_image_name, png_compressed)
            except BaseException:
                # do nothing, this can be because of emergency shutdown
                pass

        if not same:
            s.append(f"Making {png_compressed}")
            cmdline = prepare_ect(
                png_image_name,
                png_compressed,
                PATH_TO_ECT)
            run(cmdline, stdout=DEVNULL, stderr=DEVNULL)

            s.append(f"comparing {png_image_name} and {png_compressed}")
            try:
                if is_16_bit:
                    same = is_same_16_bit_pngs(png_image_name, png_compressed)
                else:
                    same = is_same(png_image_name, png_compressed)
            except BaseException:
                s.append(
                    f"Error during compare of {png_image_name} and {png_compressed}")
                s.append(format_exc())
                return '\n'.join(s)

        if same:
            s.extend(print_size_difference(png_image_name, png_compressed))
            png_compressed.rename(png_sameness_confirmed)
        else:
            s.append("Error: image pixels are different")
    else:
        webp_image_name = COMPRESSED_DIR / Path(png_image_name.name + ".webp")

        same = False
        if webp_image_name.exists():
            try:
                same = is_same(png_image_name, webp_image_name)
            except BaseException:
                pass

        if not same:
            s.append(f"Making {webp_image_name}")
            cmdline = prepare_cwepb(
                png_image_name,
                webp_image_name,
                PATH_TO_CWEBP)
            run(cmdline, stdout=DEVNULL, stderr=DEVNULL)

            s.append(f"Comparing {png_image_name} and {webp_image_name}")
            try:
                same = is_same(png_image_name, webp_image_name)
            except BaseException:
                s.append(
                    f"Error during compare of {png_image_name} and {webp_image_name}")
                s.append(format_exc())
                return '\n'.join(s)

        if same:
            s.append(
                f"Size difference of {png_image_name} and {webp_image_name}")
            s.extend(print_size_difference(png_image_name, webp_image_name))
            webp_image_name.rename(webp_sameness_confirmed)
        else:
            s.append("Error: image pixels are different")

    return '\n'.join(s)




if __name__ == '__main__':
    os.makedirs(COMPRESSED_DIR, exist_ok=True)
    os.makedirs(CONFIRMED_DIR, exist_ok=True)
    if len(sys.argv)<2:
        originals_dir = Path("originals")
        os.makedirs(originals_dir, exist_ok=True)
    else:
        originals_dir = Path(sys.argv[1])

    images = (x for x in originals_dir.iterdir() if x.match("*.png"))
    
    with Pool(processes=cpu_count(), initializer=mute) as pool, open("log.txt", "w", encoding="utf-8") as f:
        for i in pool.imap_unordered(process_single_png, images):
            if i:
                print(i)
                print(i, file=f, flush=True)
