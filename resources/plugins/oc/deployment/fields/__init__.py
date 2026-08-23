"""Deployment field handlers."""

from .image import ImageFieldHandler


FIELD_HANDLERS = {
    "image": ImageFieldHandler(),
}
