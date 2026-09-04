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

# Body measurements in inches, used on the size guide page.
SIZE_CHART = [
    {"size": "XS", "bust": "32", "waist": "26", "hip": "35", "uk": "6"},
    {"size": "S", "bust": "34", "waist": "28", "hip": "37", "uk": "8"},
    {"size": "M", "bust": "36", "waist": "30", "hip": "39", "uk": "10"},
    {"size": "L", "bust": "38", "waist": "32", "hip": "41", "uk": "12"},
    {"size": "XL", "bust": "40–42", "waist": "34–36", "hip": "43–45", "uk": "14–16"},
]


def size_label(code):
    return dict(SIZE_CHOICES).get(code, code)
