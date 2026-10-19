from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable

from .extraction import PageContent, WordBox
from .vision import VisionFinding


@dataclass
class Detection:
    kind: str
    page: int
    bbox: tuple[float, float, float, float]
    confidence: float
    source: str
    value: str = ""
    public_id: str = ""


PAN_RE = re.compile(r"(?<![A-Z0-9])[A-Z]{5}[0-9]{4}[A-Z](?![A-Z0-9])", re.IGNORECASE)
AADHAAR_RE = re.compile(r"(?<!\d)(?:\d{4}[ -]?\d{4}[ -]?\d{4})(?!\d)")
PHONE_RE = re.compile(r"(?<!\d)(?:(?:\+|00)91[ -]?)?(?:0[ -]?)?[6-9]\d{9}(?!\d)")
EMAIL_RE = re.compile(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])", re.IGNORECASE)
DATE_RE = re.compile(
    r"(?<!\d)(?:(?:0?[1-9]|[12]\d|3[01])[-/.](?:0?[1-9]|1[0-2])[-/.](?:19|20)\d{2}|(?:19|20)\d{2}[-/.](?:0?[1-9]|1[0-2])[-/.](?:0?[1-9]|[12]\d|3[01]))(?!\d)"
)
PIN_RE = re.compile(r"(?<!\d)[1-9]\d{5}(?!\d)")
PASSPORT_RE = re.compile(r"(?<![A-Z0-9])[A-Z][0-9]{7}(?![A-Z0-9])", re.IGNORECASE)
IFSC_RE = re.compile(r"(?<![A-Z0-9])[A-Z]{4}0[A-Z0-9]{6}(?![A-Z0-9])", re.IGNORECASE)
BANK_ACCOUNT_RE = re.compile(
    r"\b(?:bank\s+)?(?:account(?:\s*(?:no|number))?|a\s*/\s*c)\b[^\d\n]{0,24}(\d(?:[ -]?\d){5,17})(?!\d)",
    re.IGNORECASE,
)


