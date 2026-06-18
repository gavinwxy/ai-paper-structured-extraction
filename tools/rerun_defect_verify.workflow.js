export const meta = {
  name: 'rerun-defect-verify',
  description: 'Check each baseline framework defect against the re-run (new code+prompts) extraction',
  phases: [
    { title: 'Check', detail: 'one agent per paper: is each baseline defect fixed in the re-run?' },
    { title: 'Skeptic', detail: 'adversarial re-check of every fixed claim' },
  ],
}

const ROOT = '/Users/wxy/projects/knowledge-ontology-ai-focused'
const DOSSIER = `${ROOT}/production-outputs/rerun_defect_dossiers.json`
// The 52 defect-bearing paper ids (embedded — the runtime does not pass args through as an array).
const PIDS = ["002_AAAI_2024_Exploring_Diverse_Representations_for_Open_Set_Recognition", "024_AAAI_2024_Text2Data__Low-Resource_Data_Generation_with_Textual_Control", "038_AAAI_2025_When_Shadow_Removal_Meets_Intrinsic_Image_Decomposition__A_Joint_Learning_Framework_Using_Unpaired_Data", "055_AAAI_2025_VisRec__A_Semi-Supervised_Approach_to_Visibility_Data_Reconstruction_in_Radio_Astronomy", "064_AAAI_2025_VarDrop__Enhancing_Training_Efficiency_by_Reducing_Variate_Redundancy_in_Periodic_Time_Series_Forecasting", "081_AAAI_2025_Unified_Graph_Neural_Networks_Pre-training_for_Multi-domain_Graphs", "095_AAAI_2025_Tri-Ergon__Fine-Grained_Video-to-Audio_Generation_with_Multi-Modal_Conditions_and_LUFS_Control", "002_ACL_2025_Your_Model_is_Overconfident__and_Other_Lies_We_Tell_Ourselves", "016_ACL_2025_Why_Not_Act_on_What_You_Know__Unleashing_Safety_Potential_of_LLMs_via_Self-Aware_Guard_Enhancement", "022_ACL_2025_Where_Are_We__Evaluating_LLM_Performance_on_African_Languages", "038_ACL_2025_VReST__Enhancing_Reasoning_in_Large_Vision-Language_Models_through_Tree_Search_and_Self-Reward_Mechanism", "051_ACL_2025_Variable_Layerwise_Quantization__A_Simple_and_Effective_Approach_to_Quantize_LLMs", "074_ACL_2025_UniConv__Unifying_Retrieval_and_Response_Generation_for_Large_Language_Models_in_Conversations", "096_ACL_2025_TUMLU__A_Unified_and_Native_Language_Understanding_Benchmark_for_Turkic_Languages", "043_CVPR_2025_Weakly_Supervised_Semantic_Segmentation_via_Progressive_Confidence_Region_Expansion", "059_CVPR_2025_Vision-Language_Gradient_Descent-driven_All-in-One_Deep_Unfolding_Networks", "076_CVPR_2025_VasTSD__Learning_3D_Vascular_Tree-state_Space_Diffusion_Model_for_Angiography_Synthesis", "096_CVPR_2025_Uncertainty_Weighted_Gradients_for_Model_Calibration", "010_ICLR_2023_Merge__Then_Compress__Demystify_Efficient_SMoE_with_Hints_from_Its_Routing_Policy", "018_ICLR_2023_Large_Content_And_Behavior_Models_To_Understand__Simulate__And_Optimize_Content_And_Behavior", "027_ICLR_2025_ZETA__Leveraging_Z-order_Curves_for_Efficient_Top-k_Attention", "035_ICLR_2025_When_GNNs_meet_symmetry_in_ILPs__an_orbit-based_feature_augmentation_approach", "037_ICLR_2025_What_Makes_a_Good_Diffusion_Planner_for_Decision_Making", "049_ICLR_2025_VLAS__Vision-Language-Action_Model_With_Speech_Instructions_For_Customized_Robot_Manipulation", "054_ICLR_2025_Video_Action_Differencing", "062_ICLR_2025_Unlocking_Efficient__Scalable__and_Continual_Knowledge_Editing_with_Basis-Level_Representation_Fine-Tuning", "067_ICLR_2025_UniMatch__Universal_Matching_from_Atom_to_Task_for_Few-Shot_Drug_Discovery", "082_ICLR_2025_Uncertainty-Aware_Decoding_with_Minimum_Bayes_Risk", "090_ICLR_2025_Transformer_Meets_Twicing__Harnessing_Unattended_Residual_Information", "071_ICML_2024_Unlock_the_Cognitive_Generalization_of_Deep_Reinforcement_Learning_via_Granular_Ball_Representation", "078_ICML_2024_Understanding_the_Learning_Dynamics_of_Alignment_with_Human_Feedback", "079_ICML_2024_Understanding_the_Effects_of_Iterative_Prompting_on_Truthfulness", "030_ICML_2025_Exact_Soft_Analytical_Side-Channel_Attacks_using_Tractable_Circuits", "035_ICML_2025_Asymptotically-Optimal_Gaussian_Bandits_with_Side_Observations", "033_IJCAI_2025_Where_and_When__Predict_Next_POI_and_Its_Explicit_Timestamp_in_Sequential_Recommendation", "041_IJCAI_2025_Wave-wise_Discriminative_Tracking_by_Phase-Amplitude_Separation__Augmentation_and_Mixture", "054_IJCAI_2025_Variety-Seeking_Jump_Games_on_Graphs", "071_IJCAI_2025_Two-Stage_Feature_Generation_with_Transformer_and_Reinforcement_Learning", "018_KDD_2025_Stable_Representation_Learning_on_Graphs_from_Multiple_Environments_with_Structure_Distribution_Shift", "024_KDD_2025_SEPTQ__A_Simple_and_Effective_Post-Training_Quantization_Paradigm_for_Large_Language_Models", "029_KDD_2025_Scaling_the_Vocabulary_of_Non-autoregressive_Models_for_Fast_Generative_Retrieval", "030_KDD_2025_ScalaGBM__Memory_Efficient_GBDT_Training_for_High-Dimensional_Data_on_GPU", "033_KDD_2025_Safe_Online_Bid_Optimization_with_Return_on_Investment_and_Budget_Constraints", "052_KDD_2025_On_the_Support_Vector_Effect_in_DNNs__Rethinking_Data_Selection_and_Attribution", "056_KDD_2025_Noise-Resilient_Point-wise_Anomaly_Detection_in_Time_Series_Using_Weak_Segment_Labels", "012_NeurIPS_2023_Multi-task_Representation_Learning_for_Pure_Exploration_in_Bilinear_Bandits", "024_NeurIPS_2023_What_functions_can_Graph_Neural_Networks_compute_on_random_graphs__The_role_of_Positional_Encoding", "094_NeurIPS_2024_You_Only_Look_Around__Learning_Illumination_Invariant_Feature_for_Low-light_Object_Detection", "099_NeurIPS_2024_Why_Transformers_Need_Adam__A_Hessian_Perspective", "026_NeurIPS_2025_Your_contrastive_learning_problem_is_secretly_a_distribution_alignment_problem", "063_NeurIPS_2025_Improving_Environment_Novelty_Quantification_for_Effective_Unsupervised_Environment_Design", "080_NeurIPS_2025_DeTrack__In-model_Latent_Denoising_Learning_for_Visual_Object_Tracking"]
// args = array of paper-id strings; falls back to PIDS. Each agent reads its dossier entry from DOSSIER.
const pids = Array.isArray(args) && args.length ? args : PIDS
if (!pids.length) throw new Error('pass the paper-id list as args (JSON array of strings)')

