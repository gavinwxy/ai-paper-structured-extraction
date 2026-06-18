export const meta = {
  name: 'verify-section-ir-100',
  description: 'Item-by-item verify 100 section-ir-0.17 extractions against source, adversarially confirm',
  phases: [
    { title: 'Verify', detail: 'one agent per paper: read source + extraction, flag faithfulness issues' },
    { title: 'Adversary', detail: 'skeptic re-checks high/medium findings against source' },
  ],
}

// ----- section-ir-0.17 contract the verifier must judge against (INTENDED design) -----
const CONTRACT = `
SECTION-IR 0.17 CONTRACT (judge the extraction against THIS intended design, not your own taste):

OUTPUT = { document, sections[problem,method,evidence], relations[], extraction_notes }.

Unit TYPES (7): Document, Problem, Contribution, Component, ExperimentSetup, Measure, Finding.
 - 'type' is primary; 'kind' is a finer differentia ONLY on Document/Contribution/ExperimentSetup/Finding.
 - Contribution = the paper's OWN root deliverable; kind in {method,dataset,benchmark,finding}. id 'con:'.
   A proven formal result roots as kind=method with method_kind in {theorem,lemma,bound,definition}.
 - Component = a sub-module part_of a Contribution. id 'cmp:'. (Contribution+Component replace old 'Method'.)
 - ExperimentSetup: substrate kinds {dataset,benchmark,task}; configuration kinds {data_split,inference_protocol,training_config,ensembling,population}. id 'exp:'.
 - Measure: a metric/axis; carries scores[] rows {variant,value,variance,system_id,setup_id}(+opt opponent_id/judge_id), unit, comparison_direction, setup_ids. id 'mea:'.
 - Finding: born in evidence; kind in {descriptive,mechanistic,comparative,modeling,ablation_finding,failure_mode,theorem,lemma,bound}. id 'fnd:'.
 - Problem: the research problem, born in problem section. id 'prb:'.
 - method_kind (optional, on method-Contribution & Component) in {algorithm,model_architecture,training_strategy,objective_function,resource,taxonomy,theorem,lemma,bound,definition}.

RELATIONS (fixed matrix): part_of(Comp/Exp->Contrib/Comp/Exp), builds_on, uses, co_contribution(Contrib<->Contrib),
 compares_to(peer variants), evaluates(Measure->Contrib/Comp), about(Finding->Contrib/Comp/Exp/Measure),
 supports(Measure/Finding/Contrib/Comp->Finding), motivates(Problem->Contrib/Comp/Exp), resolves(Finding->Problem).

INTENTIONAL DESIGN — DO NOT flag these as "missing"/errors (they are BY DESIGN):
 - EXTERNAL prior-art methods (works the paper builds on / reuses / compares against) are NOT census nodes
   and NOT internal units. The paper's relation to them lives PAPER-LEVEL in the citation layer
   (03_references.json: relation.roles in {compares_with,uses_component,builds_on,inspired_by,
   adapts_idea_from,addresses_limitation_of,analyzes_property_of}). So a missing "baseline method node" is correct.
 - BASELINE numeric results are NOT required as score rows; they survive verbatim in the reference/source blob.
   The paper's OWN method/variants ARE internal nodes and SHOULD have score rows.
 - Apparatus (hardware; metric-scoring helper models) is intentionally dropped (not a node).
 - Findings are NOT census nodes; they are born in the evidence section.
 - 'background' citations are intentionally not emitted as relations; they stay in references_blob.
 - provenance §N markers in units/relations are machine [§N] chunk ids of the pipeline input; in the
   census they are author-section labels. extraction_notes.span_index gives a text prefix per cited §N.

WHAT TO VERIFY (item-by-item, against the ACTUAL paper content you read — the filename may be MISLABELED):
 1 document: title/thesis/headline_result/topics/tasks/domain faithful & correct?
 2 problem: does the Problem unit match the paper's actual stated problem? motivates edge right?
 3 method: are the paper's OWN contribution(s) correctly identified (root + components)? kind/method_kind right?
   formulas[] expressions faithful to the paper's equations? any real contribution missed or hallucinated?
 4 evidence_setups: datasets/benchmarks/splits/configs faithful? kinds right? cite_keys plausible?
 5 evidence_measures: metric names & units right? comparison_direction right? ARE SCORE VALUES PRESENT AND
   NUMERICALLY CORRECT vs the source tables/text? (empty value/value_num where the paper reports numbers = a defect).
   system_id/setup_id wiring correct?
 6 evidence_findings: are stated findings faithful to the paper's claims? polarity/kind right? hallucinated or missing key findings?
 7 relations: part_of/evaluates/motivates/about/resolves directionally correct & supported by the text?
 8 provenance: do cited §N markers actually point to relevant source content (cross-check span_index / grep [§N] in source)?
 9 references: do citation-layer roles/signals match what the paper says about those works?
 10 coverage: any SIGNIFICANT paper content silently dropped (sections_omitted, uncovered_items, a whole results table, a key method)?

ATTRIBUTION for every finding (critical):
 - framework_design = the schema/prompt/pipeline CANNOT represent it or instructs the wrong thing (a true framework limitation).
 - model_error = the framework allows the correct output but the qwen extractor got it wrong (model capability/noise).
 - source_quality = the source markdown is garbled/mis-parsed (OCR junk, wrong paper, missing tables).
 - unclear = cannot tell.
Only framework_design findings should drive framework revision; label honestly.
`

