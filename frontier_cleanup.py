from pathlib import Path
from datetime import datetime, timedelta
from wand.image import Image

import argparse
import re


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
    IMAGE_DIR_PATTERN = \
        r"(?P<order_id>.{1,10})" \
        r"(?P<roll_number>\d{6})"
    IMAGE_DIR_GLOB_PATTERN = "*" + "[0-9]" * 6
    IMAGE_NAME_PATTERN = \
        r"(?P<frame_number>\d{6})"

    def __init__(self,
                 search_path=None,
                 reorg=False,
                 roll_padding=4,
                 frame_padding=4):
        """
        search_path is a str representing the path to search for images to fix.
        If not provided, search_path will be the current working directory.
        reorg is whether to reorganize all scans into directories based on
        order id and date. Defaults to False.
        roll_padding is how many characters of zero padding to add for the
        roll number.
        frame_padding is how many characters of zero padding to add for the
        frame number.
        """
        if not search_path:
            self.search_path = Path.cwd()
        else:
            self.search_path = Path(search_path)

        self.reorg = reorg
        self.roll_padding = roll_padding
        self.frame_padding = frame_padding
        self.image_name_matcher = re.compile(self.IMAGE_NAME_PATTERN)

    def clean(self):
        base_timestamp = datetime.now()
        for index, image_dir in enumerate(self.find_all_image_dirs()):
            try:
                self.convert_bmps_to_tifs(image_dir)
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
        if not self.search_path.is_dir():
            raise ValueError("given path is not a directory")

        found_dirs += sorted(
            filter(lambda x: x.is_dir(),
                   self.search_path.glob(self.IMAGE_DIR_GLOB_PATTERN)
            )
        )

        return found_dirs

    def convert_bmps_to_tifs(self, images_dir):
        """
        Converts all BMP files to compressed TIF files (with zip compression).
        images_dir is a path object that represents the directory of images to
        operate on
        """
        print("converting bmps to tifs...")
        for image_path in sorted(images_dir.glob("*")):
            filename = image_path.stem  # the filename without extension
            suffix = image_path.suffix  # the extension including the .

            if str(suffix).lower() != ".bmp" or not image_path.is_file():
                continue

            print(f"converting {image_path}")
            bmp_image = Image(filename=image_path)
            with bmp_image.convert("tif") as tif_image:
                tif_image.compression = "lzw"
                tif_filepath = image_path.with_suffix(".tif")
                tif_image.save(tif_filepath)

            # delete original bmps
            image_path.unlink()

    def rename_images(self, images_dir):
        """
        Renames the images in the images_dir directory in the format:
            R{roll_number}F{frame_number}.jpg (or .tif)

        Since the Frontier doesn't seem to save the frame names as read by the
        DX code reader, its filenames are always frame numbers. We can rename
        these filenames to be sequential since the Frontier sometimes numbers
        these wrong, skipping frames 02-06 often.
        images_dir is a path object that represents the directory of images to
        operate on
        """
        images_glob = sorted(images_dir.glob("*"))
        if not images_glob:
            print(f"No images found, skipping: {images_dir}")
            return

        # the roll number can be extracted from the directory name
        match = re.match(self.IMAGE_DIR_PATTERN, images_dir.name)
        roll_number = match.group("roll_number")
        # convert roll number to an int, and then zero pad it as desired
        formatted_roll_number = \
            f"{int(roll_number):0>{self.roll_padding}d}"

        first_image_path = images_glob[0]
        if self.reorg:
            # the order id can be extracted from the directory name
            order_id = match.group("order_id")

            # find the date from the mtime of the first image
            first_image_mtime = datetime.fromtimestamp(
                first_image_path.stat().st_mtime)
            date_dir_number = first_image_mtime.strftime("%Y%m%d")

            # the parent dir that the image_dir is in
            parent_dir = first_image_path.parent.parent

            # destination dir to save the images to
            dest_dir = parent_dir / \
                    order_id / date_dir_number / formatted_roll_number
        else:
            # reuse the same directory
            dest_dir = first_image_path.parent

        print(f"saving to: {dest_dir}")

        for image_number, image_path in enumerate(images_glob):
            filename = image_path.stem  # the filename without extension
            suffix = image_path.suffix  # the extension including the .

            if str(suffix).lower() not in (".jpg", ".tif", ".bmp") or \
                    not image_path.is_file():
                continue

            match = self.image_name_matcher.match(filename)
            if not match:
                raise ValueError(
                    f"image filename doesn't match expected format: "
                    f"{image_path}")

            frame_number = image_number + 1  # since image_number is 0-indexed
            new_filename = f"R{formatted_roll_number}" \
                f"F{int(frame_number):0>{self.frame_padding}d}"

            new_filepath = dest_dir / f"{new_filename}{suffix}"
            print(f"{image_path.name} => {new_filename}{suffix}")
            dest_dir.mkdir(parents=True, exist_ok=True)
            image_path.rename(new_filepath)

        if self.reorg:
            # delete the original directory now
            try:
                first_image_path.parent.rmdir()
            except OSError as err:
                print(f"Directory not empty, skipping deletion: {images_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sanitizes Frontier scan files by renaming images and "
        "correcting EXIF metadata."
    )
    parser.add_argument(
        "search_path", nargs="?", default=None,
        help="The path to search for Frontier scan files. If not provided, "
        "will use current working directory."
    )

    parser.add_argument(
        "--reorg", action="store_true", default=False,
        help="whether to reorganize the scans into order and date directories "
        "or not. default: False"
    )

    parser.add_argument(
        "--roll_padding", type=int, default=4,
        help="how many characters of zero padding to add for the roll number. "
        "default: 4"
    )

    parser.add_argument(
        "--frame_padding", type=int, default=2,
        help="how many characters of zero padding to add for the frame "
        "number. default: 2"
    )

    args = parser.parse_args()

    # the -G and -n are the default common args, -overwrite_original makes sure
    # to not leave behind the "original" files
    common_args = ["-G", "-n", "-overwrite_original"]
    cleaner = FrontierCleaner(
        search_path=args.search_path,
        reorg=args.reorg,
        roll_padding=args.roll_padding,
        frame_padding=args.frame_padding)
    cleaner.clean()
