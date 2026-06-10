#!/usr/bin/env python3
"""Display-only, rule-based reference-list prettifier.

This runs at RENDER time only. The extraction path is untouched: the references LLM pass and
`reconcile_reference_units`'s cite-key join always consume the raw verbatim bibliography blob
(`extraction_notes["references_blob"]`, sliced by `_slice_references_blob`). This module exists
purely to make that blob *readable* for a human in the rendered HTML, by splitting a
run-together / unbroken bibliography (the OCR'd markdown often jams every entry onto one line —
and frequently drops the space after the period too: ``…785–794.Chen, T.`` — 不换行/不分割) into
one entry per reference.

Because it is cosmetic and post-LLM, any split error costs only readability, never graph
correctness. The governing contract is therefore **"never render worse than raw"**: we split
only when the signal is strong, and return ``None`` (the caller falls back to the verbatim
``<pre>``) whenever we are not confident — so the output is always at least as readable as raw.

An 8-venue survey + an adversarial review of real outputs shaped the rules:
  * marker regime — ``[N]`` bracketed numeric (dominant), ``N.`` numeric-dot, ``[Key]`` /
    ``[Bar93]`` / ``[Zhong et al.(2024)]`` bracketed key, or *unmarked* author-year.
  * the unmarked author-year regime has two sub-formats with different boundary signals:
    surname-first (``Chen, D. … 2020. Title. Venue.``  → a new ``Surname, I.`` after a period) and
    firstname-first (``Nelson Elhage, … 2021.``        → the trailing year then the next author).
  * numbered/keyed regimes split on the marker (longest increasing run for numerics); the
    markerless regimes split on the author/year boundary and fall back to raw when the result is
    grossly under-split (far fewer entries than year tokens).

The ``[§N]`` paragraph markers in the source are deliberately *not* used — the survey confirmed
they never align 1:1 with references.
"""
from __future__ import annotations

import bisect
import re
from dataclasses import dataclass

# A reference's leading marker stripped from its body, e.g. ("[12]", "Vaswani et al. ...").
# ``marker`` is None for the unmarked author-year regime.
Entry = tuple[str | None, str]


@dataclass
class FormattedReferences:
    """A confidently-split bibliography, ready for hanging-indent list rendering."""

    entries: list[Entry]
    regime: str  # "numbered-bracket" | "numbered-dot" | "bracket-key" | "author-year"
    marked: bool  # whether entries carry an explicit leading marker


# --- regime signals -------------------------------------------------------------------------