const VERIFY_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    paper_id: { type: 'string' },
    actual_title: { type: 'string', description: 'the paper title as found IN THE CONTENT' },
    label_faithful: { type: 'boolean', description: 'does the actual content match the filename venue/topic' },
    coherent_paper: { type: 'boolean', description: 'is the source a single coherent scientific paper' },
    dimension_scores: {
      type: 'object', additionalProperties: false,
      description: '1=badly wrong .. 5=faithful, for each dimension',
      properties: {
        document: { type: 'integer' }, problem: { type: 'integer' }, method: { type: 'integer' },
        evidence_setups: { type: 'integer' }, evidence_measures: { type: 'integer' },
        evidence_findings: { type: 'integer' }, relations: { type: 'integer' },
        provenance: { type: 'integer' }, references: { type: 'integer' }, coverage: { type: 'integer' },
      },
      required: ['document','problem','method','evidence_setups','evidence_measures','evidence_findings','relations','provenance','references','coverage'],
    },
    findings: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          dimension: { enum: ['document','problem','method','evidence_setups','evidence_measures','evidence_findings','relations','provenance','references','coverage','other'] },
          severity: { enum: ['high','medium','low'] },
          kind: { enum: ['missing','hallucinated','wrong_value','imprecise','misclassified','wrong_relation','provenance_error','structural','other'] },
          description: { type: 'string' },
          source_evidence: { type: 'string', description: 'verbatim quote and/or §marker from the SOURCE that proves the issue' },
          extraction_fragment: { type: 'string', description: 'the offending part of the extraction' },
          attribution: { enum: ['framework_design','model_error','source_quality','unclear'] },
          confidence: { enum: ['high','medium','low'] },
        },
        required: ['dimension','severity','kind','description','source_evidence','extraction_fragment','attribution','confidence'],
      },
    },
    summary: { type: 'string', description: '2-4 sentences: overall extraction quality and the most important issues' },
  },
  required: ['paper_id','actual_title','label_faithful','coherent_paper','dimension_scores','findings','summary'],
}

const ADVERSARY_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    paper_id: { type: 'string' },
    verdicts: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          finding_index: { type: 'integer', description: 'index into the findings list you were given' },
          verdict: { enum: ['confirmed','refuted','downgraded'] },
          corrected_attribution: { enum: ['framework_design','model_error','source_quality','unclear'] },
          note: { type: 'string', description: 'why — cite the source span you checked' },
        },
        required: ['finding_index','verdict','corrected_attribution','note'],
      },
    },
  },
  required: ['paper_id','verdicts'],
}

const SRC_DIR = 'production-outputs/eval_sample100_v017_inputs'
const OUT_DIR = 'production-outputs/eval_8x100_sample100_v0.17'

