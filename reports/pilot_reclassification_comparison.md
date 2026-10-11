# Pilot Reclassification Comparison

Based on the corrected taxonomy for Class 9 Mathematics and Class 9 Social Science, we can re-evaluate the classifications for the previously flagged pilot questions.

## 1. Class 9 Mathematics

**Question ID:** CQ_0389
**Question Text:** "What is the solution set of the equation 3x + 1 = 0?"

- **Old Classification:**
  - Chapter: `CBSE9_MATH_02` (Incorrectly extracted as "ALGEBRA")
  - Topic: `None`
  - Status: `review_required` (Confidence 0.8)
  - Issue: The parser missed the actual chapters under Algebra.

- **New Available Classification:**
  - Unit: `ALGEBRA`
  - Chapter: `Linear Equations in Two Variables`
  - Topic: `None` (Legitimately remains chapter-level)
  - **Resolution:** The question now has a valid chapter-level node ("Linear Equations in Two Variables"). It legitimately lacks a topic-level node because "equations in one variable" is officially considered a prerequisite/Class 8 concept, not explicitly listed as a topic in the Class 9 2026-27 syllabus.

## 2. Class 9 Social Science

**Question ID:** CQ_1316
**Question Text:** "Assertion (A): The rise of Hitler was facilitated by the Treaty of Versailles..."

- **Old Classification:**
  - Chapter: `CBSE9_SST_04` (Incorrectly extracted fallback generic chapter)
  - Topic: `None`
  - Status: `review_required`

- **New Available Classification:**
  - Unit/Chapter: `UNCLASSIFIABLE`
  - Topic: `None`
  - **Resolution:** After parsing the authentic 2026-27 CBSE Course Outline, it is confirmed that modern European history (French Revolution, Nazism, Hitler, etc.) has been completely removed from the Class 9 curriculum under the NCF-SE 2023 update. This question belongs to an older syllabus and is now legitimately unclassifiable in the 2026-27 taxonomy.

**Question ID:** CQ_1314
**Question Text:** "Which of the following best describes the Estates System in pre-revolutionary France?"

- **Old Classification:**
  - Chapter: `CBSE9_SST_03`
  - Topic: `CBSE9_SST_03_TOP67` (Incorrectly extracted bullet point)
  - Status: `review_required`

- **New Available Classification:**
  - Unit/Chapter: `UNCLASSIFIABLE`
  - Topic: `None`
  - **Resolution:** Like CQ_1316, the French Revolution is no longer present in the official 2026-27 syllabus. The question becomes legitimately unclassifiable.

---

### Conclusion on Reclassification
- **Questions that now have a valid lower-level node:** Questions in Class 9 Maths regarding Linear Equations (e.g., CQ_0389) now correctly map to the "Linear Equations in Two Variables" chapter instead of the broad "Algebra" unit.
- **Questions that legitimately remain chapter-level:** CQ_0389 legitimately remains chapter-level since the topic is a prerequisite.
- **Questions that remain unclassifiable / require human review:** Questions about the French Revolution and Nazism (CQ_1314, CQ_1316) are now completely unclassifiable because the official 2026-27 syllabus removed these topics.

No question-driven nodes were manually invented. The taxonomy strictly represents the official CBSE PDFs.
