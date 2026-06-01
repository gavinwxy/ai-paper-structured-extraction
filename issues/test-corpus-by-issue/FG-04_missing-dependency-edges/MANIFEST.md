# FG-04_missing-dependency-edges  —  关系矩阵缺依赖边

> builds_on 角色无对应边(塞进 part_of 或成孤儿);compared_against 混淆 baseline 与相关工作引用。

**全语料命中:** 449 篇  ·  **本目录选中:** 18 篇(按命中强度 + 会议多样性)

**修复后检查:** 修复后期望:`jq '[.relations[].relation]|group_by(.)'` 出现 builds_on/uses 边;builds_on 方法不再挂在 part_of 上。

| # | paper | venue | strength | 命中证据 |
|---|---|---|---|---|
| 1 | 002_ACL_2025_Your_Model_is_Overconfident__and_Other_Lies_We_Tell_Ourselves | ACL | 3 | builds_on=10 (on part_of:2); compared_against unscored=6/6 |
| 2 | 003_CVPR_2006_A_Mean_Field_EM-algorithm_for_Coherent_Occlusion_Handling_in_MAP-Estimation_Prob | CVPR | 3 | builds_on=8 (on part_of:8); compared_against unscored=6/6 |
| 3 | 003_ICML_2024_Various_Lengths__Constant_Speed__Efficient_Language_Modeling_with_Lightning_Attention | ICML | 3 | builds_on=1 (on part_of:1); compared_against unscored=9/29 |
| 4 | 004_IJCAI_2007_A_Heuristic_Search_Approach_to_Planning_with_Temporally_Extended_Preferences | IJCAI | 3 | builds_on=2 (on part_of:2); compared_against unscored=8/12 |
| 5 | 009_NeurIPS_2023_Beyond_Normal__On_the_Evaluation_of_Mutual_Information_Estimators | NeurIPS | 3 | builds_on=10 (on part_of:10); compared_against unscored=9/9 |
| 6 | 011_KDD_2025_Towards_Controllable_Hybrid_Fairness_in_Graph_Neural_Networks | KDD | 3 | builds_on=1 (on part_of:1); compared_against unscored=34/34 |
| 7 | 016_ICLR_2023_Quantifying_and_Mitigating_the_Impact_of_Label_Errors_on_Model_Disparity_Metrics | ICLR | 3 | builds_on=5 (on part_of:5); compared_against unscored=5/7 |
| 8 | 031_AAAI_2025_WPMixer__Efficient_Multi-Resolution_Mixing_for_Long-Term_Time_Series_Forecasting | AAAI | 3 | builds_on=2 (on part_of:2); compared_against unscored=5/6 |
| 9 | 008_ACL_2025_Words_of_Warmth__Trust_and_Sociability_Norms_for_over_26k_English_Words | ACL | 3 | builds_on=4 (on part_of:4); compared_against unscored=7/7 |
| 10 | 016_CVPR_2019_Smooth_Shells__Multi-Scale_Shape_Registration_With_Functional_Maps | CVPR | 3 | builds_on=4 (on part_of:3); compared_against unscored=6/11 |
| 11 | 017_ICML_2009_Non-monotonic_feature_selection | ICML | 3 | builds_on=2 (on part_of:2); compared_against unscored=6/6 |
| 12 | 010_IJCAI_2023_ScriptWorld__Text_Based_Environment_For_Learning_Procedural_Knowledge | IJCAI | 3 | builds_on=2 (on part_of:2); compared_against unscored=5/9 |
| 13 | 021_NeurIPS_2023_Stability_and_Generalization_of_the_Decentralized_Stochastic_Gradient_Descent_Ascent_Algorithm | NeurIPS | 3 | builds_on=1 (on part_of:1); compared_against unscored=7/7 |
| 14 | 027_KDD_2025_SCode__A_Spherical_Code_Metric_Learning_Approach_to_Continuously_Monitoring_Predictive_Events_in_Networked_Dat | KDD | 3 | builds_on=1 (on part_of:1); compared_against unscored=11/12 |
| 15 | 053_ICLR_2025_VideoGrain__Modulating_Space-Time_Attention_for_Multi-grained_Video_Editing | ICLR | 3 | builds_on=1 (on part_of:1); compared_against unscored=7/7 |
| 16 | 037_AAAI_2025_When_to_Learn_and_When_to_Stop__Quitting_at_the_Optimal_Time__Student_Abstract | AAAI | 3 | builds_on=1 (on part_of:1); compared_against unscored=20/20 |
| 17 | 019_ACL_2025_White_Men_Lead__Black_Women_Help__Benchmarking_and_Mitigating_Language_Agency_Social_Biases_in_LLMs | ACL | 3 | builds_on=16 (on part_of:16); compared_against unscored=10/10 |
| 18 | 018_CVPR_2020_BFBox__Searching_Face-Appropriate_Backbone_and_Feature_Pyramid_Network_for_Face_Detector | CVPR | 3 | builds_on=2 (on part_of:2); compared_against unscored=12/23 |
