# Class 9 CBSE 2026-27 Taxonomy Coverage Audit

## 1. Executive Summary

This audit evaluated the exact taxonomy structure for Class 9 Mathematics and Social Science against the official CBSE 2026-27 PDF curriculum. 
Two major, distinct issues were identified regarding the pilot questions:
1. **Mathematical Terminology & Parser Failure**: The mathematics question regarding "equations in one variable" corresponds to "linear polynomials" in the official syllabus. However, the current JSON taxonomy is severely malformed due to a parser failure that nested the entire textbook under Unit 1.
2. **Social Science Curriculum Overhaul**: The question regarding Hitler and the Treaty of Versailles is obsolete. The CBSE 2026-27 curriculum has completely removed modern European history, replacing it with ancient and medieval Indian history. This was not a classifier or parser error; the concept genuinely no longer exists in the taxonomy.

## 2. Class 9 Mathematics

### 2.1 Official PDF
File: `cbse_class9_maths_2026_27.pdf`
Pages: 4-12

### 2.2 Official Hierarchy
The official syllabus contains a summary table on Page 4 and a detailed table from Page 4 to 12. 
The true top-level hierarchy consists of Units (I. Number System, II. Algebra, III. Coordinate Geometry, IV. Geometry, V. Mensuration, VI. Statistics and Probability). Each Unit contains Chapters, and each Chapter contains Key Concepts (Topics).

### 2.3 Current JSON Hierarchy
The current taxonomy (`cbse_class9_maths_2026_27.json`) extracted the Roman Numerals (I, II, III...) from the summary table as empty standalone chapters. It then extracted "Unit 1: Number System" (`CBSE9_MATH_07`) but completely failed to recognize the boundary for Unit II. The text "UNIT II: ALGEBRA" was extracted as a leaf-level topic (`CBSE9_MATH_07_CHA01_TOP18`) under Chapter 1. As a result, Chapters 2 through 6 of the book are incorrectly nested inside Unit 1.

### 2.4 Missing Nodes
Top-level structural nodes for Units II through VI are missing as top-level bounds because they were miscategorized as topics. 

### 2.5 Incorrectly Extracted Nodes
- `CBSE9_MATH_01` to `06`: Hallucinated empty chapters created from the Roman Numerals in the summary table.
- `CBSE9_MATH_07_CHA01_TOP18`: Contains the text "UNIT II: ALGEBRA No. of periods : 66" instead of starting a new Unit array.

### 2.6 Pilot Question Investigation
Question: "What is the solution set of the equation 3x + 1 = 0?"
Investigation: The explicit phrase "algebraic equations in one variable" is not used in the 2026-27 syllabus. However, solving a linear equation maps to the official concept "Introduction to linear polynomials and applications" (Page 5) and "Linear Equations in Two Variables" (Page 6). The classifier failed to find it easily because the taxonomy's tree structure was destroyed by the parser.

### 2.7 Page-Level Evidence
- PDF File: `cbse_class9_maths_2026_27.pdf`
- Page Number: 5
- Exact Official Wording: "Introduction to linear polynomials and applications"
- Current JSON Representation: `CBSE9_MATH_07_CHA02_TOP05` (Incorrectly nested under Unit 1 -> Introduction to Polynomials)
- Discrepancy Type: Category C (OFFICIAL NODE PRESENT BUT EXTRACTED INCORRECTLY)
- Recommended Parser Correction: Improve table tracking so that "UNIT [X]: [NAME]" text spanning columns triggers a new top-level node rather than being appended as a Topic.

## 3. Class 9 Social Science

### 3.1 Official PDF
File: `cbse_class9_social_science_2026_27.pdf`
Pages: 8-14

### 3.2 Official Hierarchy
The official syllabus is divided into Part 1 and Part 2. Chapters include: Understanding Social Science, Shaping of the Earth’s Surface, Atmosphere and Climate, Early Humans, State and Society (upto 1000 CE), Democracy, Elections, Building Blocks in Economics, The Price Puzzle, Oceans and Life, Life on Earth, Resistance and Resilience, India and the World-I, Authority, From Ideas to Startups, Smart Ways to Manage Your Finances.

### 3.3 Current JSON Hierarchy
The parser failed to cleanly skip table headers on Page 8. The column header "Theme (time allocation in instructional hours)" was word-wrapped and incorrectly extracted as three dummy chapters:
- `CBSE9_SST_01`: "allocation in"
- `CBSE9_SST_02`: "instructional"
- `CBSE9_SST_03`: "hours)"

### 3.4 Missing Nodes
Concepts like the French Revolution, Treaty of Versailles, and Nazism/Hitler do not exist in the PDF. 

### 3.5 Incorrectly Extracted Nodes
The header fragments (`allocation in`, `instructional`, `hours)`) were extracted as top-level Syllabus Chapters.

### 3.6 Pilot Question Investigation
Question: "Assertion (A): The rise of Hitler was facilitated by the Treaty of Versailles..."
Investigation: An exhaustive search of the 2026-27 CBSE Class 9 Social Science syllabus confirms that modern world history has been entirely omitted from the curriculum. The syllabus now extensively covers deep ancient history, medieval history, and civilisations up to 1700 CE. 
This was not a classifier error. The classifier correctly identified that the taxonomy was "too broad" or inappropriate because the question simply does not belong to the 2026-27 academic framework.

### 3.7 Page-Level Evidence
- PDF File: `cbse_class9_social_science_2026_27.pdf`
- Page Number: 8-14
- Exact Official Wording: N/A (Does not exist)
- Current JSON Representation: N/A
- Discrepancy Type: Category D (NOT AN OFFICIAL SYLLABUS NODE)
- Recommended Parser Correction: Remove dummy header nodes (`allocation in`, etc.) by ignoring rows containing header keywords. Create an application-level rule for obsolete legacy questions.

## 4. Cross-Subject Findings
The primary point of failure is `build_syllabus.py`'s ability to maintain structural integrity across multi-page, complex PDF tables.
1. It frequently conflates index tables with detailed content tables.
2. It turns table header wrap-around text into hallucinated taxonomy nodes.
3. It fails to identify row-spanning section breaks (e.g., "UNIT II: ALGEBRA") and instead appends them as child nodes of the previous section.

## 5. Parser Corrections Required
- **Ignore summary tables**: Skip processing the preliminary index table mapping Roman Numerals to chapters if a detailed table follows.
- **Ignore table headers**: Detect and discard rows containing repetitive headers like "S. No.", "Theme", "allocation in", "Learning Outcomes".
- **Detect structural breaks properly**: Hardcode regex rules to recognize "UNIT [I-X]:" or "Part [1-2]" as explicit boundaries that close the current parent node and open a new one.

## 6. Items Requiring Manual Verification
The presence of the "Hitler/Treaty of Versailles" question in the `clean_question_bank.csv` requires a policy decision. Since the 2026-27 syllabus does not cover this era of history, should the system introduce an `obsolete` or `legacy_curriculum` tag, or drop these questions entirely from the active mock-generation bank?

## 7. Recommendation
1. Do NOT proceed with the 1,726-question classification yet.
2. Refactor `build_syllabus.py` focusing strictly on robust table-structure parsing.
3. Rerun the extraction for all 7 class-subject combinations and validate the generated JSONs.
4. Finalize the handling instruction for dataset questions that no longer map to the 2026-27 CBSE taxonomy.
