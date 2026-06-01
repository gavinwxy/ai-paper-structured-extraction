# FG-01_contribution-must-be-method  —  贡献必须是 Method

> benchmark/数据集/资源类的真实贡献被误塞进 Method[algorithm] 并复制成无连接的 ExperimentSetup 双胞胎。

**全语料命中:** 77 篇  ·  **本目录选中:** 25 篇(按命中强度 + 会议多样性)

**修复后检查:** 修复后期望:.document/.sections 中贡献可为 ExperimentSetup/Resource,或 method_kind∈{dataset,benchmark,resource};检查 `jq '.sections[].units[]|select(.role=="contribution")|{type,name,method_kind}'`

| # | paper | venue | strength | 命中证据 |
|---|---|---|---|---|
| 1 | 007_IJCAI_2009_An_Empirical_Study_about_the_Effects_of_Interlocking_Directorates_Strategy_on_the_Firm_s_Output_in_the_Dynamic | IJCAI | 3 | contribution 'Random-effects GLS regression' kind=algorithm +DUAL-as-ExperimentSetup |
| 2 | 010_ACL_2025_WikiMixQA__A_Multimodal_Benchmark_for_Question_Answering_over_Tables_and_Charts | ACL | 3 | contribution 'Chart-HQA' kind=None +DUAL-as-ExperimentSetup |
| 3 | 015_CVPR_2020_GraspNet-1Billion__A_Large-Scale_Benchmark_for_General_Object_Grasping | CVPR | 3 | contribution 'GraspNet-1Billion' kind=algorithm +DUAL-as-ExperimentSetup |
| 4 | 030_NeurIPS_2025_Unveiling_Causal_Reasoning_in_Large_Language_Models__Reality_or_Mirage | NeurIPS | 3 | contribution 'ExpliCa' kind=None +DUAL-as-ExperimentSetup |
| 5 | 047_ICLR_2025_VOILA__Evaluation_of_MLLMs_For_Perceptual_Understanding_and_Analogical_Reasoning | ICLR | 3 | contribution 'I-RAVEN-X with perceptual uncertainty' kind=algorithm +DUAL-as-ExperimentSetup |
| 6 | 055_ICML_2024_VisionGraph__Leveraging_Large_Multimodal_Models_for_Graph_Theory_Problems_in_Visual_Context | ICML | 3 | contribution 'VisionGraph' kind=algorithm +DUAL-as-ExperimentSetup |
| 7 | 011_KDD_2025_Towards_Controllable_Hybrid_Fairness_in_Graph_Neural_Networks | KDD | 1 | contribution 'Fairness-Aware GNN Survey' kind=algorithm |
| 8 | 021_AAAI_2024_Towards_Adversarially_Robust_Dataset_Distillation_by_Curvature_Regularization | AAAI | 1 | contribution 'GUARD' kind=training_strategy |
| 9 | 009_IJCAI_2023_GRASP__A_novel_benchmark_for_evaluating_language_GRounding_And_Situated_Physics_understanding_in_multimodal_la | IJCAI | 1 | contribution 'GRASP' kind=algorithm |
| 10 | 030_ACL_2025_What_Is_That_Talk_About__A_Video-to-Text_Summarization_Dataset_for_Scientific_Presentations | ACL | 3 | contribution 'VISTA' kind=algorithm +DUAL-as-ExperimentSetup |
| 11 | 022_CVPR_2020_Taking_a_Deeper_Look_at_Co-Salient_Object_Detection | CVPR | 3 | contribution 'CoSOD3k' kind=algorithm +DUAL-as-ExperimentSetup |
| 12 | 074_NeurIPS_2025_EgoSim__An_Egocentric_Multi-view_Simulator_and_Real_Dataset_for_Body-worn_Cameras_during_Motion_and_Activity | NeurIPS | 3 | contribution 'EMHI' kind=algorithm +DUAL-as-ExperimentSetup |
| 13 | 084_ICLR_2025_UGMathBench__A_Diverse_and_Dynamic_Benchmark_for_Undergraduate-Level_Mathematical_Reasoning_with_Large_Languag | ICLR | 3 | contribution 'UGMathBench' kind=algorithm +DUAL-as-ExperimentSetup |
| 14 | 004_ICML_2023_Curated_LLM__Synergy_of_LLMs_and_Data_Curation_for_tabular_augmentation_in_ultra_low-data_regimes | ICML | 1 | contribution 'CLLM' kind=algorithm |
| 15 | 015_KDD_2025_Tackling_the_Length_Barrier__Dynamic_Context_Browsing_for_Knowledge-Intensive_Task | KDD | 1 | contribution 'Crosslingual RAG (CrossRAG)' kind=algorithm |
| 16 | 033_AAAI_2025_WildFake__A_Large-Scale_and_Hierarchical_Dataset_for_AI-Generated_Images_Detection | AAAI | 1 | contribution 'Semi-TRUTHS' kind=algorithm |
| 17 | 047_IJCAI_2025_VimGeo__Efficient_Cross-View_Geo-Localization_with_Vision_Mamba_Architecture | IJCAI | 1 | contribution 'Cross-View Feature Translation' kind=algorithm |
| 18 | 041_ACL_2025_VLM2-Bench__A_Closer_Look_at_How_Well_VLMs_Implicitly_Link_Explicit_Matching_Visual_Cues | ACL | 3 | contribution 'VLM²-Bench' kind=algorithm +DUAL-as-ExperimentSetup |
| 19 | 073_CVPR_2025_VEU-Bench__Towards_Comprehensive_Understanding_of_Video_Editing | CVPR | 3 | contribution 'E.T. Bench' kind=algorithm +DUAL-as-ExperimentSetup |
| 20 | 033_NeurIPS_2025_The_iNaturalist_Sounds_Dataset | NeurIPS | 2 | contribution 'Manikin-Recorded Cardiopulmonary Sounds ' kind=None |
| 21 | 030_ICLR_2025_ZAPBench__A_Benchmark_for_Whole-Brain_Activity_Prediction_in_Zebrafish | ICLR | 2 | contribution 'Z-Brain atlas' kind=algorithm |
| 22 | 015_ICML_2024_Active_Label_Correction_for_Semantic_Segmentation_with_Foundation_Models | ICML | 1 | contribution 'Active Label Correction (ALC) Framework' kind=algorithm |
| 23 | 053_KDD_2025_On_the_Necessity_of_World_Knowledge_for_Mitigating_Missing_Labels_in_Extreme_Classification | KDD | 1 | contribution 'SKIM' kind=algorithm |
| 24 | 063_AAAI_2025_VE-Bench__Subjective-Aligned_Benchmark_Suite_for_Text-Driven_Video_Editing_Quality_Assessment | AAAI | 1 | contribution 'VE-Bench' kind=algorithm |
| 25 | 057_IJCAI_2025_Unveiling_Maternity_and_Infant_Care_Conversations__A_Chinese_Dialogue_Dataset_for_Enhanced_Parenting_Support | IJCAI | 1 | contribution 'CARE-MI' kind=algorithm |
