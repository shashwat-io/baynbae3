"""Size vocabulary shared by catalog, cart and admin."""

SIZE_CHOICES = [
    ("XS", "XS"),
    ("S", "S"),
    ("M", "M"),
    ("L", "L"),
    ("XL", "XL"),
    ("FREE", "Free size"),
]
SIZE_ORDER = {code: i for i, (code, _) in enumerate(SIZE_CHOICES)}
FITTED_SIZES = ["XS", "S", "M", "L", "XL"]

# The size guide table (PROJECT.md S17): sizes XS-XL, centimetres only, and
# every measurement cell an owner placeholder until the owner supplies real
# numbers. The figures that used to sit here were invented, and in inches.
SIZE_GUIDE_COLUMNS = ["Bust", "Waist", "Hip", "Length"]
SIZE_GUIDE = [
    {"size": size, "cells": [f"{size} {column.lower()} in cm" for column in SIZE_GUIDE_COLUMNS]}
    for size in FITTED_SIZES
]


def size_label(code):
    return dict(SIZE_CHOICES).get(code, code)