_BRACKET_NUM_RE = re.compile(r"\[(\d{1,3})\]")
# A bracketed author-year / abbrev key: starts with a letter, ends in 2-4 digits (then an optional
# ")" for keys that wrap the year, ``[Zhong et al.(2024)]``). [Black, 1958], [Bar93], [AET+23].
_BRACKET_KEY_RE = re.compile(r"\[[A-Za-z][^\]\n]{0,40}?\d{2,4}[a-z]?\)?\]")
# A numeric-dot marker ("1. ", "12. ") preceding a capitalised author — also after "<digit>." so a
# run-together "pp. 1–7.7. Shafiei" still exposes the "7." marker; never a bare "vol. 3.".
_DOT_NUM_RE = re.compile(r"(?:(?<=\s)|(?<=\d\.)|^)(\d{1,3})\.(?=\s+[A-Z])", re.MULTILINE)
_YEAR_RE = re.compile(r"\b(?:19|20)\d\d[a-z]?\b")
# Sub-format discriminators: a year token preceded by a period ("Anderson. 2019.", year-AFTER the
# authors) vs preceded by a comma ("Venue, 2021.", year at the END). Whichever dominates picks the cut.
_PERIOD_YEAR_RE = re.compile(r"[.)]\s+(?:19|20)\d\d[a-z]?\.")
_COMMA_YEAR_RE = re.compile(r",\s+(?:19|20)\d\d[a-z]?\.")
# An author token "Surname, I." (capitalised name, comma, initial) — both a surname-first signal
# and the lookahead that opens a new surname-first entry.
_AY_SURNAME_RE = re.compile(r"[A-Z][A-Za-z'’\-]+,\s+[A-Z]\.")
# A line that STARTS like an author block: "Firstname Lastname" / "Surname, I." / "I. Surname".
# A line failing this (and not an explicit continuation token) is a wrapped tail — venue, DOI, URL
# — even when it embeds a year (e.g. "…/v1/2023.findings-emnlp.68"), so it must not start an entry.
_AUTHOR_START_RE = re.compile(
    r"^(?:[A-Z][a-z][A-Za-z'’\-]* [A-Z]|[A-Z][A-Za-z'’\-]+,\s+[A-Z]\.|[A-Z]\.[-\s]*[A-Z])"
)
# Start of a surname-first entry: a new "Surname, I." that follows a sentence-ending period (the end
# of the previous entry). Co-authors follow a comma, not a period, so they are excluded — this is
# what disambiguates an entry boundary from an author list. ``\s*`` because OCR often drops the space.
_AY_CUT_SURNAME_RE = re.compile(r"(?<=[.)])\s*(?=[A-Z][A-Za-z'’\-]+,\s+[A-Z]\.)")
# Boundary for firstname-first, year-at-END entries ("… Venue, 2021. NextAuthor"): a trailing year
# token then the next author. Consumes the year+gap; cut taken at the following capital.
_AY_CUT_YEAR_RE = re.compile(r"(?:19|20)\d\d[a-z]?\)?\.\s*(?=[A-Z])")
# An author-list token: a capitalised word, a lone initial ("Y."), a lowercase particle/connector
# ("and"/"et al"/nobiliary "de"/"van"…), or separators. Modelling the block as a run of these (rather
# than "no periods") tolerates middle initials AND rejects title prose, which contains lowercase words.
# The initial alternative requires "not preceded by a letter" so a word ending in a capital
# ("NeurIPS.") can't be backtracked into word + "S." initial and bridge across a real boundary.
_AY_AUTHOR_TOKEN = (
    r"(?:[A-Z][A-Za-z'’\-]+|(?<![A-Za-z])[A-Z]\.|and\b|et\b|al\b|de\b|van\b|von\b|der\b|del\b|da\b|di\b|&|[,\s\-])"
)
# Boundary for firstname-first, year-AFTER-authors entries ("Harsh Agrawal, … Daniel Y. Fu. 2022. Title"):
# cut before an author block that is shortly followed by ". YEAR.".
_AY_CUT_YEARAFTER_RE = re.compile(
    r"(?<=[.)])\s*(?=" + _AY_AUTHOR_TOKEN + r"{2,120}?\.\s*(?:19|20)\d\d[a-z]?\.)"
)
# A period that belongs to an abbreviation or a lone initial, not the end of a reference — used to
# veto a false surname-first cut (e.g. "..., eds. Smith, J." or "vol. 3. Smith, J.").
# Note: publisher suffixes like "Inc."/"Ltd." are deliberately NOT here — they END a reference
# (e.g. "Curran Associates, Inc.Hoogeboom, E."), so vetoing the cut after them would jam entries.
_ABBR_BEFORE_RE = re.compile(
    r"(?:\b(?:eds?|vol|no|pp|chap|proc|conf|al|univ|dept|inst|fig|tab)|\b[A-Z])\.$",
    re.IGNORECASE,
)
# Continuation tokens / venue leads / metadata tails that mark a fragment belonging to the previous
# entry (used both to rejoin wrapped source lines and to re-merge over-split cut fragments).
_CONT_RE = re.compile(
    r"^(?:and\b|&|pp\.|pages?\b|vol\.?\b|no\.?\b|doi\b|https?:|www\.|arxiv|url\b|"
    r"accessed\b|retrieved\b|available\b|isbn\b|issn\b|preprint\b|"
    r"in\s+proc|in\s+proceedings|proceedings\b|transactions\b|journal\b|advances\b|"
    r"international\b|annual\b|conference\b|workshop\b|symposium\b|acm\b|ieee\b|"
    r"springer\b|pmlr\b|neural\s+information\b|eds?\.|editors?\b)",
    re.IGNORECASE,
)
# A leading bare numeric marker ("1. ", "18.") left over when a numbered-dot list (whose markers were
# too OCR-mangled to detect as the dot regime) is split as author-year — strip it from the entry.
_LEADING_NUM_RE = re.compile(r"^\d{1,3}\.\s*")
_HEADER_RE = re.compile(r"^\s*#{1,6}[ \t]*(?:references?|bibliography|references\s+and\s+notes|literature\s+cited)\b[^\n]*\n", re.IGNORECASE)
# A leading "References"/"Bibliography" word — possibly glued to the first author by OCR
# ("ReferencesM. Andriushchenko"), so we strip the word itself, not a whole line.
_BARE_HEADER_RE = re.compile(
    r"^\s*(?:references\s+and\s+notes|literature\s+cited|references?|bibliography)[ \t]*",
    re.IGNORECASE,
)
_MIN_BODY = 15  # a real reference body is longer than this; shorter ones smell like a bad split


