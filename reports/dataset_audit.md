# Dataset Audit Report

**Generated at:** 2026-09-28T18:55:57.347918
**Source file:** `D:\CBSE910\clean_question_bank.csv`

---
## Summary
| Metric | Value |
|--------|-------|
| Total records | 1795 |
| Columns | 18 |
| Duplicate questions | 150 |
| Empty question text | 0 |
| Questions missing metadata | 0 |

## Column Names & Inferred Types
| # | Column | Inferred Type | Missing Count |
|---|--------|---------------|---------------|
| 1 | `﻿question_id` | integer | 0 |
| 2 | `class` | string | 0 |
| 3 | `subject` | string | 0 |
| 4 | `session` | string | 0 |
| 5 | `source_file` | string | 0 |
| 6 | `question_number` | integer | 0 |
| 7 | `question_text` | string | 0 |
| 8 | `answer` | empty | 1795 |
| 9 | `section` | empty | 1795 |
| 10 | `question_type` | string | 0 |
| 11 | `options` | string | 874 |
| 12 | `marks` | empty | 1795 |
| 13 | `topic` | empty | 1795 |
| 14 | `difficulty` | empty | 1795 |
| 15 | `has_diagram` | string | 0 |
| 16 | `correct_answer` | empty | 1795 |
| 17 | `answer_explanation` | empty | 1795 |
| 18 | `question_text_clean` | string | 0 |

## Unique Classes
`class10`, `class9`

## Unique Subjects
`computer_application`, `home_science`, `maths`, `science`, `social_science`

## Unique Sessions
`2023-24`, `2024-25`, `2025-26`, `2026-27`

## Unique Question Types
`Assertion-Reason`, `Case-Based`, `MCQ`, `Short/Long Answer`

## Marks Distribution
| Marks | Count |
|-------|-------|
| missing | 1795 |

## Class x Subject Breakdown
| Class | Subject | Count |
|-------|---------|-------|
| class10 | computer_application | 53 |
| class10 | home_science | 90 |
| class10 | maths | 126 |
| class10 | social_science | 116 |
| class9 | maths | 466 |
| class9 | science | 463 |
| class9 | social_science | 481 |

## Sample Duplicate Groups (first 10 groups)
- IDs ['row_39', 'row_40']: "assertion..."
- IDs ['row_66', 'row_67', 'row_132', 'row_133']: "given below are two statements labeled as assertion..."
- IDs ['row_279', 'row_292', 'row_1530']: "there are two statements marked as assertion..."
- IDs ['row_966', 'row_1046']: "the pictures show the arrangement of electrons in the shells of different atoms...."
- IDs ['row_967', 'row_1047']: "which of these is common for all chemical changes?..."