# `prompts-sc-style/` — SC-style restyle of the extraction prompts (A/B arm)

A **style-only** rewrite of the section-ir-0.17 extraction prompts, recast in the persona-driven,
definition-first idiom of `~/projects/ie-pipeline-integrated-sc/prompts` (the materials-science
"genealogy tree" pipeline: `# Role` → `# Goal`/`CRITICAL-n` → `# Important Definitions` →
`# Instructions` → `# Output Detail Level (Tiered Strategy)` → `# Missing Data Protocol` →
`# Mental Sandbox Examples` with **Key lessons** → `# Output Format`).

The **semantics are held constant** — every type, kind, id-prefix, relation, enum, field contract,
carve-out, and anti-pattern is identical to the shipped `prompts/`. Only the prose dress differs, so
a head-to-head run isolates **prompt style**, not framework behavior.

This folder is a **drop-in structural twin** of `prompts/` (verified 1:1 by filename). Nothing here
is wired into the pipeline by default; the production path still uses `prompts/`. Switch via the A/B
swap below.

## 1:1 file mapping

| original (`prompts/…`) | restyle (`prompts-sc-style/…`) | loader |
|---|---|---|
| `section-extraction/node-census.md` | same | fenced (Stage A) |
| `section-extraction/relation-pass.md` | same | fenced (Stage B) |
| `section-extraction/section-extraction-pass.md` | same | fenced (Stage C shared core) |
| `section-extraction/section-modules/problem.md` | same | raw-injected `section_focus` |
| `section-extraction/section-modules/method.md` | same | raw-injected `section_focus` |
| `section-extraction/section-modules/evidence.md` | same | raw-injected `section_focus` |
| `metadata-extraction.md` | same | fenced |
| `citations-extraction.md` | same | fenced |
| `reference-metadata.md` | same | fenced |

## Machine-contract invariants preserved

These are load-bearing for the loader (`section_pipeline.py::load_prompt` / `load_section_module`)
and were verified before commit:

1. **Fenced files** (`node-census`, `relation-pass`, `section-extraction-pass`, `metadata-extraction`,
   `citations-extraction`, `reference-metadata`): `load_prompt` sends **only the first fenced block
   (System Prompt) and the last fenced block (User Prompt)** to the model; everything outside the
   fences is human documentation. Each file parses to **exactly 2 fenced blocks**. JSON examples
   inside a block use **bare braces, never inner ```` ``` ```` fences** (which would split the block).
2. **Raw section modules** (`problem`/`method`/`evidence`): the **entire file** is injected as
   `<section_focus>`; the `SECTION FOCUS: <name>` lead line is kept.
3. **Placeholders are byte-exact**: `{{paper_content}}`, `{{nodes_json}}`, `{{cite_keys}}`,
   `{{references_blob}}` (the section-extraction-pass user block is discarded at runtime but must
   still exist for the 2-block loader).
4. **No schema is embedded.** The `OUTPUT FORMAT CONTRACT` (fields, enums, id pattern) is appended
   automatically from the JSON schema at runtime for json_object models (qwen/deepseek). The prompts
   only *reference* it.
5. **Provenance markers are bare `§N`** (e.g. `["§12", "§14"]`) — **not** the bracketed `["[§12]"]`
   form the reference pipeline happens to use. (The current pipeline parses bare `§N`.)

Verification performed: all 6 fenced files parse to exactly 2 blocks with placeholders intact; every
controlled-vocabulary token (types, prefixes, kinds, relation names, enums, field names) present in
each original survives into its restyle.

## How to A/B test

The prompt root is set by four constants in **`section_pipeline.py`** (changing `PROMPTS_DIR` also
repoints the three Stage-A/B/C paths, `SECTION_MODULES_DIR`, and `EXAMPLES_DIR`, which derive from
it; the other three are rooted directly):

```
line 18: PROMPTS_DIR                   = PROJECT_ROOT / "prompts" / "section-extraction"
line 24: METADATA_PROMPT_PATH          = PROJECT_ROOT / "prompts" / "metadata-extraction.md"
line 27: CITATIONS_PROMPT_PATH         = PROJECT_ROOT / "prompts" / "citations-extraction.md"
line 28: REFERENCE_METADATA_PROMPT_PATH= PROJECT_ROOT / "prompts" / "reference-metadata.md"
```

**Option A — minimal manual swap (4 lines).** Replace `"prompts"` with `"prompts-sc-style"` on
lines 18, 24, 27, 28; run the pipeline; revert to compare. Keep the two arms on **disjoint inputs or
a cold cache** — the DeepSeek/qwen proxy keys its prompt cache by content, not by API key, so the
two arms otherwise share cache.

**Option B — optional env-var toggle (recommended for repeated runs; not applied).** Replace those
four lines with:

```python
import os
_PROMPT_ROOT = PROJECT_ROOT / os.environ.get("PROMPT_SET", "prompts")
PROMPTS_DIR = _PROMPT_ROOT / "section-extraction"
# ... NODE_CENSUS_PROMPT_PATH etc. already derive from PROMPTS_DIR ...
METADATA_PROMPT_PATH = _PROMPT_ROOT / "metadata-extraction.md"
CITATIONS_PROMPT_PATH = _PROMPT_ROOT / "citations-extraction.md"
REFERENCE_METADATA_PROMPT_PATH = _PROMPT_ROOT / "reference-metadata.md"
```

Then the default arm is unchanged (`PROMPT_SET` unset → `prompts/`), and the restyle arm is:

```
PROMPT_SET=prompts-sc-style python -m production <input_dir> <output_dir> ...
```

(Say the word and I'll apply Option B.)

## What the restyle changes (style only)

- **Persona openings** (`# Role`: "You are an expert Scientific Literature Census Auditor and
  Knowledge-Graph Architect…") instead of a one-line "You are a …".
- **`CRITICAL-1` / `CRITICAL-2`** callouts hoisting the two rules each stage most often gets wrong.
- The type/kind/role taxonomies recast as a numbered **`# Important Definitions`** glossary with
  bolded terms and inline `(e.g., …)` examples.
- The procedure recast as **`# Instructions`** with bolded step titles and an explicit self-check
  (the boundary audit / completeness check).
- **`# Output Detail Level (Tiered Strategy)`** where field verbosity differs (method, evidence,
  problem).
- **`# Mental Sandbox Examples`** with explicit **Key lessons** encoding the trickiest carve-outs
  (external baselines are not nodes; sibling variants are `compares_to` not `part_of`; released vs
  used; analysis-paper `kind: finding`; metric-identity).
- Heavier **bold/`MUST`/`Do NOT`** emphasis and visual hierarchy throughout.