// Background on the framework fixes under test, so a "fixed" judgement is calibrated
// to the INTENDED behaviour rather than to the verifier's earlier expectation.
const FIXES = `
The re-run applied these section-ir-0.17 framework fixes (code + prompts):
- FD-1 (provenance): unit/relation provenance markers [§N] are SEQUENTIAL input-chunk ids, not
  author section numbers. Assembly now RESOLVES an author label like "§3.1" to the real chunk that
  prints under that heading (instead of truncating §3.1->§3, which used to alias the method to the
  abstract/affiliation block). A method Component should now cite the chunk where the method is
  actually described, not §1/§2/§3 boilerplate. extraction_notes.provenance_resolution reports the
  resolve rate.
- FD-2 (resolves): the assembly attaches the 'resolves' relation only to the ONE headline finding
  per contribution root, not to every contribution-finding. So a paper should have few resolves
  edges (roughly one per contribution), not one per finding.
- FD-4 (theory): theory/proof papers should surface their theorems/lemmas/bounds as Components
  (method_kind theorem/lemma) and formal-result Findings (kind theorem/lemma/bound). The census +
  evidence prompts now nudge this; it is partly model-recall-bound.
- FD-5 (env mis-mint): an environment / simulator / game / scenario the method is merely EVALUATED
  in must be an ExperimentSetup (kind dataset or task), NOT a con:*_dataset / con:*_benchmark
  Contribution. Releasing a dataset is still a Contribution; running on one is an ExperimentSetup.
- FD-6 (structural validity): assembly strips unknown unit fields and backfills Measure unit /
  Measure+Finding provenance, so papers that were schema-invalid should now validate.
INTENTIONAL design (NOT defects — never mark these "still present"): external prior-art / base
models are not census nodes (citation layer handles them); apparatus (GPUs, scoring models) is not
a node; baseline numbers stay in the verbatim blob; Findings are born in the evidence pass.`

