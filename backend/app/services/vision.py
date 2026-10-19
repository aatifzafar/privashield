from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VisionFinding:
    kind: str
    bbox: tuple[float, float, float, float]
    confidence: float
    source: str


def detect_vision(image: Any) -> tuple[list[VisionFinding], list[str]]:
    """Best-effort QR, photo, and signature hints. Missing OpenCV never blocks text redaction."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return [], ["QR/photo/signature detection unavailable: install the optional OpenCV dependency"]

    try:
        pixels = np.array(image.convert("RGB"))[:, :, ::-1]
        height, width = pixels.shape[:2]
        findings: list[VisionFinding] = []
        qr = cv2.QRCodeDetector()
        decoded, points, _ = qr.detectAndDecode(pixels)
        if points is not None:
            points_array = points.reshape(-1, 2)
            x0 = max(0.0, float(points_array[:, 0].min()))
            y0 = max(0.0, float(points_array[:, 1].min()))
            x1 = min(float(width), float(points_array[:, 0].max()))
            y1 = min(float(height), float(points_array[:, 1].max()))
            if x1 > x0 and y1 > y0:
                findings.append(VisionFinding("qr_code", (x0, y0, x1, y1), 0.45, "vision"))

        cascade_path = getattr(cv2.data, "haarcascades", "") + "haarcascade_frontalface_default.xml"
        cascade = cv2.CascadeClassifier(cascade_path)
        if not cascade.empty():
            gray = cv2.cvtColor(pixels, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24))
            for x, y, face_width, face_height in faces:
                findings.append(
                    VisionFinding(
                        "photo_region",
                        (float(x), float(y), float(x + face_width), float(y + face_height)),
                        0.45,
                        "vision",
                    )
                )

        # Signature-like ink is intentionally conservative and low confidence.
        # It is a review hint, not handwriting recognition.
        gray = cv2.cvtColor(pixels, cv2.COLOR_BGR2GRAY)
        _, threshold = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(threshold, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        signature_candidates: list[tuple[float, tuple[float, float, float, float]]] = []
        for contour in contours:
            x, y, contour_width, contour_height = cv2.boundingRect(contour)
            area = float(contour_width * contour_height)
            if y < height * 0.55 or contour_width < 80 or contour_height < 8 or contour_height > 90:
                continue
            if contour_width / max(1, contour_height) < 2.2 or area > width * height * 0.08:
                continue
            signature_candidates.append((area, (float(x), float(y), float(x + contour_width), float(y + contour_height))))
        if signature_candidates:
            _, signature_box = max(signature_candidates, key=lambda candidate: candidate[0])
            findings.append(VisionFinding("signature_region", signature_box, 0.35, "vision"))
        return findings, []
    except Exception:
        return [], ["QR/photo/signature detection failed; text and OCR detections remain available"]
