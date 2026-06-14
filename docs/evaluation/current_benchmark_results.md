# Current ICTU Benchmark Results

- Dataset: `docs/evaluation/ictu_30_questions_dataset.json`
- Dataset SHA-256: `da8d680cea6a9058a7cbe6ac62ce3839aa799e93870eedd0b58d90cb751c794e`
- Generated at: `2026-06-14T01:56:34+07:00`
- Router mode requested: `keyword`
- Route Accuracy: **96.67%**
- Source Top-1: **86.67%**
- Source Top-3: **86.67%**
- MRR: **0.8800**
- Fallback count: **8**
- Latency ms: min=48.81, max=19934.01, mean=6223.16, median=4412.59, p95=12913.73

## Cases

| ID | Router mode | Selected tool | Source rank | Latency ms | Result |
| --- | --- | --- | ---: | ---: | --- |
| local_001 | keyword | student_handbook_rag | 1 | 2930.34 | pass |
| local_002 | keyword | student_handbook_rag | 1 | 2076.08 | pass |
| local_003 | keyword | student_handbook_rag | 1 | 907.27 | pass |
| local_004 | keyword | student_handbook_rag | 1 | 804.55 | pass |
| local_005 | keyword | general_ictu_rag | - | 48.81 | fail |
| local_006 | keyword | student_handbook_rag | 1 | 2007.36 | pass |
| local_007 | keyword | student_handbook_rag | 1 | 1542.61 | pass |
| local_008 | keyword | student_handbook_rag | 1 | 1091.19 | pass |
| local_009 | keyword | student_handbook_rag | 1 | 1936.68 | pass |
| local_010 | keyword | student_handbook_rag | 1 | 1996.52 | pass |
| local_011 | keyword | student_handbook_rag | 1 | 2007.72 | pass |
| local_012 | keyword | student_handbook_rag | 1 | 1111.54 | pass |
| local_013 | keyword | student_handbook_rag | 1 | 938.01 | pass |
| local_014 | keyword | student_handbook_rag | 1 | 1080.29 | pass |
| local_015 | keyword | student_faq_rag | 5 | 1736.37 | pass |
| web_001 | keyword | general_ictu_rag | - | 11073.63 | pass |
| web_002 | keyword | general_ictu_rag | - | 10400.88 | pass |
| web_003 | keyword | general_ictu_rag | - | 19934.01 | pass |
| web_004 | keyword | general_ictu_rag | - | 10572.4 | pass |
| web_005 | keyword | academic_policy_rag | - | 10480.26 | pass |
| web_006 | keyword | student_faq_rag | - | 12913.73 | pass |
| web_007 | keyword | student_faq_rag | - | 9912.98 | pass |
| web_008 | keyword | student_faq_rag | - | 10597.22 | pass |
| web_009 | keyword | student_faq_rag | - | 10198.57 | pass |
| web_010 | keyword | academic_policy_rag | - | 10269.71 | pass |
| web_011 | keyword | student_faq_rag | - | 10427.31 | pass |
| web_012 | keyword | student_handbook_rag | - | 10565.78 | pass |
| web_013 | keyword | general_ictu_rag | - | 11552.24 | pass |
| web_014 | keyword | general_ictu_rag | - | 5894.84 | pass |
| web_015 | keyword | general_ictu_rag | - | 9685.8 | pass |

## Wrong Cases And Reasons

- `local_005`: selected_tool_mismatch, expected_source_not_in_retrieved_ranking; selected_tool=`general_ictu_rag`; source_rank=None.
