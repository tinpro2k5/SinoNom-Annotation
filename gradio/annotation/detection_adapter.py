"""Adapter for character and damage detection, supporting both local models and remote API."""

import json
import logging
from pathlib import Path
from typing import Any, Dict

import httpx

log = logging.getLogger(__name__)


def detect_boxes_remote(image_path: str, api_url: str, timeout: float = 60.0) -> Dict[str, Any]:
    """Call remote API to detect bounding boxes (geometry only for Step 3)."""
    p = Path(image_path)
    if not p.is_file():
        raise FileNotFoundError(f"Image not found: {image_path}")

    url = f"{api_url.rstrip('/')}/detect/boxes"
    log.info("Requesting remote box detection from %s for %s", url, p.name)

    try:
        with open(p, "rb") as f:
            files = {"file": (p.name, f, "image/jpeg")}
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, files=files)
                if resp.status_code != 200:
                    raise RuntimeError(f"Remote detector returned status {resp.status_code}: {resp.text}")
                data = resp.json()
    except httpx.RequestError as exc:
        raise RuntimeError(f"Could not connect to Remote Detection API at {api_url}: {exc}") from exc

    if not data.get("success", False):
        raise RuntimeError(f"Remote detector error: {data.get('detail') or data}")

    raw_boxes = data.get("bounding_boxes", {})
    bounding_boxes: Dict[str, Dict[str, Any]] = {}
    for box_id, box_data in raw_boxes.items():
        coords = [int(round(x)) for x in box_data["bbox"]]
        bounding_boxes[str(box_id)] = {
            "bbox": coords,
            "status": "intact",
            "damage_level": None,
            "unknown": False,
            "unavailable_font": False,
            "expert_prediction": False,
            "suspicious": False,
        }

    reading_order = data.get("reading_order")
    if not reading_order:
        reading_order = list(range(1, len(bounding_boxes) + 1))
    else:
        reading_order = [int(i) for i in reading_order]

    return {
        "image": p.name,
        "bounding_boxes": bounding_boxes,
        "reading_order": reading_order,
    }


def detect_damage_remote(image_path: str, boxes_dict: Dict[str, list], api_url: str, timeout: float = 60.0) -> Dict[str, Any]:
    """Call remote API to classify damage on finalized bounding boxes (for Step 4)."""
    p = Path(image_path)
    if not p.is_file():
        raise FileNotFoundError(f"Image not found: {image_path}")

    url = f"{api_url.rstrip('/')}/detect/damage"
    log.info("Requesting remote damage detection from %s for %d boxes", url, len(boxes_dict))

    try:
        with open(p, "rb") as f:
            files = {"file": (p.name, f, "image/jpeg")}
            data_payload = {"boxes": json.dumps(boxes_dict)}
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, files=files, data=data_payload)
                if resp.status_code != 200:
                    raise RuntimeError(f"Remote damage detector returned status {resp.status_code}: {resp.text}")
                result = resp.json()
    except httpx.RequestError as exc:
        raise RuntimeError(f"Could not connect to Remote Detection API at {api_url}: {exc}") from exc

    if not result.get("success", False):
        raise RuntimeError(f"Remote damage detector error: {result.get('detail') or result}")

    return result


def detect(image_path, options):
    """Entry point for Step 3 detection."""
    api_url = getattr(options, "detection_api_url", None)
    if api_url:
        return detect_boxes_remote(image_path, api_url)

    from pathlib import Path
    from text_detection import run_detection_pipeline
    from text_detection.main import build_detection_document
    return build_detection_document(Path(image_path), run_detection_pipeline(str(image_path), options))
