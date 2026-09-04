"""
Static URLs for image filenames typed by hand in the admin.

`static()` under the hashed-manifest storage that production uses raises for a
path the manifest does not know, so one mistyped filename on a product or a
category would take down every page that shows it, the home page included.
Every admin-typed image path goes through `image_url()` instead, which checks
that the file exists and otherwise serves the branded placeholder.
"""

from django.conf import settings
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import staticfiles_storage
from django.templatetags.static import static

PLACEHOLDER = "img/placeholder.svg"


def static_file_exists(path):
    """True if `path` is a static file this deployment can serve."""
    if settings.DEBUG:
        return finders.find(path) is not None
    # Manifest storage: the manifest is the authority on what was collected.
    manifest = getattr(staticfiles_storage, "hashed_files", None)
    if manifest is not None:
        return path in manifest
    return finders.find(path) is not None


def image_url(path):
    """`static(path)`, or the placeholder's URL when the file is missing."""
    if path and static_file_exists(path):
        return static(path)
    return static(PLACEHOLDER)
