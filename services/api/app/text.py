from __future__ import annotations

import re
import secrets
from collections import Counter

from fastapi import HTTPException, status


MIN_WORDS = 800
MAX_WORDS = 5000
MAX_PARAGRAPHS = 400

PROTECTED_PATTERN = re.compile(
    r"https?://\S+|\[[0-9,\-\s]+\]|\([A-Z][A-Za-z'’-]+(?:\s+et al\.)?,?\s+\d{4}[a-z]?\)|"
    r"\b\d+(?:\.\d+)?%?\b|\b[A-Z]{2,}[A-Z0-9-]*\b|[\"“”][^\"“”]{2,240}[\"“”]"
)
SENTENCE_PATTERN = re.compile(r"[^.!?]+(?:[.!?]+|$)", re.MULTILINE)


def normalize_text(value: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"\r\n?", "\n", str(value or ""))).strip()


def word_count(value: str) -> int:
    return len(re.findall(r"\b[\w’'-]+\b", value, flags=re.UNICODE))


def validate_english_coursework(value: str) -> int:
    count = word_count(value)
    if count < MIN_WORDS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"Paper must contain at least {MIN_WORDS} words")
    if count > MAX_WORDS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"Paper must contain at most {MAX_WORDS} words")
    letters = re.findall(r"[A-Za-z]", value[:12000])
    non_latin = re.findall(r"[\u4e00-\u9fff]", value[:12000])
    if len(letters) < max(200, len(non_latin) * 3):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="V1 accepts English coursework only")
    return count


def paragraphs_from_text(value: str, previous: list[dict] | None = None) -> list[dict]:
    normalized = normalize_text(value)
    chunks = [item.strip() for item in re.split(r"\n\s*\n", normalized) if item.strip()]
    if len(chunks) == 1:
        chunks = [item.strip() for item in normalized.split("\n") if item.strip()]
    if not chunks or len(chunks) > MAX_PARAGRAPHS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid paragraph count")
    previous = previous or []
    result = []
    for index, chunk in enumerate(chunks):
        paragraph_id = previous[index]["id"] if index < len(previous) and previous[index].get("text") == chunk else f"p_{secrets.token_hex(8)}"
        result.append({"id": paragraph_id, "text": chunk})
    return result


def validate_paragraphs(paragraphs: list[dict]) -> int:
    if not paragraphs or len(paragraphs) > MAX_PARAGRAPHS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid paragraph count")
    ids: set[str] = set()
    normalized: list[str] = []
    for paragraph in paragraphs:
        paragraph_id = str(paragraph.get("id", ""))
        text = normalize_text(str(paragraph.get("text", "")))
        if not paragraph_id or paragraph_id in ids or not text:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid paragraph data")
        ids.add(paragraph_id)
        normalized.append(text)
    return validate_english_coursework("\n\n".join(normalized))


def protected_tokens(value: str) -> Counter:
    return Counter(match.group(0) for match in PROTECTED_PATTERN.finditer(value))


def assert_protected_equal(original: str, revised: str) -> None:
    before = protected_tokens(original)
    after = protected_tokens(revised)
    if before != after:
        missing = list((before - after).elements())[:3]
        added = list((after - before).elements())[:3]
        detail = "Protected citations, numbers, quotations, URLs, or abbreviations changed"
        if missing or added:
            detail += f" (missing: {missing or 'none'}; added: {added or 'none'})"
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def sentence_ranges(value: str) -> list[tuple[int, int, str]]:
    output: list[tuple[int, int, str]] = []
    for match in SENTENCE_PATTERN.finditer(value):
        raw = match.group(0)
        leading = len(raw) - len(raw.lstrip())
        trailing = len(raw.rstrip())
        start = match.start() + leading
        end = match.start() + trailing
        if end > start:
            output.append((start, end, value[start:end]))
    return output


def document_quality_checks(paragraphs: list[dict]) -> dict:
    repeated: dict[str, list[dict]] = {}
    inline_citations = 0
    reference_heading_index: int | None = None
    for index, paragraph in enumerate(paragraphs):
        text = paragraph["text"]
        if text.strip().lower() in {"references", "bibliography", "works cited"}:
            reference_heading_index = index
        inline_citations += len(re.findall(r"\[[0-9,\-\s]+\]|\([A-Z][A-Za-z'’-]+(?:\s+et al\.)?,?\s+\d{4}[a-z]?\)", text))
        for start, end, sentence in sentence_ranges(text):
            normalized = re.sub(r"[^a-z0-9 ]+", "", sentence.lower())
            normalized = re.sub(r"\s+", " ", normalized).strip()
            if word_count(normalized) < 8:
                continue
            repeated.setdefault(normalized, []).append(
                {"paragraphId": paragraph["id"], "start": start, "end": end, "preview": sentence[:180]}
            )
    duplicate_groups = [
        {"occurrences": rows, "count": len(rows)}
        for rows in repeated.values()
        if len(rows) > 1
    ]
    reference_entries = 0 if reference_heading_index is None else max(0, len(paragraphs) - reference_heading_index - 1)
    warnings: list[str] = []
    if inline_citations and reference_heading_index is None:
        warnings.append("Inline citations were found but no References or Bibliography heading was detected.")
    if reference_heading_index is not None and reference_entries == 0:
        warnings.append("A reference heading was found without reference entries.")
    if not inline_citations:
        warnings.append("No recognizable inline citation markers were detected; verify whether the assignment requires sources.")
    return {
        "duplicateGroups": duplicate_groups[:20],
        "inlineCitationCount": inline_citations,
        "referenceHeadingPresent": reference_heading_index is not None,
        "referenceEntryParagraphs": reference_entries,
        "warnings": warnings,
    }
