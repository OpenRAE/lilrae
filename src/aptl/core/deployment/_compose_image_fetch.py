"""Docker Compose image pre-fetch / staged-image verification.

Split out of ``docker_compose.py`` to keep that module within the S104
file-length budget. ``pull_images`` makes images available before
``compose up`` so a missing image fails as a bounded warning rather than
mid-start. It inspects the selected daemon first: an image already present is
used as is, as Compose itself would use it, so a warm start needs no registry
(#953). Offline-staged mode never pulls. A ``name:tag@sha256:…`` reference
is realized digest first, and its tag is then pointed at that image.
"""

from __future__ import annotations

from aptl.utils.logging import get_logger

log = get_logger("deployment.docker_compose")


class ComposeImageFetchMixin:
    """Pre-pull or verify staged container images for the Compose backend."""

    def pull_images(self, images: list[str]) -> list[str]:
        """Pull each image the selected daemon does not already hold.

        A ``name:tag@sha256:…`` reference makes the tag resolve to that
        digest; offline-staged mode verifies the staged tag.

        Args:
            images: List of image references to make available.

        Returns:
            List of warning messages for images that are missing offline or
            failed to pull (non-fatal online).
        """
        warnings: list[str] = []
        for image in images:
            try:
                warning = (
                    self._fetch_pinned_image(image)
                    if "@sha256:" in image
                    else self._fetch_one_image(image)
                )
            except OSError as exc:
                warning = self._image_fetch_exception(image, exc)
                log.warning(warning)
            if warning is not None:
                warnings.append(warning)
        return warnings

    def _fetch_one_image(self, image: str) -> str | None:
        """Use a local image, or pull it online; return a warning on failure."""

        present = self._run(["docker", "image", "inspect", image])
        if present.returncode == 0:
            log.info(
                "%s %s",
                "Verified staged image" if self._offline_staged else "Using local image",
                image,
            )
            return None
        if self._offline_staged:
            return self._image_fetch_failure(image, present.stderr)
        return self._pull_one_image(image)

    def _fetch_pinned_image(self, pinned: str) -> str | None:
        """Point a ``name:tag@sha256:…`` reference's tag at its pinned digest.

        Containers keep running by the tag. Online, the digest is used if the
        daemon holds it and pulled otherwise, and the tag is then pointed at it.
        Offline-staged mode verifies only the staged tag: ``docker save`` and
        ``docker load`` need not keep a registry digest.
        """

        tag = pinned.partition("@")[0]
        if self._offline_staged:
            return self._fetch_one_image(tag)
        present = self._run(["docker", "image", "inspect", pinned])
        warning = None if present.returncode == 0 else self._pull_one_image(pinned)
        if warning is None:
            tagged = self._run(["docker", "tag", pinned, tag])
            if tagged.returncode != 0:
                warning = f"Failed to tag {pinned} as {tag}: {tagged.stderr.strip()}"
                log.warning(warning)
        return warning

    def _pull_one_image(self, image: str) -> str | None:
        """Pull one image the daemon lacks; return a warning on failure."""

        result = self._run(["docker", "pull", image])
        if result.returncode != 0:
            return self._image_fetch_failure(image, result.stderr)
        log.info("Pulled %s", image)
        return None

    def _image_fetch_failure(self, image: str, stderr: str) -> str:
        """Return and log one bounded image verification failure."""

        if self._offline_staged:
            message = f"Required staged image is missing: {image}"
        else:
            message = f"Failed to pull {image}: {stderr.strip()}"
        log.warning(message)
        return message

    def _image_fetch_exception(self, image: str, exc: OSError) -> str:
        """Return one image operation failure caused by a local tool error."""

        if self._offline_staged:
            return f"Required staged image could not be inspected: {image}"
        return f"Failed to pull {image}: {exc}"
