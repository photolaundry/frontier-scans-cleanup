# Fujifilm Frontier scan file cleanup
This script takes Fujifilm Frontier scan files and cleans up the filenames and optionally the folder structure. Currently this script works only with the C4/C5 exporting software.

## What the problem is
For certain versions (e.g. A1+C4/C5) of the Fujifilm Frontier scanner software, you can only export BMPs (no TIFFs). Additionally, the output folder organization gets messy, with each order taking up a folder at the top-level, and no sorting by date or order ID (e.g. customer name). Another issue is the export software confuses the frame numbers, and the resulting filenames are off (e.g. 000001, 000007, 000008, etc).

Also the exporting software doesn't seem to set the correct DateTime EXIF tags for any of the images, so photo editing/organizing software can have trouble determining when the photos were scanned. This script adds these tags based on the file modification time, so the files will be more compatible with modern photo apps.

## What this script does
 1. (C4/C5 only) Converts any BMPs into compressed lossless TIFF.
 2. Adds timestamp EXIF data to all images.
 3. Renames the images from `Customer001234/000001.jpg` (C4/C5) or `Customer_001234/R1-001231-000001.JPG` (MS01) to `R1234F01.jpg`, a simplification into this format: `R{roll_number}F{frame_number}.jpg`.
 4. (C4/C5 only) Reindexes the frame numbers for each roll starting at 1, fixing the wrong frame numbers from a bad DX reader.
 5. Optionally reorganizes scan folders into: `<order_id>/<date>/<order_number>/<frame_number>.jpg` format.

## Requirements
The script was written and tested in Python 3.9, but likely works for Python 3.6 and newer. Use `pip install -r requirements/default.txt` to install the required python packages. In addition, ImageMagick and exiftool must both be installed. If you need help installing ImageMagick, go *[here](https://docs.wand-py.org/en/latest/guide/install.html#install-imagemagick-on-debian-ubuntu)*. For help installing exiftool, go *[here](https://exiftool.org/install.html)* (for MacOS users, you can also use *[homebrew](https://formulae.brew.sh/formula/exiftool)* to install it).

## Run
### C4/C5 exporting software
Run `python frontier_cleanup_c4c5.py` in the directory you've directly exported all your Frontier scans to (e.g. the directory you exported to the Writing tab in the C4/C5 software). Alternatively, you can specify the location as an argument: `python frontier_cleanup_c4c5.py path/to/frontier_scans/`.
### MS01 exporting software
Run `python frontier_cleanup_ms01.py` in the directory you've directly exported all your Frontier scans to (e.g. the directory you specified in the export digital product in MS01 server software). Alternatively, you can specify the location as an argument: `python frontier_cleanup_ms01.py path/to/frontier_scans/`.
