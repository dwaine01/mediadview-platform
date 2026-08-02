"""
MediaDView — Magic-number MIME validation (P0-A3).

Prevents MIME-spoofing on uploads: an attacker who claims
`Content-Type: image/jpeg` while actually uploading an `.exe` or an
HTML/SVG-with-script payload cannot bypass the check any more.

We use the `filetype` library because it is:
    · Pure Python (no libmagic system dep)
    · Small (single import, no runtime hit)
    · Reads only the first ~262 bytes (fast even for large uploads)

Public API:
    · validate_magic_bytes(payload, declared_mime, filename) → normalised MIME
    · ACCEPTED_IMAGE_MIMES / ACCEPTED_VIDEO_MIMES — allowlists

Raises ValueError with a user-friendly message on any inconsistency.
"""
from __future__ import annotations

from typing import Optional

import filetype

ACCEPTED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ACCEPTED_VIDEO_MIMES = {"video/mp4", "video/webm", "video/quicktime"}
ACCEPTED_MIMES = ACCEPTED_IMAGE_MIMES | ACCEPTED_VIDEO_MIMES

# Aliases produced by `filetype` that must be treated as equivalent to
# the "canonical" MIME. e.g. iOS ships JPGs as `image/jpg`.
MIME_ALIASES = {
    "image/jpg": "image/jpeg",
    "image/jp2": "image/jpeg",
}


def normalise_mime(mime: str) -> str:
    m = (mime or "").split(";")[0].strip().lower()
    return MIME_ALIASES.get(m, m)


def validate_magic_bytes(
    payload: bytes,
    declared_mime: str,
    filename: Optional[str] = None,
) -> str:
    """Verify that the first bytes of `payload` match one of the
    accepted MIME types AND (if declared) match the declared type.

    Returns the SERVER-TRUSTED mime type (what filetype detected).

    Raises ValueError on mismatch. Never trusts `declared_mime` alone.
    """
    if not payload:
        raise ValueError("upload is empty")

    # `filetype.guess` reads only first 262 bytes → fast on big uploads.
    kind = filetype.guess(payload)
    if kind is None:
        raise ValueError(
            "could not identify file type from bytes — "
            "may be corrupt or an unsupported format"
        )
    detected_mime = normalise_mime(kind.mime)

    if detected_mime not in ACCEPTED_MIMES:
        raise ValueError(
            f"file appears to be {detected_mime!r} which is not allowed. "
            f"Accepted: images (jpeg/png/webp/gif) or videos (mp4/webm/quicktime)."
        )

    declared_norm = normalise_mime(declared_mime)
    if declared_norm and declared_norm != detected_mime:
        # Also allow certain safe cross-mappings that shouldn't fail
        # (e.g. some browsers send `application/octet-stream` when the
        # user drags a file directly).
        if declared_norm == "application/octet-stream":
            # Client didn't know → trust bytes
            pass
        else:
            raise ValueError(
                f"declared content-type {declared_norm!r} does not match "
                f"file bytes ({detected_mime!r}). Possible MIME spoofing — "
                "upload rejected."
            )

    # Filename sanity check (only used for UX, not security)
    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()
        ext_map = {
            "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "png": "image/png", "webp": "image/webp", "gif": "image/gif",
            "mp4": "video/mp4", "webm": "video/webm",
            "mov": "video/quicktime", "qt": "video/quicktime",
        }
        expected = ext_map.get(ext)
        if expected and expected != detected_mime:
            # Warn only, do not fail — some proxies rewrite extensions.
            # The bytes-based decision is what matters for security.
            pass

    return detected_mime
