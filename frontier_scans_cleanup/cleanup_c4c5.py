import argparse
import itertools
import re
from datetime import datetime
from pathlib import Path

import exiftool
from wand.image import Image

# assume folder structure:
# YourName007466/  <- order id + roll number
#   000001.jpg  <- frame number
#   000002.jpg  <- frame number
#   000003.jpg  <- frame number
#   ...
# YourName007467/
#   ...
# OtherName007468/
#   ...


class FrontierCleaner:
    EXIF_DATETIME_STR_FORMAT = "%Y:%m:%d %H:%M:%S"
    EXIFTOOL_SUCCESSFUL_WRITE_MESSAGE = "1 image files updated"
    IMAGE_DIR_PATTERN = r"(?P<order_id>.{1,10})(?P<roll_number>\d{6})"
    IMAGE_DIR_GLOB_PATTERN = "*" + "[0-9]" * 6
    IMAGE_NAME_PATTERN = r"(?P<frame_number>\d{6})"

    def __init__(
        self,
        exiftool_client,
        frontier_export_path=None,
        reorg=False,
        roll_padding=4,
        frame_padding=2,
    ):
        """
        exiftool_client is a exiftool.ExifToolHelper object that will be used
        to perform all EXIF modifications required.
        frontier_export_path is the path that the Frontier exporting software
        directly exports to. If not provided, frontier_export_path will default
        to the current working directory.
        reorg is whether to reorganize all scans into directories based on
        order id and date. Defaults to False.
        roll_padding is how many characters of zero padding to use for the
        roll number.
        frame_padding is how many characters of zero padding to use for the
        frame number.
        """
        self.exiftool = exiftool_client

        if not frontier_export_path:
            self.frontier_export_path = Path.cwd()
        else:
            self.frontier_export_path = Path(frontier_export_path)

        self.reorg = reorg
        self.roll_padding = roll_padding
        self.frame_padding = frame_padding
        self.image_name_matcher = re.compile(self.IMAGE_NAME_PATTERN)

    def clean(self):
        for image_dir in self.find_all_image_dirs():
            try:
                self.convert_bmps_to_tifs(image_dir)
                self.fix_timestamps(image_dir)
                self.rename_images(image_dir)
            except ValueError as e:
                print(e)
                print(f"skipping directory {image_dir}...")

    def find_all_image_dirs(self):
        """
        The Frontier exports images into a dir for each roll, where the
        directory name is the order id (up to 10 of any character) followed by
        the 6-digit roll number.
        """
        found_dirs = []
        if not self.frontier_export_path.is_dir():
            raise ValueError("given path is not a directory")

        found_dirs += sorted(
            filter(
                lambda x: x.is_dir(),
                self.frontier_export_path.glob(self.IMAGE_DIR_GLOB_PATTERN),
            )
        )

        return found_dirs

    def convert_bmps_to_tifs(self, images_dir):
        """
        Converts all BMP files to compressed TIF files (with lzw compression).
        images_dir is a path object that represents the directory of images to
        operate on
        """
        print("converting bmps to tifs...")
        for image_path in sorted(images_dir.glob("*")):
            _ = image_path.stem  # the filename without extension
            suffix = image_path.suffix  # the extension including the .

            if str(suffix).lower() != ".bmp" or not image_path.is_file():
                continue

            print(f"converting {image_path}")
            bmp_image = Image(filename=image_path)
            with bmp_image.convert("tif") as tif_image:
                tif_image.compression = "lzw"
                tif_filepath = image_path.with_suffix(".tif")
                tif_image.save(filename=tif_filepath)

            # delete original bmps
            image_path.unlink()

    def rename_images(self, images_dir):
        """
        Renames the images in the images_dir directory in the format:
            R{roll_number}F{frame_number}.jpg (or .tif)

        Since the C4/C5 software doesn't seem to save the frame names as read
        by the DX code reader, its filenames are always frame numbers. We can
        rename these filenames to be sequential since the Frontier sometimes
        numbers these wrong, skipping frames 02-06 often.
        images_dir is a path object that represents the directory of images to
        operate on
        """
        images_glob = sorted(
            itertools.chain(
                images_dir.glob("*.jpg"),
                images_dir.glob("*.bmp"),
                images_dir.glob("*.JPG"),
                images_dir.glob("*.BMP"),
            )
        )
        if not images_glob:
            print(f"No images found, skipping: {images_dir}")
            return

        # the roll number can be extracted from the directory name
        dir_match = re.match(self.IMAGE_DIR_PATTERN, images_dir.name)
        if not dir_match:
            raise ValueError(
                f"image dir doesn't match expected format: {images_dir}"
            )
        roll_number = dir_match.group("roll_number")
        # convert roll number to an int, and then zero pad it as desired
        formatted_roll_number = f"{int(roll_number):0>{self.roll_padding}d}"

        first_image_path = images_glob[0]
        if self.reorg:
            # the order id can be extracted from the directory name
            order_id = dir_match.group("order_id")

            # find the date from the mtime of the first image
            first_image_mtime = datetime.fromtimestamp(
                first_image_path.stat().st_mtime
            )
            date_dir_number = first_image_mtime.strftime("%Y%m%d")

            # destination dir to save the images to (same dir as Frontier)
            dest_dir = (
                self.frontier_export_path
                / order_id
                / date_dir_number
                / formatted_roll_number
            )
        else:
            # reuse the same directory as the original image
            dest_dir = first_image_path.parent

        print(f"saving to: {dest_dir}")

        for image_number, image_path in enumerate(images_glob):
            filename = image_path.stem  # the filename without extension
            suffix = image_path.suffix  # the extension including the .

            if not image_path.is_file():
                continue

            img_match = self.image_name_matcher.match(filename)
            if not img_match:
                raise ValueError(
                    f"image filename doesn't match expected format: "
                    f"{image_path}"
                )

            frame_number = image_number + 1  # since image_number is 0-indexed
            new_filename = (
                f"R{formatted_roll_number}"
                f"F{int(frame_number):0>{self.frame_padding}d}"
            )

            new_filepath = dest_dir / f"{new_filename}{suffix}"
            print(f"{image_path.name} => {new_filename}{suffix}")
            dest_dir.mkdir(parents=True, exist_ok=True)
            image_path.rename(new_filepath)

        if self.reorg:
            # delete the images_dir now that all images are renamed and moved
            try:
                images_dir.rmdir()
            except OSError:
                print(f"Directory not empty, skipping deletion: {images_dir}")

    def fix_timestamps(self, images_dir):
        """
        Adds the DateTimeOriginal EXIF tag to all images, based on the
        filesystem modified timestamp of the file. This fixes the issue where
        rotating a file in Finder or Adobe Bridge will adjust the image's
        modified timestamp, messing up programs that sort by Capture Time
        (such as Lightroom).

        We set the capture times of the files as such:
            1st image gets the same capture time as its file modified time.
            2nd image gets the 1st image's capture time, but +1 millisecond.
            3rd image gets the 1st image's capture time, but +2 milliseconds.

        We can't just save each image's modified time as its capture time
        because the software doesn't guarantee that it saves the images in
        sequential order, sometimes a later frame gets saved before an earlier
        one.

        The adding of milliseconds helps preserve the sorting order in programs
        like Lightroom since the ordering is also enforced by the capture time
        set.  If all files got the same capture time, and we were saving the
        frame name in the filenames, we would get cases where ###, 00, 0, E, XA
        frames get out of order, because LR would have to use filename to sort
        since they'd all have the same capture time.

        images_dir is a path object that represents the directory of images to
        operate on.
        """
        first_image_mtime = None
        image_num = 0
        images_glob = sorted(
            itertools.chain(
                images_dir.glob("**/*.jpg"),
                images_dir.glob("**/*.tif"),
                images_dir.glob("**/*.bmp"),
                images_dir.glob("**/*.JPG"),
                images_dir.glob("**/*.TIF"),
                images_dir.glob("**/*.BMP"),
            )
        )
        for image_path in images_glob:
            filename = image_path.stem  # the filename without extension

            if str(filename).startswith(".") or not image_path.is_file():
                continue

            img_match = self.image_name_matcher.match(filename)
            if not img_match:
                raise ValueError(
                    f"image filename doesn't match expected format: "
                    f"{image_path}"
                )

            # only bump counter for images that match
            image_num += 1

            if not first_image_mtime:
                first_image_mtime = datetime.fromtimestamp(
                    image_path.stat().st_mtime
                )

            # image ordering is preserved in the capture time saved,
            # see above docstring
            datetime_original = first_image_mtime.strftime(
                self.EXIF_DATETIME_STR_FORMAT
            )
            datetime_digitized = first_image_mtime.strftime(
                self.EXIF_DATETIME_STR_FORMAT
            )
            # There's 3 decimal places for the milliseconds, so zero-pad to 3
            subsec_time_original = f"{image_num - 1:0>3d}"
            subsec_time_digitized = f"{image_num - 1:0>3d}"

            tags_to_write = {
                "EXIF:DateTimeOriginal": datetime_original,
                "EXIF:DateTimeDigitized": datetime_digitized,
                "EXIF:SubSecTimeOriginal": subsec_time_original,
                "EXIF:SubSecTimeDigitized": subsec_time_digitized,
            }

            print(
                f"{image_path.name} getting datetime: "
                f"{datetime_original}:"
                f"{subsec_time_original}"
            )

            try:
                result = self.exiftool.set_tags(str(image_path), tags_to_write)
            except exiftool.exceptions.ExifToolExecuteError as err:
                print(
                    f"exiftool error while updating timestamps on image: "
                    f"{image_path}"
                )
                print(f"error: {err.stdout}")
            else:
                result = result.strip()
                if result != self.EXIFTOOL_SUCCESSFUL_WRITE_MESSAGE:
                    print(
                        f"failed to update timestamps on image: "
                        f"{image_path}"
                    )
                    print(f"exiftool: {result}")


def cli():
    parser = argparse.ArgumentParser(
        description="Sanitizes Frontier scan files by renaming images and "
        "optionally reorganizes them into order id directories."
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
        "--frame_padding",
        type=int,
        default=2,
        help="how many characters of zero padding to add for the frame "
        "number. default: 2",
    )

    args = parser.parse_args()

    # the -G and -n are the default common args, -overwrite_original makes sure
    # to not leave behind the "original" files
    common_args = ["-G", "-n", "-overwrite_original"]
    with exiftool.ExifToolHelper(common_args=common_args) as et:
        cleaner = FrontierCleaner(
            exiftool_client=et,
            frontier_export_path=args.frontier_export_path,
            reorg=args.reorg,
            roll_padding=args.roll_padding,
            frame_padding=args.frame_padding,
        )
        cleaner.clean()


if __name__ == "__main__":
    cli()
