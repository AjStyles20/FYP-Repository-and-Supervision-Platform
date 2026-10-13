"""Opening a stored file for a download view, with a clear page (not a server error) when it is gone.

A file's database row can outlive the file on disk: a restore without the media folder, a disk
clean-up, or a move to another server. Then the person sees what happened and who can fix it.
"""

import logging

from django.shortcuts import render

logger = logging.getLogger(__name__)


def open_stored_file(request, stored, what="file"):
    """Return the open file, or (None, response) with a 404 page explaining the file is missing."""
    try:
        return stored.open("rb"), None
    except (FileNotFoundError, OSError):
        logger.warning("Stored %s is missing on disk: %s", what, stored.name)
        response = render(request, "file_missing.html", {"what": what}, status=404)
        return None, response
