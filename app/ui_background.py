from __future__ import annotations

from dataclasses import dataclass


BACKGROUND_SCALE_MODES = ("cover", "contain", "stretch", "tile")


@dataclass(frozen=True, slots=True)
class BackgroundRect:
    x: int
    y: int
    width: int
    height: int


def background_rect(
    image_width: int,
    image_height: int,
    canvas_width: int,
    canvas_height: int,
    mode: str,
) -> BackgroundRect:
    """Return a centered draw rectangle for a non-tiled background image."""
    canvas_width = max(0, canvas_width)
    canvas_height = max(0, canvas_height)
    if mode == "stretch" or image_width <= 0 or image_height <= 0:
        return BackgroundRect(0, 0, canvas_width, canvas_height)

    width_ratio = canvas_width / image_width
    height_ratio = canvas_height / image_height
    ratio = max(width_ratio, height_ratio) if mode == "cover" else min(width_ratio, height_ratio)
    width = round(image_width * ratio)
    height = round(image_height * ratio)
    return BackgroundRect((canvas_width - width) // 2, (canvas_height - height) // 2, width, height)


def normalize_background_scale_mode(value: str) -> str:
    return value if value in BACKGROUND_SCALE_MODES else "cover"


__all__ = ["BACKGROUND_SCALE_MODES", "BackgroundRect", "background_rect", "normalize_background_scale_mode"]
