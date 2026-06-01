# FG-06_non-leaderboard-eval  —  非榜单评测不适配

> 成对/胜率/裁判评测的对手与裁判塌进 variant 串;空 value。

**全语料命中:** 86 篇  ·  **本目录选中:** 20 篇(按命中强度 + 会议多样性)

**修复后检查:** 修复后期望:scores 行出现 opponent_id/judge_id,或 pairwise_preference 子类型;无空 value。

| # | paper | venue | strength | 命中证据 |
|---|---|---|---|---|
| 1 | 001_KDD_2025_YaART__Yet_Another_ART_Rendering_Technology | KDD | 2 | judge/pairwise measures=['Side-by-side human p', 'Side-by-side human p', 'Side-by-side human p']; empty-value measures=0 |
| 2 | 002_ICLR_2024_Are_Models_Biased_on_Text_without_Gender-related_Language | ICLR | 2 | judge/pairwise measures=['Preferences disparit']; empty-value measures=0 |
| 3 | 005_ACL_2025_YESciEval__Robust_LLM-as-a-Judge_for_Scientific_Question_Answering | ACL | 2 | judge/pairwise measures=['Preference Ranking']; empty-value measures=0 |
| 4 | 010_NeurIPS_2024_Transformers_represent_belief_state_geometry_in_their_residual_stream | NeurIPS | 2 | judge/pairwise measures=['R² (Pairwise Distanc']; empty-value measures=0 |
| 5 | 026_CVPR_2025_Zero-Shot_Styled_Text_Image_Generation__but_Make_It_Autoregressive | CVPR | 2 | judge/pairwise measures=['User Preference']; empty-value measures=0 |
| 6 | 037_ICML_2024_Zero-Shot_Unsupervised_and_Text-Based_Audio_Editing_Using_DDPM_Inversion | ICML | 2 | judge/pairwise measures=['User study preferenc']; empty-value measures=0 |
| 7 | 077_AAAI_2025_Universal_Post-Processing_Networks_for_Joint_Optimization_of_Modules_in_Task-Oriented_Dialogue_Systems | AAAI | 2 | judge/pairwise measures=['Success Rate (Human ', 'Turns (Human Evaluat']; empty-value measures=0 |
| 8 | 006_IJCAI_2024_Dynamic_and_Adaptive_Feature_Generation_with_LLM | IJCAI | 1 | judge/pairwise measures=[]; empty-value measures=4 |
| 9 | 010_KDD_2025_Towards_Web-scale_Recommendations_with_LLMs__From_Quality-aware_Ranking_to_Candidate_Generation | KDD | 2 | judge/pairwise measures=['Exact Match / F1 und', 'Exact Match / F1 und']; empty-value measures=0 |
| 10 | 041_ICLR_2025_Weakly-Supervised_Affordance_Grounding_Guided_by_Part-Level_Semantic_Priors | ICLR | 2 | judge/pairwise measures=['User study MOS (Fine', 'User study MOS (Sepa']; empty-value measures=0 |
| 11 | 010_ACL_2025_WikiMixQA__A_Multimodal_Benchmark_for_Question_Answering_over_Tables_and_Charts | ACL | 2 | judge/pairwise measures=['Human Evaluation Sco']; empty-value measures=0 |
| 12 | 014_NeurIPS_2024_AttnDreamBooth__Towards_Text-Aligned_Personalized_Text-to-Image_Generation | NeurIPS | 2 | judge/pairwise measures=['User Study Preferenc']; empty-value measures=0 |
| 13 | 036_CVPR_2025_Words_or_Vision__Do_Vision-Language_Models_Have_Blind_Faith_in_Text | CVPR | 2 | judge/pairwise measures=['Text Preference Rati', 'Text Preference Rati', 'Text Preference Rati']; empty-value measures=0 |
| 14 | 003_ICML_2024_Various_Lengths__Constant_Speed__Efficient_Language_Modeling_with_Lightning_Attention | ICML | 1 | judge/pairwise measures=[]; empty-value measures=10 |
| 15 | 080_AAAI_2025_Union_Is_Strength__Unite_the_Power_of_LLMs_and_MLLMs_for_Chart_Question_Answering | AAAI | 2 | judge/pairwise measures=['Human Preference']; empty-value measures=0 |
| 16 | 011_IJCAI_2023_Unbiased_Gradient_Boosting_Decision_Tree_with_Unbiased_Feature_Importance | IJCAI | 1 | judge/pairwise measures=[]; empty-value measures=2 |
| 17 | 015_KDD_2025_Tackling_the_Length_Barrier__Dynamic_Context_Browsing_for_Knowledge-Intensive_Task | KDD | 1 | judge/pairwise measures=[]; empty-value measures=5 |
| 18 | 049_ICLR_2025_VLAS__Vision-Language-Action_Model_With_Speech_Instructions_For_Customized_Robot_Manipulation | ICLR | 2 | judge/pairwise measures=['Customization task s']; empty-value measures=0 |
| 19 | 042_ACL_2025_VITAL__A_New_Dataset_for_Benchmarking_Pluralistic_Alignment_in_Healthcare | ACL | 2 | judge/pairwise measures=['human evaluation win', 'GPT-4 judge win rate']; empty-value measures=0 |
| 20 | 001_NeurIPS_2023_Re-Think_and_Re-Design_Graph_Neural_Networks_in_Spaces_of_Continuous_Graph_Diffusion_Functionals | NeurIPS | 1 | judge/pairwise measures=[]; empty-value measures=2 |
