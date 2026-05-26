<!-- These examples show assembled IR output (post-assembly), not raw per-section extraction output. -->

# Hypothesis-Verification Style Example

**Input excerpt**

"We evaluate our proposed Vision Transformer (ViT) on ImageNet-1K classification. ViT-Large achieves 87.1% top-1 accuracy when pre-trained on JFT-300M and fine-tuned on ImageNet, outperforming the ResNet-152 baseline (82.0%) by 5.1 percentage points under the same evaluation setup."

**Mental sandbox (before generating JSON)**

- ViT-Large is a `Method` defined in the method section.
- ImageNet-1K and JFT-300M are dataset `Entity` units in the experiment section.
- ResNet-152 is not modeled as an Entity or Metric because it is only a comparison baseline; its score is not captured, and the comparison is expressed textually in the analysis Claim.
- The pretraining/fine-tuning setup is a `Condition`.
- The target-method result is one experiment `Metric` anchored on ViT-Large.
- The comparative interpretation can be a local analysis `Claim` supported by a local analysis `Metric`.

**Representative assembled output**

```json
{
  "document": {
    "id": "doc:vit_imagenet",
    "type": "Document",
    "doc_id": "vit_imagenet",
    "title": "An Image is Worth 16x16 Words",
    "doc_role": "research_article",
    "provenance": []
  },
  "sections": [
    {
      "section_type": "method",
      "anchor_id": "mth:vit_large",
      "covers_entries": ["mth:vit_large"],
      "units": [
        {
          "id": "mth:vit_large",
          "type": "Method",
          "name": "Vision Transformer (ViT-Large)",
          "method_kind": "model_architecture",
          "description": "Large-scale Vision Transformer pre-trained on JFT-300M and fine-tuned on ImageNet.",
          "provenance": [{"source_kind": "sentence", "source": ["§5"]}]
        }
      ],
      "links": []
    },
    {
      "section_type": "experiment",
      "anchor_id": "met:vit_accuracy",
      "covers_entries": ["met:imagenet_result"],
      "units": [
        {
          "id": "ent:imagenet",
          "type": "Entity",
          "name": "ImageNet-1K",
          "entity_class": "dataset",
          "provenance": [{"source_kind": "sentence", "source": ["§5"]}]
        },
        {
          "id": "ent:jft300m",
          "type": "Entity",
          "name": "JFT-300M",
          "entity_class": "dataset",
          "provenance": [{"source_kind": "sentence", "source": ["§5"]}]
        },
        {
          "id": "cnd:eval_setup",
          "type": "Condition",
          "condition_kind": "evaluation_setup",
          "description": "ViT-Large is pre-trained on JFT-300M, fine-tuned on ImageNet-1K, and evaluated on ImageNet top-1 accuracy.",
          "provenance": [{"source_kind": "sentence", "source": ["§5"]}]
        },
        {
          "id": "met:vit_accuracy",
          "type": "Metric",
          "name": "Top-1 accuracy",
          "unit": "%",
          "subject_id": "mth:vit_large",
          "comparison_direction": "higher_is_better",
          "value_type": "scalar",
          "context_ids": ["cnd:eval_setup"],
          "scores": [
            {"variant": "ViT-Large", "value": "87.1", "variance": ""}
          ],
          "provenance": [{"source_kind": "sentence", "source": ["§5"]}]
        }
      ],
      "links": []
    },
    {
      "section_type": "analysis",
      "anchor_id": "clm:vit_outperforms",
      "covers_entries": [],
      "units": [
        {
          "id": "clm:vit_outperforms",
          "type": "Claim",
          "statement": "Vision Transformer outperforms ResNet-152 on ImageNet-1K classification when pre-trained at scale.",
          "claim_kind": "comparative",
          "target_ids": ["mth:vit_large"],
          "polarity": "positive",
          "novelty": "original",
          "epistemic_status": "conclusion",
          "provenance": [{"source_kind": "sentence", "source": ["§5"]}]
        },
        {
          "id": "met:vit_resnet_margin",
          "type": "Metric",
          "name": "Top-1 accuracy margin over ResNet-152",
          "unit": "percentage points",
          "subject_id": "mth:vit_large",
          "comparison_direction": "higher_is_better",
          "value_type": "scalar",
          "context_ids": [],
          "scores": [
            {"variant": "ViT-Large", "value": "5.1", "variance": ""}
          ],
          "provenance": [{"source_kind": "sentence", "source": ["§5"]}]
        }
      ],
      "links": [
        {"source_id": "met:vit_resnet_margin", "relation": "supports", "target_id": "clm:vit_outperforms"}
      ]
    }
  ],
  "extraction_notes": {
    "ir_version": "section-ir-0.6",
    "sections_used": ["method", "experiment", "analysis"],
    "uncertain_assignments": [],
    "skipped_spans": [],
    "input_mode": "full_paper",
    "uncovered_items": [],
    "plan_coverage": {"must_covered": 2, "must_total": 2}
  }
}
```