const PAPER_IDS = [
"007_AAAI_2020_Restraining_Bolts_for_Reinforcement_Learning_Agents","001_AAAI_2023_Risk_Controlled_Image_Retrieval","002_AAAI_2024_Exploring_Diverse_Representations_for_Open_Set_Recognition","024_AAAI_2024_Text2Data__Low-Resource_Data_Generation_with_Textual_Control","027_AAAI_2025_Zero-shot_Video_Moment_Retrieval_via_Off-the-shelf_Multimodal_Large_Language_Models","038_AAAI_2025_When_Shadow_Removal_Meets_Intrinsic_Image_Decomposition__A_Joint_Learning_Framework_Using_Unpaired_Data","046_AAAI_2025_Wavelet-Driven_Masked_Image_Modeling__A_Path_to_Efficient_Visual_Representation","055_AAAI_2025_VisRec__A_Semi-Supervised_Approach_to_Visibility_Data_Reconstruction_in_Radio_Astronomy","059_AAAI_2025_VidEvent__A_Large_Dataset_for_Understanding_Dynamic_Evolution_of_Events_in_Videos","064_AAAI_2025_VarDrop__Enhancing_Training_Efficiency_by_Reducing_Variate_Redundancy_in_Periodic_Time_Series_Forecasting","081_AAAI_2025_Unified_Graph_Neural_Networks_Pre-training_for_Multi-domain_Graphs","095_AAAI_2025_Tri-Ergon__Fine-Grained_Video-to-Audio_Generation_with_Multi-Modal_Conditions_and_LUFS_Control","002_ACL_2025_Your_Model_is_Overconfident__and_Other_Lies_We_Tell_Ourselves","016_ACL_2025_Why_Not_Act_on_What_You_Know__Unleashing_Safety_Potential_of_LLMs_via_Self-Aware_Guard_Enhancement","017_ACL_2025_Who_Writes_What__Unveiling_the_Impact_of_Author_Roles_on_AI-generated_Text_Detection","022_ACL_2025_Where_Are_We__Evaluating_LLM_Performance_on_African_Languages","029_ACL_2025_What_s_the_Difference__Supporting_Users_in_Identifying_the_Effects_of_Prompt_and_Model_Changes_Through_Token_P","034_ACL_2025_WavRAG__Audio-Integrated_Retrieval_Augmented_Generation_for_Spoken_Dialogue_Models","038_ACL_2025_VReST__Enhancing_Reasoning_in_Large_Vision-Language_Models_through_Tree_Search_and_Self-Reward_Mechanism","051_ACL_2025_Variable_Layerwise_Quantization__A_Simple_and_Effective_Approach_to_Quantize_LLMs","074_ACL_2025_UniConv__Unifying_Retrieval_and_Response_Generation_for_Large_Language_Models_in_Conversations","085_ACL_2025_Uncovering_the_Impact_of_Chain-of-Thought_Reasoning_for_Direct_Preference_Optimization__Lessons_from_Text-to-S","096_ACL_2025_TUMLU__A_Unified_and_Native_Language_Understanding_Benchmark_for_Turkic_Languages","098_ACL_2025_TROVE__A_Challenge_for_Fine-Grained_Text_Provenance_via_Source_Sentence_Tracing_and_Relationship_Classificatio","010_CVPR_2017_Unite_the_People__Closing_the_Loop_Between_3D_and_2D_Human_Representations","017_CVPR_2019_VITAMIN-E__VIsual_Tracking_and_MappINg_With_Extremely_Dense_Feature_Points","026_CVPR_2025_Zero-Shot_Styled_Text_Image_Generation__but_Make_It_Autoregressive","043_CVPR_2025_Weakly_Supervised_Semantic_Segmentation_via_Progressive_Confidence_Region_Expansion","045_CVPR_2025_VTON_360__High-Fidelity_Virtual_Try-On_from_Any_Viewing_Direction","059_CVPR_2025_Vision-Language_Gradient_Descent-driven_All-in-One_Deep_Unfolding_Networks","071_CVPR_2025_VI3NR__Variance_Informed_Initialization_for_Implicit_Neural_Representations","072_CVPR_2025_VGGT__Visual_Geometry_Grounded_Transformer","076_CVPR_2025_VasTSD__Learning_3D_Vascular_Tree-state_Space_Diffusion_Model_for_Angiography_Synthesis","091_CVPR_2025_UniGoal__Towards_Universal_Zero-shot_Goal-oriented_Navigation","092_CVPR_2025_Unified_Medical_Lesion_Segmentation_via_Self-referring_Indicator","096_CVPR_2025_Uncertainty_Weighted_Gradients_for_Model_Calibration","010_ICLR_2023_Merge__Then_Compress__Demystify_Efficient_SMoE_with_Hints_from_Its_Routing_Policy","018_ICLR_2023_Large_Content_And_Behavior_Models_To_Understand__Simulate__And_Optimize_Content_And_Behavior","027_ICLR_2025_ZETA__Leveraging_Z-order_Curves_for_Efficient_Top-k_Attention","034_ICLR_2025_When_is_Task_Vector_Provably_Effective_for_Model_Editing__A_Generalization_Analysis_of_Nonlinear_Transformers","035_ICLR_2025_When_GNNs_meet_symmetry_in_ILPs__an_orbit-based_feature_augmentation_approach","037_ICLR_2025_What_Makes_a_Good_Diffusion_Planner_for_Decision_Making","049_ICLR_2025_VLAS__Vision-Language-Action_Model_With_Speech_Instructions_For_Customized_Robot_Manipulation","054_ICLR_2025_Video_Action_Differencing","062_ICLR_2025_Unlocking_Efficient__Scalable__and_Continual_Knowledge_Editing_with_Basis-Level_Representation_Fine-Tuning","067_ICLR_2025_UniMatch__Universal_Matching_from_Atom_to_Task_for_Few-Shot_Drug_Discovery","075_ICLR_2025_Uni-Sign__Toward_Unified_Sign_Language_Understanding_at_Scale","082_ICLR_2025_Uncertainty-Aware_Decoding_with_Minimum_Bayes_Risk","090_ICLR_2025_Transformer_Meets_Twicing__Harnessing_Unattended_Residual_Information","007_ICML_2023_Correcting_discount-factor_mismatch_in_on-policy_policy_gradient_methods","024_ICML_2023_Approximation_Algorithms_for_Fair_Range_Clustering","002_ICML_2024_Listening_to_the_Noise__Blind_Denoising_with_Gibbs_Diffusion","022_ICML_2024_Sample-Efficient_Robust_Multi-Agent_Reinforcement_Learning_in_the_Face_of_Environmental_Uncertainty","071_ICML_2024_Unlock_the_Cognitive_Generalization_of_Deep_Reinforcement_Learning_via_Granular_Ball_Representation","078_ICML_2024_Understanding_the_Learning_Dynamics_of_Alignment_with_Human_Feedback","079_ICML_2024_Understanding_the_Effects_of_Iterative_Prompting_on_Truthfulness","083_ICML_2024_Understanding_Diffusion_Models_by_Feynman_s_Path_Integral","085_ICML_2024_Uncertainty_for_Active_Learning_on_Graphs","091_ICML_2024_Two_Stones_Hit_One_Bird__Bilevel_Positional_Encoding_for_Better_Length_Extrapolation","100_ICML_2024_Transformers_Learn_Nonlinear_Features_In_Context__Nonconvex_Mean-field_Dynamics_on_the_Attention_Landscape","030_ICML_2025_Exact_Soft_Analytical_Side-Channel_Attacks_using_Tractable_Circuits","035_ICML_2025_Asymptotically-Optimal_Gaussian_Bandits_with_Side_Observations","011_IJCAI_2023_Unbiased_Gradient_Boosting_Decision_Tree_with_Unbiased_Feature_Importance","013_IJCAI_2023_DEIR__Efficient_and_Robust_Exploration_through_Discriminative-Model-Based_Episodic_Intrinsic_Rewards","022_IJCAI_2024_Beyond_Alignment__Blind_Video_Face_Restoration_via_Parsing-Guided_Temporal-Coherent_Transformer","028_IJCAI_2025_X-KAN__Optimizing_Local_Kolmogorov-Arnold_Networks_via_Evolutionary_Rule-Based_Machine_Learning","033_IJCAI_2025_Where_and_When__Predict_Next_POI_and_Its_Explicit_Timestamp_in_Sequential_Recommendation","041_IJCAI_2025_Wave-wise_Discriminative_Tracking_by_Phase-Amplitude_Separation__Augmentation_and_Mixture","054_IJCAI_2025_Variety-Seeking_Jump_Games_on_Graphs","059_IJCAI_2025_Unlocking_the_Potential_of_Lightweight_Quantized_Models_for_Deepfake_Detection","063_IJCAI_2025_Universal_Graph_Self-Contrastive_Learning","071_IJCAI_2025_Two-Stage_Feature_Generation_with_Transformer_and_Reinforcement_Learning","086_IJCAI_2025_Towards_Micro-Action_Recognition_with_Limited_Annotations__An_Asynchronous_Pseudo_Labeling_and_Training_Approa","091_IJCAI_2025_Towards_Debiased_Generalized_Category_Discovery","095_IJCAI_2025_TOTF__Missing-Aware_Encoders_for_Clustering_on_Multi-View_Incomplete_Attributed_Graphs","002_KDD_2025_Why_Not_Together__A_Multiple-Round_Recommender_System_for_Queries_and_Items","018_KDD_2025_Stable_Representation_Learning_on_Graphs_from_Multiple_Environments_with_Structure_Distribution_Shift","024_KDD_2025_SEPTQ__A_Simple_and_Effective_Post-Training_Quantization_Paradigm_for_Large_Language_Models","026_KDD_2025_Seeing_the_Unseen_in_Micro-Video_Popularity_Prediction__Self-Correlation_Retrieval_for_Missing_Modality_Genera","029_KDD_2025_Scaling_the_Vocabulary_of_Non-autoregressive_Models_for_Fast_Generative_Retrieval","030_KDD_2025_ScalaGBM__Memory_Efficient_GBDT_Training_for_High-Dimensional_Data_on_GPU","033_KDD_2025_Safe_Online_Bid_Optimization_with_Return_on_Investment_and_Budget_Constraints","035_KDD_2025_Robust_Uplift_Modeling_with_Large-Scale_Contexts_for_Real-time_Marketing","051_KDD_2025_Partial_Pre-Post_Code_Tree__A_Memory-Efficient_Tree_Structure_for_Conjunctive_Rule_Mining","052_KDD_2025_On_the_Support_Vector_Effect_in_DNNs__Rethinking_Data_Selection_and_Attribution","056_KDD_2025_Noise-Resilient_Point-wise_Anomaly_Detection_in_Time_Series_Using_Weak_Segment_Labels","063_KDD_2025_MobileSteward__Integrating_Multiple_App-Oriented_Agents_with_Self-Evolution_to_Automate_Cross-App_Instructions","012_NeurIPS_2023_Multi-task_Representation_Learning_for_Pure_Exploration_in_Bilinear_Bandits","024_NeurIPS_2023_What_functions_can_Graph_Neural_Networks_compute_on_random_graphs__The_role_of_Positional_Encoding","017_NeurIPS_2024_ReST-MCTS__LLM_Self-Training_via_Process_Reward_Guided_Tree_Search","094_NeurIPS_2024_You_Only_Look_Around__Learning_Illumination_Invariant_Feature_for_Low-light_Object_Detection","096_NeurIPS_2024_XMask3D__Cross-modal_Mask_Reasoning_for_Open_Vocabulary_3D_Semantic_Segmentation","098_NeurIPS_2024_WorldCoder__a_Model-Based_LLM_Agent__Building_World_Models_by_Writing_Code_and_Interacting_with_the_Environmen","099_NeurIPS_2024_Why_Transformers_Need_Adam__A_Hessian_Perspective","026_NeurIPS_2025_Your_contrastive_learning_problem_is_secretly_a_distribution_alignment_problem","051_NeurIPS_2025_Multi-Instance_Partial-Label_Learning_with_Margin_Adjustment","063_NeurIPS_2025_Improving_Environment_Novelty_Quantification_for_Effective_Unsupervised_Environment_Design","078_NeurIPS_2025_Divergence-Augmented_Policy_Optimization","080_NeurIPS_2025_DeTrack__In-model_Latent_Denoising_Learning_for_Visual_Object_Tracking","087_NeurIPS_2025_Aligner-Encoders__Self-Attention_Transformers_Can_Be_Self-Transducers"
]