def verhoeff_checksum(value: str) -> bool:
    digits = [int(char) for char in value if char.isdigit()]
    if len(digits) != 12:
        return False
    multiplication = (
        (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
        (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
        (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
        (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
        (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
        (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
        (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
        (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
        (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
        (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
    )
    permutation = (
        (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
        (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
        (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
        (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
        (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
        (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
        (2, 7, 9, 3, 8, 0, 6, 5, 1, 4),
        (7, 0, 4, 6, 9, 1, 3, 2, 8, 5),
        (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
        (1, 2, 3, 4, 5, 6, 7, 8, 9, 0),
    )
    check = 0
    for index, digit in enumerate(reversed(digits)):
        check = multiplication[check][permutation[(index + 1) % 8][digit]]
    return check == 0


def _page_text_and_spans(words: list[WordBox]) -> tuple[str, list[tuple[int, int, WordBox]]]:
    ordered = sorted(words, key=lambda word: (word.line_id, word.bbox[1], word.bbox[0]))
    pieces: list[str] = []
    spans: list[tuple[int, int, WordBox]] = []
    position = 0
    previous_line: tuple[int, int] | None = None
    for word in ordered:
        if previous_line is not None:
            separator = "\n" if word.line_id != previous_line else " "
            pieces.append(separator)
            position += len(separator)
        start = position
        pieces.append(word.text)
        position += len(word.text)
        spans.append((start, position, word))
        previous_line = word.line_id
    return "".join(pieces), spans


def _bbox_for_span(spans: list[tuple[int, int, WordBox]], start: int, end: int) -> tuple[float, float, float, float] | None:
    matching = [word.bbox for word_start, word_end, word in spans if word_end > start and word_start < end]
    if not matching:
        return None
    return (
        min(box[0] for box in matching),
        min(box[1] for box in matching),
        max(box[2] for box in matching),
        max(box[3] for box in matching),
    )


def _add_pattern(
    detections: list[Detection],
    text: str,
    spans: list[tuple[int, int, WordBox]],
    pattern: re.Pattern[str],
    kind: str,
    confidence: float,
    validator: Callable[[str], bool] | None = None,
) -> None:
    for match in pattern.finditer(text):
        value = match.group(0).strip()
        if validator and not validator(value):
            continue
        bbox = _bbox_for_span(spans, match.start(), match.end())
        if bbox:
            detections.append(Detection(kind, spans[0][2].page, bbox, confidence, "text", value))


def _line_groups(words: list[WordBox]) -> list[list[WordBox]]:
    groups: dict[tuple[int, int], list[WordBox]] = {}
    for word in words:
        groups.setdefault(word.line_id, []).append(word)
    return [sorted(group, key=lambda word: word.bbox[0]) for group in groups.values()]


def _label_detections(page: PageContent) -> list[Detection]:
    detections: list[Detection] = []
    lines = _line_groups(page.words)
    labels = re.compile(r"\b(full\s+name|name|applicant|customer|residential\s+address|permanent\s+address|address)\b", re.IGNORECASE)
    for index, line in enumerate(lines):
        line_text = " ".join(word.text for word in line)
        label_match = labels.search(line_text)
        if not label_match:
            continue
        value_start = label_match.end()
        remainder = line_text[value_start:].lstrip(" :\t-")
        if remainder:
            offset = line_text.find(remainder, value_start)
            value_words = [word for word in _words_over_text(line, offset, offset + len(remainder))]
            value = remainder.strip()
        elif index + 1 < len(lines):
            value_words = lines[index + 1]
            value = " ".join(word.text for word in value_words)
        else:
            continue
        if not value_words or len(value) < 2:
            continue
        bbox = (
            min(word.bbox[0] for word in value_words),
            min(word.bbox[1] for word in value_words),
            max(word.bbox[2] for word in value_words),
            max(word.bbox[3] for word in value_words),
        )
        label = label_match.group(1).lower()
        kind = "address_label" if "address" in label else "name_label"
        detections.append(Detection(kind, page.page, bbox, 0.72, "label", value))
    return detections


def _words_over_text(words: list[WordBox], start: int, end: int) -> Iterable[WordBox]:
    position = 0
    for index, word in enumerate(words):
        word_start = position
        word_end = word_start + len(word.text)
        if word_end > start and word_start < end:
            yield word
        position = word_end + (1 if index < len(words) - 1 else 0)


def _overlap_ratio(first: tuple[float, float, float, float], second: tuple[float, float, float, float]) -> float:
    x0 = max(first[0], second[0])
    y0 = max(first[1], second[1])
    x1 = min(first[2], second[2])
    y1 = min(first[3], second[3])
    intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    first_area = max(1.0, (first[2] - first[0]) * (first[3] - first[1]))
    second_area = max(1.0, (second[2] - second[0]) * (second[3] - second[1]))
    return intersection / min(first_area, second_area)


def detect_page(page: PageContent, vision_findings: Iterable[VisionFinding] = ()) -> list[Detection]:
    detections: list[Detection] = []
    text, spans = _page_text_and_spans(page.words)
    if spans:
        page_number = page.page
        _add_pattern(detections, text, spans, PAN_RE, "pan", 0.98, lambda value: len(value) == 10)
        _add_pattern(detections, text, spans, AADHAAR_RE, "aadhaar", 0.99, verhoeff_checksum)
        _add_pattern(detections, text, spans, PHONE_RE, "indian_phone", 0.94)
        _add_pattern(detections, text, spans, EMAIL_RE, "email", 0.99)
        _add_pattern(detections, text, spans, DATE_RE, "date_of_birth", 0.84)
        _add_pattern(detections, text, spans, PIN_RE, "indian_pin", 0.82)
        _add_pattern(detections, text, spans, PASSPORT_RE, "passport", 0.9)
        _add_pattern(detections, text, spans, IFSC_RE, "ifsc", 0.96)
        for match in BANK_ACCOUNT_RE.finditer(text):
            value = match.group(1).strip()
            digits = re.sub(r"\D", "", value)
            if not 6 <= len(digits) <= 18:
                continue
            bbox = _bbox_for_span(spans, match.start(1), match.end(1))
            if bbox:
                detections.append(Detection("bank_account", page_number, bbox, 0.95, "label", value))
        detections.extend(_label_detections(page))

    for finding in vision_findings:
        detections.append(Detection(finding.kind, page.page, finding.bbox, finding.confidence, finding.source))

    # Prefer a specific high-confidence match when a broad numeric rule overlaps it.
    result: list[Detection] = []
    for candidate in sorted(detections, key=lambda item: (-item.confidence, item.bbox[1], item.bbox[0])):
        if any(existing.page == candidate.page and _overlap_ratio(existing.bbox, candidate.bbox) > 0.65 for existing in result):
            continue
        result.append(candidate)
    return sorted(result, key=lambda item: (item.page, item.bbox[1], item.bbox[0], item.kind))
