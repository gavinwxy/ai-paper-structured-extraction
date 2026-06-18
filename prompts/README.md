# `prompts/` — section-ir-0.17 extraction prompts (SC idiom)

The **production** extraction prompts for the section-ir-0.17 pipeline, written in the persona-driven,
definition-first **SC idiom** (`# Role` → `# Goal`/`CRITICAL-n` → `# Important Definitions` →
`# Instructions` → `# Output Detail Level (Tiered Strategy)` → `# Missing Data Protocol` →
`# Mental Sandbox Examples` with **Key lessons** → `# Output Format`), adapted from the
`ie-pipeline-integrated-sc` "genealogy tree" pipeline.

**Provenance.** This SC-idiom set won a head-to-head A/B against the previous one-line-persona phrasing
and was promoted to the default on 2026-06-18. The pre-SC original is preserved verbatim at
`archive/legacy-prompts/section-ir-0.17-original/` (identical file layout). The two are *intended
semantic equivalents* — same types, kinds, id-prefixes, relations, enums, field contracts, carve-outs,
and anti-patterns — so the only deliberate difference is prose style. Where they ever disagree, **this
production set is authoritative** (a June 2026 review reconciled a few drifts across both arms).

## File layout

| file | loader |
|---|---|
| `section-extraction/node-census.md` | fenced (Stage A) |
| `section-extraction/relation-pass.md` | fenced (Stage B) |
| `section-extraction/section-extraction-pass.md` | fenced (Stage C shared core) |
| `section-extraction/section-modules/problem.md` | raw-injected `section_focus` |
| `section-extraction/section-modules/method.md` | raw-injected `section_focus` |
| `section-extraction/section-modules/evidence.md` | raw-injected `section_focus` (blob-primary) |
| `metadata-extraction.md` | fenced |
| `citations-extraction.md` | fenced |
| `reference-metadata.md` | fenced |

Paths are wired in `section_pipeline.py` (`PROMPTS_DIR` plus the metadata/citations/reference
constants); `production/worker.py` imports those constants, so this directory is the **single source of
truth** for the live prompts.

## Machine-contract invariants (load-bearing for the loader)

`section_pipeline.py::load_prompt` / `load_section_module`:

1. **Fenced files** (`node-census`, `relation-pass`, `section-extraction-pass`, `metadata-extraction`,
   `citations-extraction`, `reference-metadata`): `load_prompt` sends **only the first fenced block
   (System Prompt) and the last fenced block (User Prompt)**; everything outside the fences is human
   documentation. Each file parses to **exactly 2 fenced blocks**. JSON examples inside a block use
   **bare braces, never inner ```` ``` ```` fences** (which would split the block).
2. **Raw section modules** (`problem`/`method`/`evidence`): the **entire file** is injected as
   `<section_focus>`; the `SECTION FOCUS: <name>` lead line is kept.
3. **Placeholders are byte-exact**: `{{paper_content}}`, `{{nodes_json}}`, `{{cite_keys}}`,
   `{{references_blob}}` (the section-extraction-pass user block is discarded at runtime but must still
   exist for the 2-block loader).
4. **No schema is embedded.** The `OUTPUT FORMAT CONTRACT` (fields, enums, id pattern) is appended
   automatically from the JSON schema at runtime for json_object models (qwen/deepseek); the prompts
   only *reference* it.
5. **Provenance markers are bare `§N`** (e.g. `["§12", "§14"]`), not the bracketed `["[§12]"]` form.

## A/B against the archived original

The pre-SC original still lives at `archive/legacy-prompts/section-ir-0.17-original/`. To run it as a
comparison arm, point the four `section_pipeline.py` path constants at that tree (then revert):

```
line 18: PROMPTS_DIR                    = PROJECT_ROOT / "archive" / "legacy-prompts" / "section-ir-0.17-original" / "section-extraction"
line 24: METADATA_PROMPT_PATH           = PROJECT_ROOT / "archive" / "legacy-prompts" / "section-ir-0.17-original" / "metadata-extraction.md"
line 27: CITATIONS_PROMPT_PATH          = PROJECT_ROOT / "archive" / "legacy-prompts" / "section-ir-0.17-original" / "citations-extraction.md"
line 28: REFERENCE_METADATA_PROMPT_PATH = PROJECT_ROOT / "archive" / "legacy-prompts" / "section-ir-0.17-original" / "reference-metadata.md"
```

(Changing `PROMPTS_DIR` also repoints the Stage-A/B/C paths and `SECTION_MODULES_DIR`, which derive
from it.) Keep the two arms on **disjoint inputs or a cold cache** — the DeepSeek/qwen proxy keys its
prompt cache by content, not by API key, so the arms otherwise share cache.