const paperIds = (Array.isArray(args) && args.length) ? args : PAPER_IDS
if (!paperIds.length) throw new Error('no paper ids')
log(`verifying ${paperIds.length} papers`)

const results = await pipeline(
  paperIds,
  // Stage 1 — per-paper verifier
  (pid) => agent(
    `You are auditing a knowledge-extraction system. Verify, ITEM BY ITEM, that the section-IR extraction
faithfully and completely represents the SOURCE paper.

Read these two files (use the Read tool; the source is large, read it fully and also grep [§N] markers as needed):
  SOURCE paper:   ${SRC_DIR}/${pid}.md
  EXTRACTION:     ${OUT_DIR}/${pid}/06_extraction.json
  (also useful)   ${OUT_DIR}/${pid}/03_references.json   and  ${OUT_DIR}/${pid}/07_validation.json

${CONTRACT}

Be concrete and skeptical. EVERY finding must cite verbatim SOURCE evidence (a quote and/or a §marker you
actually checked). Prefer high-confidence, real defects over nitpicks; but do surface systematic problems
(e.g. all score values empty, provenance markers pointing to the wrong text, a whole results table dropped,
the wrong contribution chosen as root). Score each of the 10 dimensions 1-5. Attribute each finding honestly
to framework_design / model_error / source_quality. Return ONLY the structured object.`,
    { label: `verify:${pid.slice(0,28)}`, phase: 'Verify', schema: VERIFY_SCHEMA, model: 'sonnet', effort: 'high', agentType: 'general-purpose' }
  ),
  // Stage 2 — adversarial re-check of high/medium findings (skip if none)
  async (v, pid) => {
    if (!v || !v.findings) return { paper_id: pid, verdicts: [], _verify: v }
    const flagged = v.findings
      .map((f, i) => ({ ...f, _i: i }))
      .filter((f) => f.severity === 'high' || f.severity === 'medium')
    if (!flagged.length) return { paper_id: pid, verdicts: [], _verify: v }
    const list = flagged.map((f) => `#${f._i} [${f.severity}/${f.dimension}/${f.attribution}] ${f.description}
    SOURCE_EVIDENCE: ${f.source_evidence}
    EXTRACTION_FRAGMENT: ${f.extraction_fragment}`).join('\n\n')
    const adv = await agent(
      `You are an ADVERSARIAL reviewer. Another auditor flagged issues in a section-IR extraction. Your job is to
REFUTE each one unless the SOURCE clearly supports it. Re-read the primary sources yourself:
  SOURCE paper: ${SRC_DIR}/${pid}.md
  EXTRACTION:   ${OUT_DIR}/${pid}/06_extraction.json

${CONTRACT}

For each flagged finding below, return a verdict: 'confirmed' (source clearly proves the defect),
'refuted' (the extraction is actually fine, OR the "defect" is intended-by-design per the contract above,
OR the source evidence does not support it), or 'downgraded' (real but minor/overstated). Also give the
CORRECTED attribution (watch for framework_design claims that are really model_error or by-design). Default
to 'refuted' when uncertain. Findings to adjudicate:\n\n${list}`,
      { label: `adv:${pid.slice(0,30)}`, phase: 'Adversary', schema: ADVERSARY_SCHEMA, effort: 'high', agentType: 'general-purpose' }
    )
    return { paper_id: pid, verdicts: (adv && adv.verdicts) || [], _verify: v }
  }
)