const CHECK_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['pid', 'verdicts', 'overall'],
  properties: {
    pid: { type: 'string' },
    overall: { type: 'string', enum: ['all_fixed', 'mostly_fixed', 'mixed', 'mostly_unfixed', 'regressed'] },
    verdicts: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        required: ['defect_summary', 'dimension', 'status', 'evidence'],
        properties: {
          defect_summary: { type: 'string', description: 'one-line restatement of the baseline defect' },
          dimension: { type: 'string' },
          status: { type: 'string', enum: ['fixed', 'partially_fixed', 'still_present', 'not_applicable', 'new_regression'] },
          evidence: { type: 'string', description: 'cite the specific new-extraction unit/relation/provenance and the source span that proves the status' },
        },
      },
    },
    new_regressions: { type: 'string', description: 'any NEW framework-level problem introduced by the re-run that was not in the baseline defect list; empty if none' },
  },
}

const SKEPTIC_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['defect_summary', 'agree_fixed', 'reason'],
  properties: {
    defect_summary: { type: 'string' },
    agree_fixed: { type: 'boolean', description: 'true only if the defect is genuinely resolved in the new extraction; default to false when uncertain' },
    reason: { type: 'string', description: 'cite the new extraction + source; explain why the fix holds or does not' },
  },
}

function checkPrompt(pid) {
  return `You are auditing whether specific extraction defects were fixed by a framework revision.

Paper id: ${pid}

STEP 1 — load this paper's dossier. Read ${DOSSIER} (a JSON array). Find the object whose "pid" ==
"${pid}". It has: "md" (absolute path to the source paper markdown), "new_dir" (relative path under
production-outputs/ to the re-run output folder), and "defects" (the baseline framework-design
defects found in the OLD extraction).

STEP 2 — read the source paper at that "md" path, and read the NEW extraction at
${ROOT}/production-outputs/<new_dir>/06_extraction.json. For context you MAY also read the OLD
extraction at ${ROOT}/production-outputs/eval_8x100_sample100_v0.17/${pid}/06_extraction.json.

${FIXES}

STEP 3 — for EACH defect in the dossier, decide its status in the NEW extraction:
- fixed: the defect is gone and the new extraction is correct on this point.
- partially_fixed: improved but not fully correct.
- still_present: the same defect remains.
- not_applicable: the new structure no longer has the element the defect referred to, in a correct way.
- new_regression: the fix overcorrected and created a different framework-level error here.
Quote the concrete new-extraction unit/relation/provenance marker and the matching source span as
evidence. Be strict: only say "fixed" if you verified it against the source. Set defect_summary to a
one-line restatement of the dossier defect (in dossier order). Also report any NEW framework-level
regression you notice elsewhere in the new extraction (new_regressions field).
Return JSON matching the schema, with pid="${pid}".`
}

function skepticPrompt(pid, v) {
  return `Adversarially re-check a claimed fix. Default to NOT fixed unless the evidence is airtight.

Paper id: ${pid}
Load the dossier entry for this pid from ${DOSSIER} to get the source "md" path and "new_dir".
Read the source paper and the NEW extraction at
${ROOT}/production-outputs/<new_dir>/06_extraction.json.

${FIXES}

A first auditor claims this defect is now FIXED:
  defect: ${v.defect_summary} [${v.dimension}]
  their evidence: ${v.evidence}

Try to REFUTE the "fixed" claim: look for the defect still present, only cosmetically moved, or
replaced by a different framework error. Set agree_fixed=true only if you independently confirm it is
genuinely resolved. Return JSON with defect_summary="${v.defect_summary}".`
}

const results = await pipeline(
  pids,
  pid => agent(checkPrompt(pid), { label: `check:${pid.slice(0, 28)}`, phase: 'Check', schema: CHECK_SCHEMA, agentType: 'Explore' })
    .then(chk => ({ pid, chk })),
  ({ pid, chk }) => {
    const fixed = (chk?.verdicts || []).filter(v => v.status === 'fixed')
    if (!fixed.length) return { pid, overall: chk?.overall, check: chk, skeptic: [] }
    return parallel(fixed.map(v => () =>
      agent(skepticPrompt(pid, v), { label: `skeptic:${pid.slice(0, 22)}`, phase: 'Skeptic', schema: SKEPTIC_SCHEMA })
        .then(s => s).catch(() => null)
    )).then(sk => ({ pid, overall: chk?.overall, check: chk, skeptic: sk.filter(Boolean) }))
  }
)

const out = results.filter(Boolean)
let fixed = 0, partial = 0, still = 0, na = 0, reg = 0, skepticOverturn = 0
for (const r of out) {
  for (const v of (r.check?.verdicts || [])) {
    if (v.status === 'fixed') fixed++
    else if (v.status === 'partially_fixed') partial++
    else if (v.status === 'still_present') still++
    else if (v.status === 'not_applicable') na++
    else if (v.status === 'new_regression') reg++
  }
  for (const s of (r.skeptic || [])) if (s && s.agree_fixed === false) skepticOverturn++
}
log(`defects: fixed=${fixed} partial=${partial} still=${still} n/a=${na} regr=${reg}; skeptic overturned ${skepticOverturn} fixed-claims`)
return { tally: { fixed, partial, still, na, reg, skepticOverturn, papers: out.length }, papers: out }
