#!/usr/bin/env python3

# Rename all JPEGs in the current directory by their date taken
import os
from PIL import Image

def rename_jpegs_by_date():
    for filename in os.listdir('.'):
        if filename.lower().endswith('.jpg') or filename.lower().endswith('.jpeg'):
            try:
                with Image.open(filename) as img:
                    exif_data = img._getexif()
                    if exif_data and 36867 in exif_data:
                        date_taken = exif_data[36867]
                        new_filename = f"{date_taken.replace(':', '').replace(' ', '_')}.jpg"
                        os.rename(filename, new_filename)
            except Exception as e:
                print(f"Error processing {filename}: {e}")

rename_jpegs_by_date()