// Merge verify + verdicts into a flat per-paper record
const merged = results.filter(Boolean).map((r) => {
  const v = r._verify || {}
  const verdictByIdx = {}
  for (const vd of r.verdicts || []) verdictByIdx[vd.finding_index] = vd
  const findings = (v.findings || []).map((f, i) => ({
    ...f,
    verdict: verdictByIdx[i] ? verdictByIdx[i].verdict : (f.severity === 'low' ? 'unreviewed_low' : 'unreviewed'),
    corrected_attribution: verdictByIdx[i] ? verdictByIdx[i].corrected_attribution : f.attribution,
    adversary_note: verdictByIdx[i] ? verdictByIdx[i].note : '',
  }))
  return {
    paper_id: v.paper_id || r.paper_id,
    actual_title: v.actual_title || '',
    label_faithful: v.label_faithful,
    coherent_paper: v.coherent_paper,
    dimension_scores: v.dimension_scores || {},
    summary: v.summary || '',
    findings,
  }
})

// Aggregate the confirmed (or unreviewed-but-present) findings for the synthesis phase
const confirmed = merged.flatMap((m) =>
  m.findings.filter((f) => f.verdict === 'confirmed' || f.verdict === 'downgraded' || f.verdict === 'unreviewed')
    .map((f) => ({ paper_id: m.paper_id, ...f }))
)
const byDimAttr = {}
for (const f of confirmed) {
  const k = `${f.dimension} | ${f.corrected_attribution}`
  byDimAttr[k] = (byDimAttr[k] || 0) + 1
}
log(`confirmed/retained findings: ${confirmed.length} across ${merged.length} papers`)

return { papers: merged, confirmed_count: confirmed.length, by_dimension_attribution: byDimAttr }
