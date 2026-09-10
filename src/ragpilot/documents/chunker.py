"""Groups a ``NormalizedDocument``'s units into indexable/storable chunks.

Headings and tables are stored one-to-one; consecutive paragraph units
under the same heading are merged up to ``max_chunk_chars`` so a very
finely split source document (one ``TextItem`` per line, in the worst
case) does not produce one DB row per line. Every output ``Chunk`` still
carries its own page/heading-path provenance, per the blueprint's
evidence-first rule.
"""

from __future__ import annotations

from dataclasses import dataclass

from ragpilot.documents.normalizer import NormalizedDocument, NormalizedUnit

DEFAULT_MAX_CHUNK_CHARS = 1000


@dataclass(frozen=True)
class Chunk:
    kind: str  # "heading" | "paragraph" | "table"
    text: str
    heading_level: int | None
    heading_path: tuple[str, ...]
    parent_index: int | None  # index into the returned chunk list, not the source units list
    page_start: int | None
    page_end: int | None
    table_rows: tuple[tuple[str, ...], ...] | None = None


def chunk_document(
    normalized: NormalizedDocument, *, max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS
) -> list[Chunk]:
    # Headings are never merged away, but merging paragraphs does drop
    # rows, so a heading's position in ``units`` no longer matches its
    # position in the output -- this remaps old index -> new index for
    # every heading so paragraph/table ``parent_index`` values stay valid.
    old_heading_to_new: dict[int, int] = {}
    chunks: list[Chunk] = []
    pending: list[NormalizedUnit] = []

    def flush_pending() -> None:
        nonlocal pending
        if not pending:
            return
        first = pending[0]
        parent_new = (
            old_heading_to_new.get(first.parent_index) if first.parent_index is not None else None
        )
        pages = [p for u in pending for p in (u.page_start, u.page_end) if p is not None]
        chunks.append(
            Chunk(
                kind="paragraph",
                text="\n\n".join(u.text for u in pending),
                heading_level=None,
                heading_path=first.heading_path,
                parent_index=parent_new,
                page_start=min(pages) if pages else None,
                page_end=max(pages) if pages else None,
            )
        )
        pending = []

    for old_index, unit in enumerate(normalized.units):
        if unit.kind == "paragraph":
            pending_chars = sum(len(u.text) for u in pending)
            if pending and pending_chars + len(unit.text) + 2 > max_chunk_chars:
                flush_pending()
            pending.append(unit)
            continue

        flush_pending()
        parent_new = (
            old_heading_to_new.get(unit.parent_index) if unit.parent_index is not None else None
        )
        new_index = len(chunks)
        chunks.append(
            Chunk(
                kind=unit.kind,
                text=unit.text,
                heading_level=unit.heading_level,
                heading_path=unit.heading_path,
                parent_index=parent_new,
                page_start=unit.page_start,
                page_end=unit.page_end,
                table_rows=unit.table_rows,
            )
        )
        if unit.kind == "heading":
            old_heading_to_new[old_index] = new_index

    flush_pending()
    return chunks