def format_references_blob(blob: str | None) -> FormattedReferences | None:
    """Split a verbatim bibliography blob into per-reference entries for display.

    Returns ``None`` (→ caller renders the raw ``<pre>``) whenever the blob has no recognisable
    marker regime or the split fails the confidence checks — honouring "never worse than raw".
    Defensive by construction: any unexpected error degrades to ``None`` rather than breaking the
    (non-essential) render.
    """
    try:
        if not blob or not isinstance(blob, str):
            return None
        text = _strip_header(blob)
        if not text.strip():
            return None

        regime = _detect_regime(text)
        if regime is None:
            return None

        if regime == "numbered-bracket":
            split = _split_numbered(text, _BRACKET_NUM_RE)
        elif regime == "numbered-dot":
            split = _split_numbered(text, _DOT_NUM_RE)
        elif regime == "bracket-key":
            split = _split_bracketed_keys(text)
        else:  # author-year
            split = _split_author_year(text)

        if not split:
            return None
        marked = regime != "author-year"
        entries: list[Entry] = split if marked else [(None, b) for b in split]
        if not _entries_are_sane(entries):
            return None
        # Gross under-split net for the weak regimes (no strictly-ordered marker to anchor on): if we
        # produced far fewer entries than year tokens, several references are still jammed together —
        # raw is more honest than a list of mega-entries.
        if regime in ("author-year", "bracket-key") and _is_gross_undersplit(entries, text):
            return None
        return FormattedReferences(entries=entries, regime=regime, marked=marked)
    except Exception:
        # The renderer treats itself as a non-essential artifact; a prettifier bug must never
        # cost a paper its bibliography — fall back to the verbatim blob.
        return None


# --- helpers --------------------------------------------------------------------------------

def _strip_header(blob: str) -> str:
    """Drop the leading ``# References`` header the slicer keeps at the top of the blob."""
    text = blob.strip()
    text = _HEADER_RE.sub("", text, count=1)
    text = _BARE_HEADER_RE.sub("", text, count=1)
    return text.lstrip()


def _detect_regime(text: str) -> str | None:
    """Pick the marker regime by signal strength; ``None`` when nothing reliable is present.

    Order matters: pure-numeric brackets are checked before author-year keys (a ``[12]`` can never
    be a ``[Bar93]``), and any marker regime is preferred over the markerless author-year fallback.
    The bracket-key test requires the keys to cover a fair share of the references (else a handful of
    stray keys in an author-year list would hijack it), and the numeric-dot test is strict because a
    bare ``N.`` collides with page/volume numbers.
    """
    if len(_BRACKET_NUM_RE.findall(text)) >= 3:
        return "numbered-bracket"
    years = len(_YEAR_RE.findall(text))
    keys = len(_BRACKET_KEY_RE.findall(text))
    if keys >= 3 and keys >= 0.3 * years:
        return "bracket-key"
    if _is_clean_dot_sequence(text):
        return "numbered-dot"
    if years >= 3:
        return "author-year"
    return None


def _is_clean_dot_sequence(text: str) -> bool:
    """True only for a genuine dot-numbered bibliography: a dense run starting near 1.

    Stray ``N.`` page/volume numbers in an author-year list never form a low-starting, dense,
    increasing run, so requiring one rejects the false positives that would otherwise hijack the
    author-year regime.
    """
    nums = [int(x) for x in _DOT_NUM_RE.findall(text)]
    if len(nums) < 5:
        return False
    keep = [nums[i] for i in _longest_increasing(nums)]
    if len(keep) < 5 or keep[0] > 2:
        return False
    return len(keep) / (keep[-1] - keep[0] + 1) >= 0.6  # dense (few gaps), not a sparse scatter


