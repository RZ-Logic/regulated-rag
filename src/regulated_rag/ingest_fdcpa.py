"""
FDCPA ingestion orchestrator.

Run from the repo root:

    python -m regulated_rag.ingest_fdcpa             # ingest, fail if already populated
    python -m regulated_rag.ingest_fdcpa --force     # clear existing fdcpa rows first
    python -m regulated_rag.ingest_fdcpa --dry-run   # fetch + chunk only, no DB writes

Two-phase ingest:
    Phase 1: fetch every FDCPA section from Cornell LII, chunk it, INSERT
             with embedding=NULL. Survives crashes mid-embed.
    Phase 2: SELECT every NULL-embedding fdcpa chunk, embed via Voyage,
             UPDATE.

Idempotency: by default refuses to run if `source='fdcpa'` already has rows.
Pass `--force` to DELETE existing fdcpa rows before phase 1. The other
sources (e.g., California EWA in v0.2) are never touched.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from typing import NoReturn

# Load .env from the repo root before anything that reads env vars.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv is in requirements; if it's missing the user already has
    # an env-loading problem and we can't paper over it.
    pass

from .chunker import Chunk, FDCPA_SECTIONS, iter_full_fdcpa
from .db import (
    connect,
    count_by_source,
    delete_by_source,
    fetch_unembedded_chunks,
    insert_chunks_without_embeddings,
    update_chunk_embeddings,
)
from .embedder import compose_embedding_input, _embed_batch_with_retry, _get_client


SOURCE = "fdcpa"

# Configure logging early so module-level imports' loggers are captured.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ingest_fdcpa")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Ingest FDCPA from Cornell LII into the chunks table."
    )
    p.add_argument(
        "--force", action="store_true",
        help=f"DELETE existing source='{SOURCE}' rows before ingest.",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Fetch + chunk only; print summary; do not write to DB.",
    )
    p.add_argument(
        "--polite-delay", type=float, default=1.0,
        help="Seconds to wait between Cornell LII fetches (default: 1.0).",
    )
    p.add_argument(
        "--batch-size", type=int, default=64,
        help="Voyage embed batch size (default: 64). Voyage's per-call max "
             "is 128; we stay below that ceiling.",
    )
    return p.parse_args()


def _fetch_and_chunk(polite_delay: float) -> list[Chunk]:
    """Fetch + parse every FDCPA section. Returns a flat chunk list."""
    all_chunks: list[Chunk] = []
    for usc_slug, section_chunks in iter_full_fdcpa(
        polite_delay_seconds=polite_delay,
    ):
        fdcpa_section = FDCPA_SECTIONS[usc_slug][0]
        logger.info(
            "  § %s (%s): %d chunks",
            fdcpa_section, usc_slug, len(section_chunks),
        )
        all_chunks.extend(section_chunks)
    return all_chunks


def _phase1_insert(chunks: list[Chunk]) -> list[tuple[int, Chunk]]:
    """
    INSERT chunks with embedding=NULL. Returns (id, chunk) pairs in order
    so phase 2 can target them.
    """
    logger.info("Phase 1: INSERT %d chunks (embedding=NULL)...", len(chunks))
    with connect() as conn:
        ids = insert_chunks_without_embeddings(conn, chunks)
        conn.commit()
    paired = list(zip(ids, chunks))
    logger.info("Phase 1: %d rows inserted.", len(paired))
    return paired


def _phase2_embed_and_update(
    paired: list[tuple[int, Chunk]],
    batch_size: int,
) -> None:
    """Embed every chunk via Voyage, UPDATE its row with the vector."""
    logger.info("Phase 2: embedding %d chunks via Voyage...", len(paired))
    client = _get_client()

    # Process in batches so a partial failure doesn't blow away the whole run.
    # Each successful batch is committed before the next is attempted, so a
    # crash mid-run leaves the DB in a partially-populated but consistent
    # state — re-running picks up where we left off via fetch_unembedded_chunks.
    total_updated = 0
    for batch_start in range(0, len(paired), batch_size):
        batch_end = min(batch_start + batch_size, len(paired))
        batch = paired[batch_start:batch_end]
        ids_in_batch = [p[0] for p in batch]
        chunks_in_batch = [p[1] for p in batch]

        logger.info(
            "  Embedding batch %d..%d (size %d)",
            batch_start, batch_end - 1, len(batch),
        )
        inputs = [compose_embedding_input(c) for c in chunks_in_batch]
        embeddings = _embed_batch_with_retry(
            client, inputs, input_type="document",
        )
        pairs = list(zip(ids_in_batch, embeddings))

        with connect() as conn:
            updated = update_chunk_embeddings(conn, pairs)
            conn.commit()
        total_updated += updated
        logger.info("  Updated %d rows. Cumulative: %d/%d.",
                    updated, total_updated, len(paired))

    logger.info("Phase 2: %d rows updated with embeddings.", total_updated)


def _resume_phase2_if_needed(batch_size: int) -> None:
    """If there are still NULL-embedding fdcpa rows, embed them. Used post-hoc."""
    with connect() as conn:
        unembedded = fetch_unembedded_chunks(conn, SOURCE)
    if not unembedded:
        return
    logger.warning(
        "Found %d NULL-embedding %s rows after main run — resuming phase 2.",
        len(unembedded), SOURCE,
    )
    # Reconstruct minimal pairs for the resume path. We re-compose the
    # embedding input from chunk_text + metadata, which is why metadata's
    # structural fields (fdcpa_section, section_title, fdcpa_subsection_path)
    # must be present at insert time.
    from .chunker import Chunk as _Chunk  # avoid name shadow above

    paired: list[tuple[int, _Chunk]] = []
    for chunk_id, chunk_text, metadata in unembedded:
        synthetic = _Chunk(
            source=SOURCE,
            section_ref=metadata.get("section_ref", "?"),
            chunk_text=chunk_text,
            metadata=metadata,
        )
        paired.append((chunk_id, synthetic))
    _phase2_embed_and_update(paired, batch_size)


def main() -> NoReturn:
    args = _parse_args()
    started = time.monotonic()

    logger.info(
        "Ingest mode: %s",
        "dry-run" if args.dry_run else ("force-replace" if args.force else "fresh"),
    )

    # Connectivity + idempotency check (skipped in dry-run).
    if not args.dry_run:
        with connect() as conn:
            existing = count_by_source(conn, SOURCE)
        if existing > 0 and not args.force:
            logger.error(
                "%d rows already exist for source='%s'. Pass --force to replace.",
                existing, SOURCE,
            )
            sys.exit(2)
        if existing > 0 and args.force:
            with connect() as conn:
                deleted = delete_by_source(conn, SOURCE)
                conn.commit()
            logger.warning("Deleted %d existing %s rows.", deleted, SOURCE)

    # Phase 0: fetch + chunk.
    logger.info("Phase 0: fetch + chunk all FDCPA sections from Cornell LII...")
    chunks = _fetch_and_chunk(args.polite_delay)
    logger.info("Phase 0: %d total chunks across %d sections.",
                len(chunks), len(FDCPA_SECTIONS))

    if args.dry_run:
        logger.info("Dry-run: skipping DB writes. Sample chunks:")
        for c in chunks[:5]:
            logger.info("  %s [%s] %s",
                        c.section_ref,
                        c.metadata["chunk_role"],
                        c.chunk_text[:100].replace("\n", " "))
        elapsed = time.monotonic() - started
        logger.info("Done in %.1fs.", elapsed)
        sys.exit(0)

    # Phase 1: INSERT with NULL embeddings.
    paired = _phase1_insert(chunks)

    # Phase 2: embed + UPDATE.
    _phase2_embed_and_update(paired, args.batch_size)

    # Belt-and-suspenders: if anything is still unembedded (e.g., transient
    # Voyage failure within a batch), pick it up.
    _resume_phase2_if_needed(args.batch_size)

    # Final tally.
    with connect() as conn:
        final = count_by_source(conn, SOURCE)
    elapsed = time.monotonic() - started
    logger.info("Ingest complete: %d rows for source='%s' in %.1fs.",
                final, SOURCE, elapsed)
    sys.exit(0)


if __name__ == "__main__":
    main()
