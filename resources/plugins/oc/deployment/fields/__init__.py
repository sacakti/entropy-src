"""Deployment field handlers."""

from .env import EnvFieldHandler
from .image import ImageFieldHandler
from .mounts import MountsFieldHandler
from .mountvolume import MountVolumeFieldHandler

FIELD_HANDLERS = {
    "image": ImageFieldHandler(),
    "mounts": MountsFieldHandler(),
    "mountvolume": MountVolumeFieldHandler(),
    "env": EnvFieldHandler(),
}
