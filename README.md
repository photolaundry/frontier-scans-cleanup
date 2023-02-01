# Fujifilm Frontier scanned images cleanup
TODO: fill out examples of what Frontier settings to use, as well as which versions of the software to use

## What the problem is
When using a Fujifilm Frontier scanner, the images that it outputs have some broken metadata. They also often have the wrong timestamps too. Specifically, the files are missing the DateTimeOriginal and related EXIF tags. This means that any image-editing software will use the last modified date from the filesystem as the "capture date," meaning rotating images or simply renaming images causes images to jump forward in time. This usually translates to Lightroom missing up the order of the photos by the time they are imported.

## What this script does
The script does 2 main things:
 1. Assigns a more reasonable DateTimeOriginal to each image, by using the current timestamp for the first image, and then adding 1 millisecond to that for each subsequent image. This preserves the sorting order in the same order they were scanned. Essentially, it's as if all the images were scanned in quick succession, 1 millisecond apart. There's additional logic to make sure different rolls don't collide on their timestamps.
 3. Renames the images from `000001008411/000001.jpg` to `R8411F1.jpg`, a simplification into this format: `R{roll_number}F{frame_number}.jpg`.

## Requirements
The script was written in Python 3.9, but likely works for Python 3.6 and newer. Use `pip install -r requirements/default.txt` to install the required python packages. In addition, exiftool must be installed and available in the PATH as `exiftool`.

## Run
Run `python frontier_cleanup.py` in the directory you wish to search for Frontier scans from. Alternatively, you can specify the location as an argument: `python frontier_cleanup.py 20211226/00007466/`.
