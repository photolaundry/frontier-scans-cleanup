from pathlib import Path
from datetime import datetime, timedelta

import argparse
import exiftool
import re


# assume folder structure:
# 000001007466/  <- order + roll number
#   000001.jpg  <- frame number
#   000002.jpg  <- frame number
#   000003.jpg  <- frame number
#   ...
# 000001007467/
#   ...
# 000001007468/
#   ...


class FrontierCleaner:
    EXIF_DATETIME_STR_FORMAT = "%Y:%m:%d %H:%M:%S"
    EXIFTOOL_SUCCESSFUL_WRITE_MESSAGE = "1 image files updated"
    IMAGE_DIR_PATTERN = \
        r"(?P<order_number>\d{6})" \
        r"(?P<roll_number>\d{6})"
    IMAGE_DIR_GLOB_PATTERN = "[0-9]" * (6 + 6)
    IMAGE_NAME_PATTERN = \
        r"(?P<frame_number>\d{6})"

    def __init__(self,
                 exiftool_client,
                 search_path=None,
                 roll_padding=4,
                 frame_padding=4):
        """
        exiftool_client is a exiftool.ExifToolHelper object that will be used
        to perform all EXIF modifications required.
        search_path is a str representing the path to search for images to fix.
        If not provided, search_path will be the current working directory.
        roll_padding is how many characters of zero padding to add for the
        roll number
        frame_padding is how many characters of zero padding to add for the
        frame number
        """
        self.exiftool = exiftool_client

        if not search_path:
            self.search_path = Path.cwd()
        else:
            self.search_path = Path(search_path)

        self.roll_padding = roll_padding
        self.frame_padding = frame_padding
        self.image_name_matcher = re.compile(self.IMAGE_NAME_PATTERN)

    def clean(self):
        base_timestamp = datetime.now()
        for index, image_dir in enumerate(self.find_all_image_dirs()):
            try:
                # make sure to give each image dir its own timestamp to not
                # collide by separting their timestamps 1 second apart
                self.fix_timestamps(image_dir,
                                    base_timestamp + timedelta(seconds=index))
                self.rename_images(image_dir)
            except ValueError as e:
                print(e)
                print(f"skipping directory {image_dir}...")

    def find_all_image_dirs(self):
        """
        The Frontier exports images into a dir for each roll, where the
        directory name is the 6-digit order number followed by the 6-digit roll
        number.
        So we just need to find all directories that are named with 12 digits.
        """
        found_dirs = []
        # if the search_path itself is a image dir, add it to beginning of
        # results
        if self.search_path.is_dir() and \
                re.match(self.IMAGE_DIR_PATTERN, self.search_path.name):
            found_dirs.append(self.search_path)
        found_dirs += sorted(
            self.search_path.glob("**/" + self.IMAGE_DIR_GLOB_PATTERN))

        return found_dirs

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
        # the roll number can be extracted from the directory name
        match = re.match(self.IMAGE_DIR_PATTERN, images_dir.name)
        roll_number = match.group("roll_number")
        for image_number, image_path in enumerate(sorted(images_dir.glob("*"))):
            filename = image_path.stem  # the filename without extension
            prefix = image_path.parent  # the full path of the parent dir
            suffix = image_path.suffix  # the extension including the .

            if str(suffix).lower() not in (".jpg", ".tif") or \
                    not image_path.is_file():
                continue

            match = self.image_name_matcher.match(filename)
            if not match:
                raise ValueError(
                    f"image filename doesn't match expected format: "
                    f"{image_path}")

            # convert roll number to an int, and then zero pad it as desired
            formatted_roll_number = \
                f"{int(roll_number):0>{self.roll_padding}d}"
            frame_number = image_number + 1  # since image_number is 0-indexed
            new_filename = f"R{formatted_roll_number}" \
                f"F{int(frame_number):0>{self.frame_padding}d}"

            new_filepath = prefix.joinpath(f"{new_filename}{suffix}")
            print(f"{image_path.name} => {new_filename}{suffix}")
            image_path.rename(new_filepath)

    def fix_timestamps(self, images_dir, base_timestamp):
        """
        Adds the DateTimeOriginal EXIF tag to all images, using the first
        file's timestamp as a starting point. This fixes the issue where
        rotating a file in Finder or Adobe Bridge will adjust the image's
        modified timestamp, messing up programs that sort by Capture Time
        (such as Lightroom).

        We set the capture times of the files as such:
            1st image gets the same capture time as its file modified time.
            2nd image gets the 1st image's capture time, but +1 millisecond.
            3rd image gets the 1st image's capture time, but +2 milliseconds.

        We can't just save each image's modified time as its capture time
        because we can't guarantee that the Frontier saves the images in
        sequential order, sometimes a later frame gets saved before an earlier
        one.

        The adding of milliseconds helps preserve the sorting order in programs
        like Lightroom since the ordering is also enforced by the capture time
        set.

        images_dir is a path object that represents the directory of images to
        operate on.
        base_timestamp is the timestamp that this directory's images should
        base their creation timestamps on. Each image will use a different
        SubSec (millisecond) of that timestamp as its creation timestamp.
        (FIXME: this assumes there's at most 1000 images in the directory).
        """
        first_image_mtime = None
        image_num = 0
        for image_path in sorted(images_dir.glob("*")):
            filename = image_path.stem  # the filename without extension
            suffix = image_path.suffix  # the extension including the .

            if str(suffix).lower() not in (".jpg", ".tif") or \
                    not image_path.is_file():
                continue

            match = self.image_name_matcher.match(filename)
            if not match:
                raise ValueError(
                    f"image filename doesn't match expected format: "
                    f"{image_path}")

            # only bump counter for jpgs and tiffs
            image_num += 1

            if not first_image_mtime:
                first_image_mtime = datetime.fromtimestamp(
                    image_path.stat().st_mtime)

            # image ordering is preserved in the capture time saved,
            # see above docstring
            datetime_original = first_image_mtime.strftime(
                self.EXIF_DATETIME_STR_FORMAT)
            datetime_digitized = first_image_mtime.strftime(
                self.EXIF_DATETIME_STR_FORMAT)
            # There's 3 decimal places for the milliseconds, so zero-pad to 3
            subsec_time_original = f"{image_num - 1:0>3d}"
            subsec_time_digitized = f"{image_num - 1:0>3d}"

            tags_to_write = {
                "EXIF:DateTimeOriginal": datetime_original,
                "EXIF:DateTimeDigitized": datetime_digitized,
                "EXIF:SubSecTimeOriginal": subsec_time_original,
                "EXIF:SubSecTimeDigitized": subsec_time_digitized,
            }

            print(f"{image_path.name} getting datetime: "
                  f"{datetime_original}:"
                  f"{subsec_time_original}")

            try:
                result = self.exiftool.set_tags(str(image_path), tags_to_write)
            except exiftool.exceptions.ExifToolExecuteError as err:
                print(f"exiftool error while updating timestamps on image: "
                      f"{image_path}")
                print(f"error: {err.stdout}")
            else:
                result = result.strip()
                if result != self.EXIFTOOL_SUCCESSFUL_WRITE_MESSAGE:
                    print(f"failed to update timestamps on image: "
                          f"{image_path}")
                    print(f"exiftool: {result}")


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
    with exiftool.ExifToolHelper(common_args=common_args) as et:
        cleaner = FrontierCleaner(
            exiftool_client=et,
            search_path=args.search_path,
            roll_padding=args.roll_padding,
            frame_padding=args.frame_padding)
        cleaner.clean()