def _split_numbered(text: str, marker_re: re.Pattern) -> list[Entry] | None:
    """Split on an ordered numeric marker (``[N]`` or ``N.``) via a longest-increasing-run guard.

    Reference numbers run 1..N strictly increasing, and a reference's own text never contains an
    ``[N]`` cross-citation — so the genuine entry markers are exactly the longest strictly-increasing
    subsequence of the bracketed numbers. Selecting that subsequence tolerates arbitrary OCR-dropped
    gaps (a ``[322] -> [332]`` jump is fine) while dropping the rare stray/backward number, and works
    identically for run-together and line-separated blobs because it keys on the marker, not newlines.
    """
    cands = list(marker_re.finditer(text))
    if len(cands) < 3:
        return None

    nums = [int(m.group(1)) for m in cands]
    keep = _longest_increasing(nums)
    if len(keep) < 2:
        return None
    boundaries = [cands[i] for i in keep]

    entries: list[Entry] = []
    for i, m in enumerate(boundaries):
        nxt = boundaries[i + 1].start() if i + 1 < len(boundaries) else len(text)
        marker = text[m.start():m.end()].strip()
        body = _collapse(text[m.end():nxt])
        if body:
            entries.append((marker, body))
    return entries or None


def _longest_increasing(nums: list[int]) -> list[int]:
    """Indices of a longest strictly-increasing subsequence of ``nums`` (O(n log n), patience sort)."""
    if not nums:
        return []
    tail_idx: list[int] = []   # tail_idx[k] = index of the smallest tail of an increasing run of length k+1
    tail_val: list[int] = []
    prev = [-1] * len(nums)
    for i, x in enumerate(nums):
        pos = bisect.bisect_left(tail_val, x)  # strictly increasing -> left
        prev[i] = tail_idx[pos - 1] if pos > 0 else -1
        if pos == len(tail_val):
            tail_val.append(x)
            tail_idx.append(i)
        else:
            tail_val[pos] = x
            tail_idx[pos] = i
    out, idx = [], tail_idx[-1]
    while idx != -1:
        out.append(idx)
        idx = prev[idx]
    return out[::-1]


def _split_bracketed_keys(text: str) -> list[Entry] | None:
    """Split on bracketed author-year keys (``[Black, 1958]``, ``[Bar93]``, ``[Zhong et al.(2024)]``).

    The bracket is a strong, well-delimited boundary, so no sequence guard is needed; we only
    require entries to be spaced apart so a key cited mid-entry does not over-split.
    """
    cands = list(_BRACKET_KEY_RE.finditer(text))
    if len(cands) < 3:
        return None

    boundaries: list[re.Match] = []
    for m in cands:
        if boundaries and m.start() - boundaries[-1].end() < _MIN_BODY:
            continue  # too close to the previous boundary — a mid-entry citation, not a new entry
        boundaries.append(m)
    if len(boundaries) < 2:
        return None

    entries: list[Entry] = []
    for i, m in enumerate(boundaries):
        nxt = boundaries[i + 1].start() if i + 1 < len(boundaries) else len(text)
        marker = text[m.start():m.end()].strip()
        body = _collapse(text[m.end():nxt])
        if body:
            entries.append((marker, body))
    return entries or None


def _split_author_year(text: str) -> list[str] | None:
    """Split an unmarked author-year bibliography (no delimiter) — the hard regime.

    Newlines are used first (to rejoin wrapped lines), then each block is cut on the author/year
    boundary. There are three sub-formats with different signals, so we DETECT which one applies and
    pick a single strategy (never cascade — a wrong strategy can over-split with the right *count*,
    so a count-based gate can't catch it; better to bail to raw):
      * surname-first ("Chen, D. … 2020. Title."): dense "Surname, I." → cut before a new one.
      * firstname-first, year-after-authors ("Harsh Agrawal, … Anderson. 2019. Title."): years sit
        after a period → cut before an author block shortly followed by ". YEAR.".
      * firstname-first, year-at-end ("Nelson Elhage, … Venue, 2021."): years sit after a comma →
        cut after the trailing year.
    If the chosen strategy fails the sanity gate, we return None and the caller renders raw.
    """
    lines = [ln.strip() for ln in re.split(r"\n+", text) if ln.strip()]
    if not lines:
        return None

    merged: list[str] = []
    for ln in lines:
        # A line is a wrapped continuation when the previous line ends mid-author-list (trailing
        # comma) or it opens with a lowercase / continuation / venue token.
        if merged and (merged[-1].rstrip().endswith(",") or _is_continuation(ln)):
            merged[-1] = f"{merged[-1]} {ln}"
        else:
            merged.append(ln)

    year_count = len(_YEAR_RE.findall(text))
    if len(_AY_SURNAME_RE.findall(text)) >= max(3, 0.4 * year_count):
        strat = _subsplit_surname
    elif len(_PERIOD_YEAR_RE.findall(text)) >= len(_COMMA_YEAR_RE.findall(text)):
        strat = _subsplit_yearafter
    else:
        strat = _subsplit_year

    entries = [_collapse(e) for block in merged for e in strat(block) if e.strip()]
    # Re-merge over-split fragments the cut produced: a URL/DOI/"Accessed:"/venue tail or any
    # year-less non-author fragment belongs to the reference before it (an over-split is worse than
    # raw; a merge is not). Then drop any leftover bare numeric markers from a mis-detected dot list.
    entries = _merge_continuations(entries)
    entries = [m for m in (_LEADING_NUM_RE.sub("", e).strip() for e in entries) if m]
    return entries if _ay_sane(entries, year_count) else None


