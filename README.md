# Fujifilm Frontier scanned images cleanup
TODO: fill out examples of what Frontier settings to use, as well as which versions of the software to use

## What the problem is
For certain versions (e.g. A1+C4/C5) of the Fujifilm Frontier scanner software, you can only export BMPs (no TIFFs). Additionally, the output folder organization gets messy, with each order taking up a folder at the top-level, and no sorting by date or order ID (e.g. customer). Another issue is the DX reader for frame numbers gets confused sometimes, and the frame numbers are off.

## What this script does
 1. Converts any BMPs into compressed lossless TIFF.
 2. Renames the images from `Customer001234/000001.jpg` to `R1234F1.jpg`, a simplification into this format: `R{roll_number}F{frame_number}.jpg`.
 3. Reindexes the frame numbers for each roll starting at 1, fixing the wrong frame numbers from a bad DX reader.
 4. Optionally reorganizes scan folders into: `<order_id>/<date>/<order_number>/<frame_number>.jpg` format.

## Requirements
The script was written and tested in Python 3.9, but likely works for Python 3.6 and newer. Use `pip install -r requirements/default.txt` to install the required python packages. In addition, ImageMagick must also be installed. If you need help installing ImageMagick, go *[here](https://docs.wand-py.org/en/latest/guide/install.html#install-imagemagick-on-debian-ubuntu)*.

## Run
Run `python frontier_cleanup.py` in the directory you've directly exported all your Frontier scans to (e.g. the directory you exported to the Writing tab in the C4/C5 software). Alternatively, you can specify the location as an argument: `python frontier_cleanup.py path/to/frontier_scans/`.
