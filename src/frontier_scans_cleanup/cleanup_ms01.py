import argparse
import itertools
import platform
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import exiftool
import readchar
from wand.image import Image

# assume folder structure:
# YourName_007466/  <- order id + roll number
#   Export JPG NoResize/ <- Tells which file format
#     R1-00046-0000A.JPG  <- R1-{MS01 internal roll number, ignore}-{frame_num}
#                         <- Often this is the first frame, named 00 or 00A
#     R1-00046-0000A_0001.JPG  <- same as above, but actually 2nd frame 0A
#     R1-00046-0001A.JPG  <- etc
#     R1-00046-0002A.JPG  <- etc
#     R1-00046-0003A.JPG  <- etc
#     ...
# YourName_007467/
#   Export TIFF NoResize/ <- Tells which file format
#     R1-00047-0001.TIF
#     ...
# OtherName_007468/
#   ...


class FrontierCleanerMS01:
    EXIF_DATETIME_STR_FORMAT = "%Y:%m:%d %H:%M:%S"
    EXIFTOOL_SUCCESSFUL_WRITE_MESSAGE = "1 image files updated"
    ROLL_DIR_PATTERN = r"(?P<order_id>.{1,10})_(?P<roll_number>\d{6})"
    ROLL_DIR_GLOB_PATTERN = "*_" + "[0-9]" * 6
    IMAGE_NAME_PATTERN = r"R1-\d{5}-(?P<frame_info>.+)"
    DEFAULT_SCANNER_MODEL = "SP-3000"
    # mapping from frame_info to a numeric key (for sorting)
    # start with X and 00
    FRAME_INFO_KEY = ("X", "00")
    # frames 0 through 40
    FRAME_INFO_KEY = FRAME_INFO_KEY + tuple(map(str, range(41)))
    # interlace all the A half-frame numbers
    FRAME_INFO_KEY = tuple(
        f"{left}{right}" for left in FRAME_INFO_KEY for right in ("", "A")
    )
    # add E at the very end
    FRAME_INFO_KEY = FRAME_INFO_KEY + ("E",)
    # convert to dict for efficient mapping from str to number
    FRAME_INFO_KEY = {k: i for i, k in enumerate(FRAME_INFO_KEY)}

    def __init__(
        self,
        exiftool_client,
        frontier_export_path=None,
        reorg=False,
        convert_bw=False,
        roll_padding=4,
        scanner_model=None,
    ):
        """
        exiftool_client is a exiftool.ExifToolHelper object that will be used
        to perform all EXIF modifications required.
        frontier_export_path is the path that the Frontier exporting software
        directly exports to. If not provided, frontier_export_path will default
        to the current working directory.
        reorg is whether to reorganize all scans into directories based on
        order id and date. Defaults to False.
        convert_bw is whether to interactively select directories to convert
        to true black-and-white. Defaults to False.
        roll_padding is how many characters of zero padding to use for the
        roll number. Defaults to 4.
        scanner_model is the name of the scanner you used (this will be
        written to the EXIF data). Defaults to "SP-3000".
        """
        self.exiftool = exiftool_client

        if not frontier_export_path:
            self.frontier_export_path = Path.cwd()
        else:
            self.frontier_export_path = Path(frontier_export_path)

        self.reorg = reorg
        self.convert_bw = convert_bw
        self.roll_padding = roll_padding
        self.image_name_matcher = re.compile(self.IMAGE_NAME_PATTERN)
        self.scanner_model = scanner_model or self.DEFAULT_SCANNER_MODEL

    def clean(self):
        for roll_dir in self.find_all_rolls():
            try:
                self.fix_all_in_dir(roll_dir)
            except ValueError as e:
                print(e)
                print(f"  skipping directory {roll_dir}...")

    def find_all_rolls(self):
        """
        The Frontier MS01 system exports images into a dir for each roll, where
        the directory name is the order id (up to 10 of any character) followed
        by a _ and the 6-digit roll number.
        """
        found_dirs = []
        if not self.frontier_export_path.is_dir():
            raise ValueError("given path is not a directory")

        found_dirs += sorted(
            filter(
                lambda x: x.is_dir(),
                self.frontier_export_path.glob(self.ROLL_DIR_GLOB_PATTERN),
            )
        )

        return found_dirs

    def fix_all_in_dir(self, roll_dir):
        """
        This method does the following to sanitize images:
        1. Optionally converts all images to B+W (asks for confirmation).
        2. Add EXIF tags for capture time to all images.
        3. Renames all images to simplify.
        4. Optionally reorganizes the images into a new directory structure.

        We first optionally convert all images to B+W, prompting the user
        for confirmation before doing so.

        We then add the DateTimeOriginal EXIF tag to all images, based on the
        filesystem modified timestamp of the file. This fixes the issue where
        rotating a file in Finder or Adobe Bridge will adjust the image's
        modified timestamp, messing up programs that sort by Capture Time
        (such as Lightroom).

        We set the capture times of the files as such:
            1st image gets the same capture time as its file modified time.
            2nd image gets the 1st image's capture time, but +1 millisecond.
            3rd image gets the 1st image's capture time, but +2 milliseconds.

        We can't just save each image's modified time as its capture time
        because the export software doesn't guarantee that it saves the images
        in sequential order, sometimes a later frame gets saved before an
        earlier one.

        The adding of milliseconds helps preserve the sorting order in programs
        like Lightroom since the ordering is also enforced by the capture time
        set.  If all files got the same capture time, and we were saving the
        frame name in the filenames, we would get cases where ###, 00, 0, E, XA
        frames get out of order, because LR would have to use filename to sort
        since they'd all have the same capture time.

        Then we rename images into a cleaner format with just the roll number
        and the frame number/name:
            R<roll_number>F<frame_info>.jpg (or .tif)

        Finally, we optionally move all images to this directory structure:
            <order/customer id>/<date>/<roll number>/

        roll_dir is a path object that represents the directory of images to
        operate on.
        """
        print(f"working on dir: {roll_dir}")

        # the roll number can be extracted from the directory name
        dir_match = re.match(self.ROLL_DIR_PATTERN, roll_dir.name)
        if not dir_match:
            raise ValueError(
                f"image dir doesn't match expected format: {roll_dir}"
            )

        images = list(
            itertools.chain(
                roll_dir.glob("**/*.jpg"),
                roll_dir.glob("**/*.tif"),
                roll_dir.glob("**/*.bmp"),
                roll_dir.glob("**/*.JPG"),
                roll_dir.glob("**/*.TIF"),
                roll_dir.glob("**/*.BMP"),
            )
        )

        if not images:
            print(f"  No images found, skipping: {roll_dir}")
            return

        img_matches = {
            img_path: self.image_name_matcher.fullmatch(img_path.stem)
            for img_path in images
        }
        bad_matches = tuple(
            img_path for img_path, match in img_matches.items() if not match
        )
        if bad_matches:
            raise ValueError(
                f"image filename doesn't match expected format: "
                f"{bad_matches[0]}"
            )

        # check a random image to see if the filename indicates this is
        # a half-frame roll
        rand_image = images[0]
        rand_image_match = img_matches[rand_image]
        rand_frame_info = rand_image_match.group("frame_info")
        if "-" in rand_frame_info:
            # this is a half-frame roll that uses "0-0A" file naming so
            # key on just the left side using the special FRAME_INFO_KEY ordering
            def key(img_path):
                img_frame_info = img_matches[img_path].group("frame_info")
                left, right = img_frame_info.split("-")
                return self.FRAME_INFO_KEY[left]

            images.sort(key=key)
        else:
            # not a half-frame roll, so sort via normal string comparison
            # like the old behavior
            images.sort()

        first_image_path = images[0]
        first_image_mtime = datetime.fromtimestamp(
            first_image_path.stat().st_mtime
        )

        need_to_convert_bw = False
        if self.convert_bw:
            while True:
                print(
                    f"  convert {roll_dir.name} to B+W? "
                    "[y->yes, n->no/skip, o->view the first image, "
                    "i->inspect the first image for B+W]: ",
                    end="",
                )
                sys.stdout.flush()
                selection = readchar.readchar().lower()
                print()
                match selection:
                    case "y":
                        need_to_convert_bw = True
                        break
                    case "n":
                        break
                    case "i":
                        mean, max = self.inspect_image_for_bw(first_image_path)
                        print(f"  inspecting {first_image_path.name}:")
                        print(f"  chroma: mean: {mean:.4f} | max: {max:.4f}")
                        if mean < 0.02 and max < 0.05:
                            print("  is B+W? likely")
                        else:
                            print("  is B+W? unlikely")
                    case "o":
                        print(
                            f"  opening {first_image_path.name} for viewing..."
                        )
                        self.open_image(first_image_path)

        roll_number = dir_match.group("roll_number")
        # convert roll number to an int, and then zero pad it as desired
        formatted_roll_number = f"{int(roll_number):0>{self.roll_padding}d}"

        if self.reorg:
            # the order id can be extracted from the directory name
            order_id = dir_match.group("order_id")

            date_dir_number = first_image_mtime.strftime("%Y%m%d")

            # destination dir to save the images to (same dir as Frontier)
            dest_dir = (
                self.frontier_export_path
                / order_id
                / date_dir_number
                / formatted_roll_number
            )
            print(f"  --reorg used, will move scans to: {dest_dir}")
        else:
            # reuse the same directory as the original image
            dest_dir = first_image_path.parent

        # set of all the "Export JPG NoResize" or "Export TIF NoResize" dirs
        # (which all images are originally stored in)
        export_dirs = set()

        for image_num, image_path in enumerate(images):
            suffix = image_path.suffix  # the extension including the .

            if not image_path.is_file():
                continue

            img_match = img_matches[image_path]

            # add the dir that the image was found in to the export_dirs set
            export_dirs.add(image_path.parent)

            if need_to_convert_bw:
                print(f"  converting {image_path.name} to B+W")
                with Image(filename=image_path) as original_image:
                    original_image.type = "grayscale"
                    original_image.save(filename=image_path)

            # image ordering is preserved in the capture time saved,
            # see above docstring
            datetime_original = first_image_mtime.strftime(
                self.EXIF_DATETIME_STR_FORMAT
            )
            datetime_digitized = first_image_mtime.strftime(
                self.EXIF_DATETIME_STR_FORMAT
            )
            # There's 3 decimal places for the milliseconds, so zero-pad to 3
            subsec_time_original = f"{image_num:0>3d}"
            subsec_time_digitized = f"{image_num:0>3d}"

            tags_to_write = {
                "EXIF:DateTimeOriginal": datetime_original,
                "EXIF:DateTimeDigitized": datetime_digitized,
                "EXIF:SubSecTimeOriginal": subsec_time_original,
                "EXIF:SubSecTimeDigitized": subsec_time_digitized,
                "EXIF:Make": "FUJI PHOTO FILM CO., LTD.",
                "EXIF:Model": self.scanner_model,
            }

            print(
                f"  {image_path.name} getting datetime: "
                f"{datetime_original}:{subsec_time_original}"
            )

            self.write_exif_tags(image_path, tags_to_write)

            frame_info = img_match.group("frame_info")

            new_filename = f"R{formatted_roll_number}F{frame_info}"

            new_filepath = dest_dir / f"{new_filename}{suffix}"
            print(f"  Renaming {image_path.name} => {new_filename}{suffix}")
            dest_dir.mkdir(parents=True, exist_ok=True)
            image_path.rename(new_filepath)

        if self.reorg:
            # delete the old roll_dir now that all images are renamed and
            # moved
            try:
                # delete all the the "Export JPG NoResize" dirs
                for export_dir in export_dirs:
                    export_dir.rmdir()
                # delete the roll_dir
                roll_dir.rmdir()
            except OSError:
                print(f"  Directory not empty, skipping deletion: {roll_dir}")

    def write_exif_tags(self, image_path, tags_to_write):
        try:
            result = self.exiftool.set_tags(str(image_path), tags_to_write)
        except exiftool.exceptions.ExifToolExecuteError as err:
            print(
                f"  exiftool error while updating timestamps on image: "
                f"  {image_path}"
            )
            print(f"error: {err.stdout}")
            return False
        else:
            result = result.strip()
            if result != self.EXIFTOOL_SUCCESSFUL_WRITE_MESSAGE:
                print(
                    f"  failed to update timestamps on image:   {image_path}"
                )
                print(f"  exiftool: {result}")
                return False
            return True

    def open_image(self, image_path):
        open_command = ""
        match platform.system():
            case "Darwin":
                open_command = "open"
            case "Linux":
                open_command = "xdg-open"
            case "Windows":
                open_command = "start"
            case _:
                print(
                    "  Could not determine the OS, skipping viewing the image"
                )
                return

        try:
            subprocess.run(
                [open_command, str(image_path)],
                check=True,
            )
        except subprocess.CalledProcessError as err:
            print("  Error while viewing image:")
            print(err.stdout)
            print(err.stderr)

    def inspect_image_for_bw(self, image_path):
        with Image(filename=image_path) as img:
            img.transform_colorspace("hcl")
            # the "green" channel is the C channel, C for chroma
            mean, stddev = img.mean_channel("green")
            min, max = img.range_channel("green")
            return (mean / img.quantum_range, max / img.quantum_range)