def _merge_continuations(entries: list[str]) -> list[str]:
    """Fold each continuation/metadata fragment into the entry before it."""
    out: list[str] = []
    for e in entries:
        if out and _is_continuation(e):
            out[-1] = f"{out[-1]} {e}"
        else:
            out.append(e)
    return out


def _ay_sane(entries: list[str], year_count: int) -> bool:
    """Sanity gate shared by the author-year cut strategies (drives the cascade selection)."""
    if len(entries) < 3:
        return False
    if sum(1 for e in entries if _YEAR_RE.search(e)) < len(entries) * 0.6:
        return False  # too few real references — likely prose mis-sliced, or wrong strategy
    if sum(1 for e in entries if len(e) < _MIN_BODY) > len(entries) * 0.3:
        return False  # ragged over-split — raw is more readable than confetti
    if year_count >= 8 and not (0.25 * year_count <= len(entries) <= 1.6 * year_count):
        return False  # entry count far from the year count → gross under- or over-split; bail to raw
    return True


def _subsplit_surname(block: str) -> list[str]:
    """Surname-first cut: before each new "Surname, I." that follows a sentence period (not a comma).

    Vetoes a candidate when the preceding period belongs to an abbreviation or a lone initial, so
    editor lists and "vol."/"pp." don't over-split.
    """
    cuts = [m.start() for m in _AY_CUT_SURNAME_RE.finditer(block)
            if not _ABBR_BEFORE_RE.search(block[:m.start()])]
    return _slice_at(block, cuts)


def _subsplit_yearafter(block: str) -> list[str]:
    """Firstname-first, year-after-authors cut: before an author block followed by ". YEAR.".

    Vetoes a candidate when the preceding period is a lone initial or abbreviation — otherwise a
    middle initial ("Joseph E. Gonzalez") would split the author list.
    """
    cuts = [m.start() for m in _AY_CUT_YEARAFTER_RE.finditer(block)
            if not _ABBR_BEFORE_RE.search(block[:m.start()])]
    return _slice_at(block, cuts)


def _subsplit_year(block: str) -> list[str]:
    """Firstname-first, year-at-end cut: after each trailing year token, before the next author."""
    return _slice_at(block, [m.end() for m in _AY_CUT_YEAR_RE.finditer(block)])


def _slice_at(block: str, cuts: list[int]) -> list[str]:
    """Slice ``block`` at the given (interior) cut positions, dropping empties."""
    cuts = sorted({c for c in cuts if 0 < c < len(block)})
    if not cuts:
        return [block]
    parts, prev = [], 0
    for c in cuts + [len(block)]:
        seg = block[prev:c].strip()
        if seg:
            parts.append(seg)
        prev = c
    return parts


def _is_continuation(line: str) -> bool:
    """A wrapped fragment of the previous entry rather than the start of a new one.

    A fragment is a continuation when it opens lowercase, with a known continuation/venue/metadata
    token, or simply does not start like an author block — the last case is what keeps a venue/DOI
    tail line that embeds a year ("…2023.findings-emnlp.68") from being mistaken for a new entry.
    """
    if line[:1].islower() or _CONT_RE.match(line):
        return True
    return not _AUTHOR_START_RE.match(line)


def _entries_are_sane(entries: list[Entry]) -> bool:
    """A real bibliography has several entries, so a 2-entry split means the markers failed — bail
    to raw rather than show a confidently-wrong under-split."""
    real = [b for _, b in entries if len(b) >= _MIN_BODY]
    return len(real) >= 3


def _is_gross_undersplit(entries: list[Entry], text: str) -> bool:
    """True when far fewer entries than year tokens remain — several references are still jammed."""
    year_count = len(_YEAR_RE.findall(text))
    return year_count >= 8 and len(entries) < 0.25 * year_count


def _collapse(text: str) -> str:
    """Join wrapped lines into one logical reference: collapse all whitespace runs to a space."""
    return re.sub(r"\s+", " ", text).strip()
