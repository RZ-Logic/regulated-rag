"""
FDCPA chunker: fetches Cornell LII section pages and parses them into
hierarchical chunks suitable for ingestion into the regulated-rag corpus.

Parser strategy
---------------
Cornell LII renders U.S. Code sections with a clean class-based markup
that directly encodes the parse tree:

    <div class="tab-pane" id="tab_default_1">  (body tab)
      <div class="section">
        [optional] <span class="chapeau indent0">section-level chapeau</span>
        <div class="paragraph indent1">         (subsection (1) / (a))
          <a name="1"/>
          <span class="num" value="1">(1)</span>
          [optional] <span class="head">heading text</span>
          [if leaf]    <div class="content">body text</div>
          [if branch]  <span class="chapeau indent2">chapeau for children</span>
                       <div class="paragraph indent2">...nested children...</div>
        </div>
        ...more .paragraph siblings...
        <div class="sourceCredit">(Pub. L. ...)</div>
      </div>
    </div>

    <div class="tab-pane" id="tab_default_2">  (editorial notes — IGNORED)

The `indentN` class on `.paragraph` and `.chapeau` is the depth of the
enumeration. We walk the DOM in document order and use indent levels to
drive a stack of active markers, regardless of whether children are nested
inside their parent paragraph (deep DOM) or sibling under .section (flat DOM).

This parser explicitly does NOT use `<p>` tags for body extraction —
Cornell uses `<div class="content">` and `<span class="chapeau">` for
substantive text. `<p>` only appears in the separate editorial-notes tab,
which we never enter because we only walk inside `<div class="section">`.

Design notes
------------
- One chunk per leaf enumerated unit (e.g., § 806(5) is one chunk).
- One chunk per framing clause — chapeau text that introduces enumerated
  children. The "A debt collector may not engage in any conduct..." opener
  of § 806 is itself substantive law.
- One chunk per section that has only flat content (no enumeration).
- `chunk_text` is the substantive text only. The structural prefix
  ("FDCPA § 806 (Harassment or abuse), subsection (5):") is composed at
  embed time, not stored.
- Footnote markers like "[1]" inside body text are stripped — they are
  Cornell LII annotations, not statutory text.
- Cornell wraps definition terms in <a class="definedterm"> links; their
  text is preserved in chunk_text via get_text().
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Iterator, Literal

import requests
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------

CORNELL_LII_BASE = "https://www.law.cornell.edu/uscode/text/15"

# Maps Cornell LII URL slug to (FDCPA §, expected section title fragment).
# The fragment is used as a sanity check during parsing — if the parsed title
# doesn't contain it, we know Cornell served us the wrong page.
FDCPA_SECTIONS: dict[str, tuple[str, str]] = {
    "1692":  ("802", "Congressional findings"),
    "1692a": ("803", "Definitions"),
    "1692b": ("804", "Acquisition of location"),
    "1692c": ("805", "Communication in connection"),
    "1692d": ("806", "Harassment or abuse"),
    "1692e": ("807", "False or misleading"),
    "1692f": ("808", "Unfair practices"),
    "1692g": ("809", "Validation of debts"),
    "1692h": ("810", "Multiple debts"),
    "1692i": ("811", "Legal actions"),
    "1692j": ("812", "Furnishing certain deceptive forms"),
    "1692k": ("813", "Civil liability"),
    "1692l": ("814", "Administrative enforcement"),
    "1692m": ("815", "Reports to Congress"),
    "1692n": ("816", "Relation to State laws"),
    "1692o": ("817", "Exemption for State regulation"),
    "1692p": ("818", "Exception for certain bad check"),
}

USER_AGENT = (
    "regulated-rag/0.1 (FDCPA corpus ingest; "
    "https://github.com/RZ-Logic/regulated-rag)"
)

# ----------------------------------------------------------------------------
# Types
# ----------------------------------------------------------------------------

ChunkRole = Literal[
    "framing_clause",     # chapeau text with enumerated children below it
    "enumerated_item",    # leaf enumerated unit (e.g., § 806(5))
    "standalone_section", # short section with no enumeration (e.g., § 810)
    "definition",         # entry in a definitions list (currently unused; v0.2)
]


@dataclass
class Chunk:
    """One row of the `chunks` table prior to embedding."""
    source: str          # always "fdcpa" for this module
    section_ref: str     # canonical citation, e.g., "§ 806(5)"
    chunk_text: str      # substantive statutory text
    metadata: dict       # JSONB payload — see CONTEXT.md for schema


# ----------------------------------------------------------------------------
# Fetcher
# ----------------------------------------------------------------------------

def fetch_section_html(usc_slug: str, *, session: requests.Session | None = None) -> str:
    """Fetch one Cornell LII section page. Returns raw HTML."""
    url = f"{CORNELL_LII_BASE}/{usc_slug}"
    sess = session or requests.Session()
    sess.headers.setdefault("User-Agent", USER_AGENT)
    resp = sess.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


# ----------------------------------------------------------------------------
# Text helpers
# ----------------------------------------------------------------------------

# Inline footnote markers like "[1]" that Cornell LII inserts into body text.
_FOOTNOTE_RE = re.compile(r"\s*\[\d+\]\s*")

# Cross-reference patterns inside chunk text.
_XREF_USC_RE = re.compile(r"section\s+(1692[a-p])\b", re.IGNORECASE)
_XREF_FDCPA_RE = re.compile(r"§\s*(80[2-9]|81[0-8])\b")

# Marker text validation: "(1)", "(a)", "(A)", "(iii)", etc.
_MARKER_RE = re.compile(r"^\(([a-zA-Z0-9]+)\)$")

# Indent class extraction: "indent0" -> 0, "indent2" -> 2.
# Note: Cornell's indent values are visual styling, NOT semantic depth.
# § 1692c uses subsection.indent2 for (a) and paragraph.indent1 for (a)(1) —
# higher number = OUTER level. We extract indent for diagnostics only;
# parent-child relationships are driven by DOM nesting, not indent class.
_INDENT_RE = re.compile(r"^indent(\d+)$")

# Cornell uses inconsistent class names across sections for the same structural
# role. We treat these as aliases:
#   - "paragraph" or "subsection"   -> enumerated-item wrapper
#   - "head" or "heading"           -> subsection heading text
#   - "continuation"                -> "flush" text after enumerated children
#                                      that applies to the parent subsection
# Examples:
#   § 1692c (a) is <div class="subsection indent2">; (a)(1) is nested inside
#     as <div class="paragraph indent1"> — higher indent = outer level.
#   § 1692c(c) ends with <div class="continuation indent0">If such notice
#     from the consumer is made by mail...</div> — flush text under (c).
PARAGRAPH_CLASSES = ("paragraph", "subsection")
HEAD_CLASSES = ("head", "heading")
CONTINUATION_CLASS = "continuation"


def _strip_footnotes(text: str) -> str:
    """Remove Cornell LII inline footnote markers like '[1]'."""
    return _FOOTNOTE_RE.sub(" ", text).strip()


def _normalize_whitespace(text: str) -> str:
    """Collapse internal whitespace runs to single spaces."""
    return re.sub(r"\s+", " ", text).strip()


def _clean_text(text: str) -> str:
    """Standard cleanup: strip footnotes + collapse whitespace."""
    return _normalize_whitespace(_strip_footnotes(text))


def _extract_xrefs(text: str) -> list[str]:
    """
    Extract cross-references mentioned in chunk text.
    Returns FDCPA-numbered refs (e.g., "804" for "section 1692b").
    """
    refs: set[str] = set()
    for match in _XREF_USC_RE.finditer(text):
        usc_slug = match.group(1).lower()
        if usc_slug in FDCPA_SECTIONS:
            refs.add(FDCPA_SECTIONS[usc_slug][0])
    for match in _XREF_FDCPA_RE.finditer(text):
        refs.add(match.group(1))
    return sorted(refs)


def _get_indent_level(elem: Tag) -> int | None:
    """Return integer N from an `indentN` class on the element, or None."""
    for cls in (elem.get("class") or []):
        match = _INDENT_RE.match(cls)
        if match:
            return int(match.group(1))
    return None


def _direct_child_with_class(parent: Tag, tag_name: str, class_name: str) -> Tag | None:
    """First DIRECT child of parent matching tag and class, or None."""
    for child in parent.children:
        if isinstance(child, Tag) and child.name == tag_name:
            if class_name in (child.get("class") or []):
                return child
    return None


def _direct_child_with_any_class(
    parent: Tag, tag_name: str, class_names: tuple[str, ...]
) -> Tag | None:
    """First DIRECT child of parent matching tag and any of the given classes."""
    for child in parent.children:
        if isinstance(child, Tag) and child.name == tag_name:
            child_classes = child.get("class") or []
            if any(cls in child_classes for cls in class_names):
                return child
    return None


def _combine_head_and_body(head: str, body: str) -> str:
    """
    Merge subsection heading text with body/chapeau text into one chunk-ready
    string. Produces patterns like "Communication with the consumer generally.
    Without the prior consent..." for sections like § 1692c(a).
    """
    head = head.rstrip(" .;:")
    if head and body:
        return f"{head}. {body}"
    return head or body


# ----------------------------------------------------------------------------
# Parser
# ----------------------------------------------------------------------------

def parse_section(html: str, usc_slug: str) -> list[Chunk]:
    """
    Parse one Cornell LII section page into chunks.

    Algorithm
    ---------
    Recursive DOM walker driven by physical containment, not by indent class.
    Cornell's `indentN` is visual styling that doesn't reliably encode parse
    depth (subsection.indent2 can wrap paragraph.indent1 children — see § 1692c).

    1. Validate H1 title contains the expected fragment for this slug.
    2. Locate `<div class="section">` — the body container.
    3. Walk its direct children recursively. The marker stack is pushed when
       entering an enumeration wrapper (.paragraph or .subsection) and popped
       when leaving — so DOM containment IS the citation hierarchy.
    4. For each wrapper, inspect direct children to decide chunk type:
       - has .content + no nested wrappers     -> enumerated_item leaf
       - has .chapeau (introduces children)    -> framing_clause + recurse
       - has .head only + nested wrappers      -> framing_clause + recurse
       - has .continuation child                -> flush text emitted at parent's
                                                   section_ref as framing_clause
    """
    expected_fdcpa, expected_title_fragment = FDCPA_SECTIONS[usc_slug]
    fdcpa_section = expected_fdcpa  # FDCPA_SECTIONS is the authoritative map.

    soup = BeautifulSoup(html, "html.parser")

    # H1 / title check — defends against Cornell serving the wrong page.
    h1 = soup.find("h1")
    if h1 is None:
        raise ValueError(f"No <h1> found in slug '{usc_slug}'.")
    h1_text = _normalize_whitespace(h1.get_text(" "))
    title_match = re.search(r"§\s*\S+\s*[-–—]\s*(.+?)$", h1_text)
    section_title = title_match.group(1).strip() if title_match else h1_text
    if expected_title_fragment.lower() not in section_title.lower():
        raise ValueError(
            f"Parsed title '{section_title}' does not contain expected "
            f"fragment '{expected_title_fragment}' for slug '{usc_slug}'. "
            "Cornell LII page may have changed; verify before ingest."
        )

    # Find the body container.
    section_div = soup.find("div", class_="section")
    if section_div is None:
        raise ValueError(
            f"No <div class='section'> body container found for slug "
            f"'{usc_slug}'. Cornell LII page structure may have changed."
        )

    chunks: list[Chunk] = []
    marker_stack: list[str] = []  # active markers from outermost to innermost

    def section_ref() -> str:
        suffix = "".join(f"({m})" for m in marker_stack)
        return f"§ {fdcpa_section}{suffix}"

    def parent_ref() -> str | None:
        if len(marker_stack) <= 1:
            return None
        suffix = "".join(f"({m})" for m in marker_stack[:-1])
        return f"§ {fdcpa_section}{suffix}"

    def emit(text: str, role: ChunkRole) -> None:
        cleaned = _clean_text(text)
        if not cleaned:
            return
        suffix = "".join(f"({m})" for m in marker_stack)
        chunks.append(Chunk(
            source="fdcpa",
            section_ref=section_ref(),
            chunk_text=cleaned,
            metadata={
                "uscode_citation": f"15 U.S.C. § {usc_slug}{suffix}",
                "fdcpa_section": fdcpa_section,
                "fdcpa_subsection_path": list(marker_stack),
                "section_title": section_title,
                "chunk_role": role,
                "parent_ref": parent_ref(),
                "cross_references": _extract_xrefs(cleaned),
            },
        ))

    def has_nested_wrapper(elem: Tag) -> bool:
        """Does this element have any direct .paragraph/.subsection child?"""
        for child in elem.children:
            if isinstance(child, Tag):
                child_classes = child.get("class") or []
                if any(c in child_classes for c in PARAGRAPH_CLASSES):
                    return True
        return False

    def is_wrapper(elem: Tag) -> bool:
        if elem.name != "div":
            return False
        classes = elem.get("class") or []
        return any(c in classes for c in PARAGRAPH_CLASSES)

    def walk(parent: Tag) -> None:
        """Walk direct children of parent, emitting chunks and managing stack."""
        for child in parent.children:
            if not isinstance(child, Tag):
                continue
            classes = child.get("class") or []

            # End-of-body marker.
            if "sourceCredit" in classes:
                return

            # Section-level chapeau (only emit when stack empty — i.e. this is
            # a top-level chapeau attached to the section, not a subsection).
            if child.name == "span" and "chapeau" in classes:
                if not marker_stack:
                    emit(child.get_text(" "), role="framing_clause")
                # Subsection-level chapeaus are emitted by their parent
                # wrapper's processing, not here.
                continue

            # Direct .content child of section_div (no enumeration wrapper).
            # Examples: § 1692h "Multiple debts", § 1692n "Relation to State
            # laws", § 1692o "Exemption for State regulation" — short
            # standalone sections with one block of body text.
            # Inside a wrapper, .content is handled by the wrapper's own
            # emit logic, so we only act here when the stack is empty.
            if child.name == "div" and "content" in classes:
                if not marker_stack:
                    emit(child.get_text(" "), role="standalone_section")
                continue

            # Continuation: flush text after enumerated children that applies
            # to the parent subsection (e.g., § 805(c)'s "If such notice from
            # the consumer is made by mail..." after (c)(1)–(c)(3)).
            if CONTINUATION_CLASS in classes:
                emit(child.get_text(" "), role="framing_clause")
                continue

            # Enumeration wrapper.
            if is_wrapper(child):
                num_span = _direct_child_with_class(child, "span", "num")
                if num_span is None:
                    # Wrapper without a marker — skip but recurse for safety.
                    walk(child)
                    continue
                marker_text = num_span.get_text(strip=True)
                marker_match = _MARKER_RE.match(marker_text)
                if not marker_match:
                    walk(child)
                    continue
                marker = marker_match.group(1)

                # Push marker, emit chunk for THIS wrapper, recurse for nested
                # wrappers, pop marker.
                marker_stack.append(marker)

                head = _direct_child_with_any_class(child, "span", HEAD_CLASSES)
                chapeau = _direct_child_with_class(child, "span", "chapeau")
                content = _direct_child_with_class(child, "div", "content")
                nested = has_nested_wrapper(child)

                head_text = head.get_text(" ", strip=True) if head else ""
                chapeau_text = chapeau.get_text(" ") if chapeau else ""
                content_text = content.get_text(" ") if content else ""

                if chapeau_text:
                    # Wrapper introduces nested children with a chapeau.
                    emit(_combine_head_and_body(head_text, chapeau_text),
                         role="framing_clause")
                elif content_text and not nested:
                    # Pure leaf.
                    emit(_combine_head_and_body(head_text, content_text),
                         role="enumerated_item")
                elif content_text and nested:
                    # Has both content and nested wrappers — emit content as
                    # leaf at this level; nested children will emit themselves
                    # at deeper levels via the recurse below.
                    emit(_combine_head_and_body(head_text, content_text),
                         role="enumerated_item")
                elif head_text and nested:
                    # Heading-only framing for a wrapper with nested children.
                    emit(head_text, role="framing_clause")
                # else: marker-only wrapper — nothing to emit at this level.

                # Recurse for nested wrappers / continuations / etc.
                walk(child)

                marker_stack.pop()
                continue

            # Anything else — recurse into children in case structure is
            # buried (e.g. wrapper divs with no recognizable class).
            walk(child)

    walk(section_div)
    return chunks


# ----------------------------------------------------------------------------
# Top-level orchestration
# ----------------------------------------------------------------------------

def chunk_full_fdcpa(
    *,
    polite_delay_seconds: float = 1.0,
    session: requests.Session | None = None,
) -> list[Chunk]:
    """Fetch and chunk every section in FDCPA_SECTIONS. Flat list across all sections."""
    sess = session or requests.Session()
    sess.headers.setdefault("User-Agent", USER_AGENT)

    all_chunks: list[Chunk] = []
    for usc_slug in FDCPA_SECTIONS:
        html = fetch_section_html(usc_slug, session=sess)
        section_chunks = parse_section(html, usc_slug)
        all_chunks.extend(section_chunks)
        time.sleep(polite_delay_seconds)
    return all_chunks


def iter_full_fdcpa(
    *,
    polite_delay_seconds: float = 1.0,
    session: requests.Session | None = None,
) -> Iterator[tuple[str, list[Chunk]]]:
    """Streaming variant — yields (usc_slug, chunks) per section."""
    sess = session or requests.Session()
    sess.headers.setdefault("User-Agent", USER_AGENT)

    for usc_slug in FDCPA_SECTIONS:
        html = fetch_section_html(usc_slug, session=sess)
        section_chunks = parse_section(html, usc_slug)
        yield usc_slug, section_chunks
        time.sleep(polite_delay_seconds)