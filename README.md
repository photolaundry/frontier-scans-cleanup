# Fujifilm Frontier scan file cleanup
This script takes Fujifilm Frontier scan files and cleans up the filenames and optionally reorganizes the folder structure. This script supports either C4/C5 or MS01 exporting software. FE or PIC 2.6 isn't supported at this moment.

## What the problem is
For certain versions (e.g. A1+C4/C5) of the Fujifilm Frontier scanner software, you can only export BMPs (no TIFFs). Additionally, the output folder organization gets messy, with each order taking up a folder at the top-level, and no sorting by date or order ID (e.g. customer name). Another issue is the export software confuses the frame numbers, and the resulting filenames are off (e.g. 000001, 000007, 000008, etc).

Lastly the exporting software doesn't seem to set the correct DateTime EXIF tags for any of the images, so photo editing/organizing software can have trouble determining when the photos were scanned. This script adds these tags based on the file modification time, so the files will be more compatible with modern photo apps.

## What this script does
 1. (C4/C5 only) Converts any BMPs into lossless compressed TIFF.
 2. Adds timestamp EXIF data to all images.
 3. (MS01 only) Adds the "Fujifilm SP-3000" (or any other model using the `--scanner_model` flag)metadata to all images.
 4. Renames the images from `Customer001234/000001.jpg` (C4/C5) or `Customer_001234/R1-00131-0001.JPG` (MS01) to `R1234F01.jpg`, a simplification into this format: `R<roll_number>F<frame_number>.jpg`.
 5. (C4/C5 only) Reindexes the frame numbers for each roll starting at 1, potentially fixing wrong frame numbers from a flaky film rebate sensor.
 6. Optionally reorganizes scan folders into: `<order_id>/<date>/<order_number>/R<roll_number>F<frame_number>.jpg` format.

## Installation
TODO: update this when the wheel is easier to find/download.
The scripts are written and tested in Python 3.12, but likely works for Python 3.10 and newer. To install, use either `pip` or `pipx` to install the `frontier-scans-cleanup` package.

*[ImageMagick](https://docs.wand-py.org/en/latest/guide/install.html#install-imagemagick-on-debian-ubuntu)* and *[ExifTool](https://exiftool.org/install.html)* must both be installed for the script to work. For MacOS users, you can alternatively use Homebrew to install both of these packages: `brew install imagemagick exiftool`

## Run
### C4/C5 exporting software
Run `frontier-clean-c4c5` in the directory you've directly exported all your Frontier scans to (e.g. the directory you exported to the Writing tab in the C4/C5 software). Alternatively, you can specify the location as an argument: `frontier-clean-c4c5 /path/to/frontier_scans/`.
### MS01 exporting software
Run `frontier-clean-ms01` in the directory you've directly exported all your Frontier scans to (e.g. the directory you specified in the export digital product in MS01 server software). Alternatively, you can specify the location as an argument: `frontier-clean-ms01 /path/to/frontier_scans/`.
### Optional flags
If you want to reorganize your order folders by date and order ID (e.g. customer name), add the `--reorg` argument: `frontier-clean-ms01 --reorg /path/to/frontier_scans/`
