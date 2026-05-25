<!-- These examples show assembled IR output (post-assembly), not raw per-section extraction output. -->

# Problem-Solution Style Example

**Input excerpt**

"Natural language inference benchmarks require robust model comparison. BERT Large achieved 86.7% accuracy on MNLI, outperforming the GPT baseline by 4.6 points on the test set."

**Mental sandbox (before generating JSON)**

- "benchmarks require robust model comparison" identifies a gap, so it becomes a `Context` with `context_kind: gap`.
- BERT Large is the target method under discussion.
- MNLI test set is an operational evaluation constraint, so it becomes a `Condition`.
- The accuracy figure is a target-method `Metric`; the GPT baseline score is not captured, and the comparison is expressed textually in the Claim.
- The context, method, claim, and experiment sections carry their roles structurally; explicit links remain section-local.

**Representative assembled output**

```json
{
  "document": {
    "id": "doc:bert_excerpt",
    "type": "Document",
    "doc_id": "example_ps_1",
    "title": "BERT benchmark excerpt",
    "doc_role": "research_article",
    "provenance": []
  },
  "sections": [
    {
      "section_type": "context",
      "anchor_id": "ctx:nli_benchmark_gap",
      "covers_entries": ["ctx:nli_benchmark_gap"],
      "units": [
        {
          "id": "ctx:nli_benchmark_gap",
          "type": "Context",
          "context_kind": "gap",
          "description": "Natural language inference benchmarks require robust model comparison.",
          "provenance": [{"source_kind": "sentence", "source": ["§1"]}]
        }
      ],
      "links": []
    },
    {
      "section_type": "method",
      "anchor_id": "mth:bert_large",
      "covers_entries": ["mth:bert_large"],
      "units": [
        {
          "id": "mth:bert_large",
          "type": "Method",
          "name": "BERT Large",
          "method_kind": "model_architecture",
          "description": "Large BERT model evaluated for natural language inference.",
          "provenance": [{"source_kind": "sentence", "source": ["§1"]}]
        }
      ],
      "links": []
    },
    {
      "section_type": "claim",
      "anchor_id": "clm:bert_outperforms_gpt",
      "covers_entries": ["clm:bert_outperforms_gpt"],
      "units": [
        {
          "id": "clm:bert_outperforms_gpt",
          "type": "Claim",
          "statement": "BERT Large outperforms the GPT baseline on MNLI.",
          "claim_kind": "comparative",
          "target_ids": ["mth:bert_large"],
          "polarity": "positive",
          "epistemic_status": "conclusion",
          "provenance": [{"source_kind": "sentence", "source": ["§1"]}]
        }
      ],
      "links": []
    },
    {
      "section_type": "experiment",
      "anchor_id": "met:mnli_accuracy",
      "covers_entries": ["met:mnli_accuracy"],
      "units": [
        {
          "id": "cnd:mnli_test",
          "type": "Condition",
          "condition_kind": "evaluation_setup",
          "description": "MNLI test set used as the evaluation benchmark.",
          "provenance": [{"source_kind": "sentence", "source": ["§1"]}]
        },
        {
          "id": "met:mnli_accuracy",
          "type": "Metric",
          "name": "MNLI accuracy",
          "unit": "%",
          "subject_id": "mth:bert_large",
          "comparison_direction": "higher_is_better",
          "value_type": "scalar",
          "context_ids": ["cnd:mnli_test"],
          "scores": [
            {"variant": "BERT Large", "value": "86.7", "variance": ""}
          ],
          "provenance": [{"source_kind": "sentence", "source": ["§1"]}]
        }
      ],
      "links": []
    }
  ],
  "extraction_notes": {
    "ir_version": "section-ir-0.6",
    "sections_used": ["context", "method", "claim", "experiment"],
    "uncertain_assignments": [],
    "skipped_spans": [],
    "input_mode": "full_paper",
    "uncovered_items": [],
    "plan_coverage": {"must_covered": 4, "must_total": 4}
  }
}
```
