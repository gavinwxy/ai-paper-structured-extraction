#!/usr/bin/env python3
"""Convert parsed paper JSON/JSONL blocks into marked Markdown documents.

This is the input preprocessor for the section-IR pipeline. The extraction pipeline
(`python -m production`) consumes a flat directory of ``*.md`` papers carrying ``[§N]``
paragraph markers; some upstream parsers emit structured JSON/JSONL blocks instead. This
module turns those blocks into exactly that marked Markdown, so json/jsonl inputs become a
drop-in source for the pipeline.

Two entry points:

* ``convert_to_markdown(...)`` — library function used by ``production.runner`` when the batch
  is launched with ``--input-format json|jsonl|auto``. Writes one ``.md`` per document into an
  output directory and returns the written paths.
* the ``main()`` CLI — run standalone to convert a file/dir up front (``-i``/``-o`` required).

Supported inputs:

* A ``.json`` file containing one top-level MinerU block array.
* A ``.json`` file containing one record with a ``content_list`` field.
* A ``.jsonl``/``.ndjson`` file containing one record per line, where each
  record has a ``content_list`` field.
* A directory containing any mix of those supported files.

Some parser fallbacks emit plain Markdown/LaTeX strings instead of structured
blocks; those are handled best-effort as Markdown-ish text.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Iterable


DEFAULT_MARKER_FORMAT = "[§{n}]"
JSONL_SUFFIXES = {".jsonl", ".ndjson"}
SUPPORTED_SUFFIXES = {".json"} | JSONL_SUFFIXES
MAX_FILENAME_STEM = 120
SKIPPED_BLOCK_TYPES = {"header", "footer", "page_number"}
TEXT_BLOCK_TYPES = {"text", "aside_text", "page_footnote", "ref_text"}

REFERENCE_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:(?:\d+(?:\.\d+)*)\.?\s+)?"
    r"(references|bibliography)\b[\s:.-]*(.*)$",
    re.IGNORECASE | re.DOTALL,
)
MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
LATEX_SECTION_RE = re.compile(
    r"\\(?P<kind>section|subsection|subsubsection)\*?\{(?P<title>[^{}]+)\}"
)


@dataclass
class InputDocument:
    source_path: Path
    source_label: str
    blocks: list[Any]
    record: dict[str, Any] | None = None
    line_no: int | None = None


class MarkdownRenderer:
    def __init__(self, marker_format: str = DEFAULT_MARKER_FORMAT) -> None:
        self.marker_format = marker_format
        self.paragraph_no = 1
        self.in_references = False

    def render(self, blocks: list[Any]) -> str:
        parts: list[str] = []
        for block in blocks:
            rendered = self.render_block(block)
            if rendered:
                parts.append(rendered)
        return "\n\n".join(parts).rstrip() + "\n"

    def render_block(self, block: Any) -> str:
        if isinstance(block, str):
            return self.render_markdownish_text(block)
        if not isinstance(block, dict):
            return self.mark_paragraph(json.dumps(block, ensure_ascii=False, sort_keys=True))

        block_type = str(block.get("type") or "text").lower()
        if block_type in SKIPPED_BLOCK_TYPES:
            return ""
        if block_type in TEXT_BLOCK_TYPES:
            return self.render_text_block(block)
        if block_type == "image":
            return self.render_image_block(block)
        if block_type == "table":
            return self.render_table_block(block)
        if block_type == "equation":
            return self.render_equation_block(block)
        if block_type == "list":
            return self.render_list_block(block)
        if block_type == "code":
            return self.render_code_block(block)

        return self.mark_paragraph(json.dumps(block, ensure_ascii=False, sort_keys=True))

    def render_text_block(self, block: dict[str, Any]) -> str:
        text = normalize_text(block.get("text", ""))
        if not text:
            return ""

        level = block.get("text_level")
        is_heading = isinstance(level, int) or isinstance(level, float)
        ref_title, ref_remainder = split_reference_heading(text)

        if self.in_references and is_heading and ref_title is None:
            self.in_references = False

        if is_heading:
            if ref_title is not None:
                self.in_references = True
                rendered = [self.heading(ref_title, level)]
                if ref_remainder:
                    rendered.append(ref_remainder)
                return "\n\n".join(rendered)
            return self.heading(text, level)

        if ref_title is not None:
            self.in_references = True
            rendered = [self.heading(ref_title, 1)]
            if ref_remainder:
                rendered.append(ref_remainder)
            return "\n\n".join(rendered)

        return self.render_plain_text(text)

    def render_image_block(self, block: dict[str, Any]) -> str:
        img_path = normalize_text(block.get("img_path", ""))
        captions = normalize_list(block.get("image_caption", block.get("img_caption")))
        footnotes = normalize_list(block.get("image_footnote", block.get("img_footnote")))
        caption = " ".join(captions).strip()

        parts: list[str] = []
        if img_path:
            alt = escape_image_alt(caption)
            parts.append(self.mark_paragraph(f"![{alt}](<{img_path}>)"))
        if caption:
            parts.append(self.render_plain_text(f"**{caption}**"))
        for footnote in footnotes:
            parts.append(self.render_plain_text(footnote))
        return "\n\n".join(part for part in parts if part)

    def render_table_block(self, block: dict[str, Any]) -> str:
        img_path = normalize_text(block.get("img_path", ""))
        captions = normalize_list(block.get("table_caption"))
        footnotes = normalize_list(block.get("table_footnote"))
        table_body = normalize_text(block.get("table_body", ""))
        caption = " ".join(captions).strip()

        parts: list[str] = []
        if img_path:
            alt = escape_image_alt(caption or "table image")
            parts.append(self.mark_paragraph(f"![{alt}](<{img_path}>)"))
        if caption:
            parts.append(self.render_plain_text(f"**{caption}**"))
        if table_body:
            parts.append(self.mark_block(table_body))
        for footnote in footnotes:
            parts.append(self.render_plain_text(footnote))
        return "\n\n".join(part for part in parts if part)

    def render_equation_block(self, block: dict[str, Any]) -> str:
        text = normalize_text(block.get("text", block.get("text_format", "")))
        if not text:
            return ""
        return self.mark_block(text)

    def render_list_block(self, block: dict[str, Any]) -> str:
        items = normalize_list(block.get("list_items"))
        if not items:
            return ""

        if block.get("sub_type") == "ref_text" or self.in_references:
            return "\n\n".join(items)

        text = "\n".join(f"- {item}" for item in items)
        return self.mark_block(text)

    def render_code_block(self, block: dict[str, Any]) -> str:
        caption = " ".join(normalize_list(block.get("code_caption"))).strip()
        code = normalize_text(block.get("code_body", block.get("text", "")))
        if not code:
            return self.render_plain_text(caption)

        parts: list[str] = []
        if caption:
            parts.append(self.render_plain_text(f"**{caption}**"))
        parts.append(self.mark_block(fenced_code(code)))
        return "\n\n".join(parts)

    def render_markdownish_text(self, text: str) -> str:
        text = normalize_text(text)
        if not text:
            return ""
        text = unwrap_outer_fence(text)
        text = convert_latex_sections(text)

        parts: list[str] = []
        for chunk in split_markdownish_chunks(text):
            parts.extend(self.render_markdownish_chunk(chunk))
        return "\n\n".join(part for part in parts if part)

    def render_markdownish_chunk(self, chunk: str) -> list[str]:
        chunk = chunk.strip()
        if not chunk:
            return []

        lines = chunk.splitlines()
        first_heading = parse_markdown_heading(lines[0])
        if first_heading and len(lines) > 1:
            first = lines[0]
            rest = "\n".join(lines[1:]).strip()
            return self.render_markdownish_chunk(first) + self.render_markdownish_chunk(rest)

        markdown_heading = parse_markdown_heading(chunk)
        ref_title, ref_remainder = split_reference_heading(chunk)

        if self.in_references and markdown_heading and ref_title is None:
            self.in_references = False

        if markdown_heading:
            level, text = markdown_heading
            ref_title, ref_remainder = split_reference_heading(text)
            if ref_title is not None:
                self.in_references = True
                rendered = [self.heading(ref_title, level)]
                if ref_remainder:
                    rendered.append(ref_remainder)
                return rendered
            return [self.heading(text, level)]

        if ref_title is not None:
            self.in_references = True
            rendered = [self.heading(ref_title, 1)]
            if ref_remainder:
                rendered.append(ref_remainder)
            return rendered

        return [self.render_plain_text(chunk)]

    def render_plain_text(self, text: str) -> str:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        if self.in_references:
            return "\n\n".join(paragraphs)
        return "\n\n".join(self.mark_paragraph(paragraph) for paragraph in paragraphs)

    def heading(self, text: str, level: Any) -> str:
        try:
            level_int = int(level)
        except (TypeError, ValueError):
            level_int = 1
        level_int = min(max(level_int, 1), 6)
        return f"{'#' * level_int} {text.strip()}"

    def mark_paragraph(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        if self.in_references:
            return text
        marker = self.marker_format.format(n=self.paragraph_no)
        self.paragraph_no += 1
        return f"{marker} {text}"

    def mark_block(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        if self.in_references:
            return text
        marker = self.marker_format.format(n=self.paragraph_no)
        self.paragraph_no += 1
        return f"{marker}\n{text}"


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.replace("\r\n", "\n").replace("\r", "\n").strip()
    return str(value).strip()


def normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [normalize_text(item) for item in value if normalize_text(item)]
    text = normalize_text(value)
    return [text] if text else []


def split_reference_heading(text: str) -> tuple[str | None, str]:
    match = REFERENCE_RE.match(text.strip())
    if not match:
        return None, ""
    title = match.group(1).strip().title()
    remainder = match.group(2).strip()
    return title, remainder


def parse_markdown_heading(text: str) -> tuple[int, str] | None:
    match = MARKDOWN_HEADING_RE.match(text.strip())
    if not match:
        return None
    return len(match.group(1)), match.group(2).strip()


def unwrap_outer_fence(text: str) -> str:
    stripped = text.strip()
    lines = stripped.splitlines()
    if len(lines) >= 2 and lines[0].lstrip().startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text


def convert_latex_sections(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        kind = match.group("kind")
        title = match.group("title").strip()
        level = {"section": 1, "subsection": 2, "subsubsection": 3}[kind]
        return f"{'#' * level} {title}"

    return LATEX_SECTION_RE.sub(replace, text)


def split_markdownish_chunks(text: str) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    in_fence = False

    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            current.append(line)
            continue
        if not in_fence and not line.strip():
            if current:
                chunks.append("\n".join(current).strip())
                current = []
            continue
        current.append(line)

    if current:
        chunks.append("\n".join(current).strip())
    return chunks


def escape_image_alt(text: str) -> str:
    return text.replace("\n", " ").replace("[", "(").replace("]", ")").strip()


def fenced_code(text: str) -> str:
    fence = "```"
    while fence in text:
        fence += "`"
    return f"{fence}\n{text}\n{fence}"


def iter_input_files(input_path: Path, input_type: str, recursive: bool) -> list[Path]:
    if input_path.is_file():
        if input_type == "auto" and input_path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError(f"Unsupported input suffix: {input_path}")
        return [input_path]
    if not input_path.is_dir():
        raise FileNotFoundError(f"Input path does not exist: {input_path}")

    pattern = "**/*" if recursive else "*"
    files = [path for path in input_path.glob(pattern) if path.is_file()]
    return sorted(path for path in files if matches_input_type(path, input_type))


def matches_input_type(path: Path, input_type: str) -> bool:
    suffix = path.suffix.lower()
    if input_type == "json":
        return suffix == ".json"
    if input_type == "jsonl":
        return suffix in JSONL_SUFFIXES
    return suffix in SUPPORTED_SUFFIXES


def detect_input_type(path: Path, input_type: str) -> str:
    if input_type != "auto":
        return input_type
    suffix = path.suffix.lower()
    if suffix in JSONL_SUFFIXES:
        return "jsonl"
    if suffix == ".json":
        return "json"
    raise ValueError(f"Cannot infer input type from suffix: {path}")


def load_documents(path: Path, input_type: str) -> list[InputDocument]:
    detected_type = detect_input_type(path, input_type)
    if detected_type == "json":
        return load_json_documents(path)
    if detected_type == "jsonl":
        return list(load_jsonl_documents(path))
    raise ValueError(f"Unsupported input type: {detected_type}")


def load_json_documents(path: Path) -> list[InputDocument]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if isinstance(data, list):
        return [
            InputDocument(
                source_path=path,
                source_label=str(path),
                blocks=data,
            )
        ]
    if isinstance(data, dict) and "content_list" in data:
        return [
            InputDocument(
                source_path=path,
                source_label=str(path),
                blocks=load_content_blocks(data, str(path)),
                record=data,
            )
        ]
    raise ValueError(f"Expected a top-level JSON array or content_list record: {path}")


def load_jsonl_documents(path: Path) -> Iterable[InputDocument]:
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSONL record: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{line_no}: expected a JSON object")
            yield InputDocument(
                source_path=path,
                source_label=f"{path}:{line_no}",
                blocks=load_content_blocks(record, f"{path}:{line_no}"),
                record=record,
                line_no=line_no,
            )


def load_content_blocks(record: dict[str, Any], source_label: str) -> list[Any]:
    content = record.get("content_list", [])
    if isinstance(content, str):
        if not content.strip():
            return []
        try:
            content = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{source_label}: invalid content_list JSON: {exc}") from exc

    if not isinstance(content, list):
        raise ValueError(f"{source_label}: content_list must be a list or JSON string")
    return content


def render_document(document: InputDocument, marker_format: str, include_metadata: bool) -> str:
    renderer = MarkdownRenderer(marker_format=marker_format)
    body = renderer.render(document.blocks).rstrip()
    metadata = document_metadata_comment(document) if include_metadata else ""
    if metadata:
        return f"{metadata}\n\n{body}\n"
    return body + "\n"


def document_metadata_comment(document: InputDocument) -> str:
    if document.record is None:
        return ""

    keys = (
        "sha256",
        "id",
        "origin_path",
        "model_name",
        "model_version",
        "content_process_path",
        "doc_loc",
    )
    lines = [f"source: {document.source_label}"]
    lines.extend(
        f"{key}: {normalize_text(document.record.get(key))}"
        for key in keys
        if normalize_text(document.record.get(key))
    )
    return "<!--\n" + "\n".join(lines) + "\n-->"


def convert_to_markdown(
    input_path: Path,
    output_dir: Path,
    *,
    input_type: str = "auto",
    recursive: bool = False,
    marker_format: str = DEFAULT_MARKER_FORMAT,
    include_metadata: bool = True,
) -> list[Path]:
    """Convert every supported JSON/JSONL document under ``input_path`` into one ``.md`` per
    document in ``output_dir`` and return the written paths (sorted by source).

    This is the library entry point the extraction pipeline calls. Output filenames are derived
    one-to-one (origin_path stem / first heading / id / sha256), de-duplicated within the run, so
    each ``.md`` becomes a stable ``paper_id`` for discovery. ``include_metadata=False`` keeps the
    rendered Markdown free of the provenance comment, which the pipeline does not consume.
    """
    files = iter_input_files(input_path, input_type, recursive)
    documents: list[InputDocument] = []
    for path in files:
        documents.extend(load_documents(path, input_type))

    output_dir.mkdir(parents=True, exist_ok=True)
    used: set[str] = set()
    written: list[Path] = []
    for document in documents:
        target = output_dir / document_output_filename(document, used)
        target.write_text(
            render_document(document, marker_format, include_metadata),
            encoding="utf-8",
        )
        written.append(target)
    return written


def write_one_to_one(
    documents: Iterable[InputDocument],
    output_path: Path,
    marker_format: str,
    include_metadata: bool,
) -> int:
    documents = list(documents)
    if len(documents) == 1 and output_path.suffix.lower() == ".md":
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            render_document(documents[0], marker_format, include_metadata),
            encoding="utf-8",
        )
        return 1

    output_path.mkdir(parents=True, exist_ok=True)
    used: set[str] = set()
    count = 0
    for document in documents:
        target = output_path / document_output_filename(document, used)
        target.write_text(
            render_document(document, marker_format, include_metadata),
            encoding="utf-8",
        )
        count += 1
    return count


def document_output_filename(document: InputDocument, used: set[str]) -> str:
    if document.record is None:
        stem = sanitize_filename_stem(document.source_path.stem)
        filename = unique_filename(f"{stem}.md", used)
        return filename

    origin_path = normalize_text(document.record.get("origin_path"))
    stem = PurePosixPath(origin_path).stem if origin_path else ""
    if not stem:
        stem = first_heading(document.blocks)
    if not stem:
        stem = (
            normalize_text(document.record.get("id"))
            or normalize_text(document.record.get("sha256"))
            or document.source_path.stem
        )

    fallback = f"record-{document.line_no:04d}" if document.line_no is not None else document.source_path.stem
    stem = sanitize_filename_stem(stem)[:MAX_FILENAME_STEM].strip("._-") or fallback
    suffix = short_id(document)
    return unique_filename(f"{stem}-{suffix}.md", used)


def unique_filename(filename: str, used: set[str]) -> str:
    filename = sanitize_filename_stem(filename.removesuffix(".md")) + ".md"
    if filename not in used:
        used.add(filename)
        return filename

    stem = filename[:-3]
    counter = 2
    while True:
        candidate = f"{stem}-{counter}.md"
        if candidate not in used:
            used.add(candidate)
            return candidate
        counter += 1


def first_heading(blocks: list[Any]) -> str:
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "text":
            continue
        if "text_level" not in block:
            continue
        text = normalize_text(block.get("text"))
        if text:
            return text
    return ""


def short_id(document: InputDocument) -> str:
    if document.record is not None:
        for key in ("sha256", "id"):
            value = sanitize_filename_stem(normalize_text(document.record.get(key)))
            if value:
                return value[:12]
    if document.line_no is not None:
        return f"{document.line_no:04d}"
    return sanitize_filename_stem(document.source_path.stem)[:12] or "document"


def sanitize_filename_stem(value: str) -> str:
    value = value.replace("/", "_").replace("\\", "_").strip()
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"[^0-9A-Za-z._-]+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("._-")


def write_combined(
    documents: Iterable[InputDocument],
    output_file: Path,
    marker_format: str,
    include_metadata: bool,
) -> int:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    parts: list[str] = []
    count = 0
    for document in documents:
        rendered = render_document(document, marker_format, include_metadata).rstrip()
        if document.record is None:
            rendered = f"<!-- source: {document.source_label} -->\n\n{rendered}"
        parts.append(rendered)
        count += 1
    output_file.write_text("\n\n---\n\n".join(parts).rstrip() + "\n", encoding="utf-8")
    return count


def resolve_combined_output(combine_arg: str | None, output_path: Path) -> Path:
    if combine_arg:
        return Path(combine_arg)
    if output_path.suffix.lower() == ".md":
        return output_path
    return output_path / "combined.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert parsed paper JSON/JSONL blocks to Markdown with [§n] paragraph markers."
    )
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        required=True,
        help="Input JSON/JSONL file or directory.",
    )
    parser.add_argument(
        "--input-type",
        choices=("auto", "json", "jsonl"),
        default="auto",
        help="Input data type. Auto detects by suffix unless overridden (default: auto).",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="When input is a directory, scan supported files recursively.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output .md file or directory.",
    )
    parser.add_argument(
        "--combine",
        nargs="?",
        const="",
        metavar="OUTPUT_MD",
        help=(
            "Write all input documents into one Markdown file. Optionally pass the "
            "combined output path here; otherwise -o/--output is used."
        ),
    )
    parser.add_argument(
        "--marker-format",
        default=DEFAULT_MARKER_FORMAT,
        help="Marker template. Use {n} for the paragraph number (default: [§{n}]).",
    )
    parser.add_argument(
        "--no-metadata",
        action="store_true",
        help="Do not prepend JSON/JSONL record metadata as a Markdown comment.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        files = iter_input_files(args.input, args.input_type, args.recursive)
        if not files:
            print(f"No supported input files found under {args.input}", file=sys.stderr)
            return 1

        documents: list[InputDocument] = []
        for path in files:
            documents.extend(load_documents(path, args.input_type))
        if not documents:
            print(f"No documents found under {args.input}", file=sys.stderr)
            return 1

        include_metadata = not args.no_metadata
        if args.combine is not None:
            output_file = resolve_combined_output(args.combine, args.output)
            count = write_combined(documents, output_file, args.marker_format, include_metadata)
            print(f"Wrote {count} Markdown document(s) to {output_file}")
        else:
            count = write_one_to_one(documents, args.output, args.marker_format, include_metadata)
            print(f"Wrote {count} Markdown document(s) to {args.output}")
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