def cli():
    parser = argparse.ArgumentParser(
        description="Sanitizes Frontier scan files by renaming images and "
        "optionally reorganizes them into order id directories. This script "
        "is meant for use with MS01 exporting software."
    )
    parser.add_argument(
        "frontier_export_path",
        nargs="?",
        default=None,
        help="The path to the directory that Frontier exporting software "
        "directly exports to. If not provided, will assume the current "
        "working directory.",
    )

    parser.add_argument(
        "--reorg",
        action="store_true",
        default=False,
        help="whether to reorganize the scans into order and date directories "
        "or not. default: False",
    )

    parser.add_argument(
        "--roll_padding",
        type=int,
        default=4,
        help="how many characters of zero padding to add for the roll number. "
        "default: 4",
    )

    parser.add_argument(
        "--scanner_model",
        default="SP-3000",
        help="the scanner model (used to write EXIF data). default: SP-3000",
    )

    parser.add_argument(
        "--convert_bw",
        action="store_true",
        default=False,
        help="interactively select orders to convert to true black-and-white. "
        "default: False",
    )

    args = parser.parse_args()

    # the -G and -n are the default common args, -overwrite_original makes sure
    # to not leave behind the "original" files
    common_args = ["-G", "-n", "-overwrite_original"]
    with exiftool.ExifToolHelper(common_args=common_args) as et:
        cleaner = FrontierCleanerMS01(
            exiftool_client=et,
            frontier_export_path=args.frontier_export_path,
            reorg=args.reorg,
            roll_padding=args.roll_padding,
            convert_bw=args.convert_bw,
        )
        cleaner.clean()


if __name__ == "__main__":
    cli()
