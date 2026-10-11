# Syllabus Taxonomy Coverage Audit

## Class 9 Mathematics
- **Official PDF:** `cbse_class9_maths_2026_27.pdf`
- **Pages Inspected:** 4, 5, 6
- **Extracted Units:** 0 (Parsed as Chapters)
- **Extracted Chapters/Themes:** 7
- **Extracted Topics:** 34
- **Extracted Learning Outcomes:** 0
- **Suspected Missing Nodes:**
  - `Linear Equations in Two Variables` (Chapter)
  - `Introduction to Polynomials` (Chapter)
  - `Exploring Algebraic Identities` (Chapter)
  - `Sequences and Progressions` (Chapter)
  - Various other chapters under Geometry, Mensuration, Statistics.
- **Suspected Incorrect Nodes:** 
  - `ALGEBRA`, `GEOMETRY`, etc. were extracted as Chapters, but they are Units.
  - The text in the "Competencies" column of the PDF table was incorrectly parsed as bullet-point topics under the Units.
- **Parser Limitations:** The `generic_parser` relies on regexes matching "UNIT X" or "ALL CAPS" for chapters, which completely failed to interpret the 4-column table layout of the syllabus (Unit Name, Chapter Name, Key Concepts, Competencies).
- **Status:** **FAIL**

**Specific Investigation (Case 1):** The official CBSE 2026-27 Mathematics PDF does NOT contain a chapter or topic explicitly for "linear equations in one variable". The topic is "Linear Equations in Two Variables" (Chapter 4 under Unit II Algebra). The LLM was correct that the *Class 9 Algebra* taxonomy lacked this specific node (because it is generally considered a Class 8 prerequisite), but the parser ALSO failed to extract the "Linear Equations in Two Variables" chapter.

---

## Class 9 Social Science
- **Official PDF:** `cbse_class9_social_science_2026_27.pdf`
- **Pages Inspected:** 8, 9, 10, 11, 12, 13, 14
- **Extracted Units:** 0
- **Extracted Chapters/Themes:** 5
- **Extracted Topics:** 83
- **Extracted Learning Outcomes:** 0
- **Suspected Missing Nodes:** 
  - `Shaping of the Earth's Surface` (Chapter)
  - `Atmosphere and Climate` (Chapter)
  - `Early Humans and Beginning of Civilisation` (Chapter)
  - `Democracy` (Chapter)
  - All 16 actual themes/chapters in the Course Outline were missed.
- **Suspected Incorrect Nodes:** 
  - Extracted "RATIONALE", "COMPETENCIES", "COURSE OUTLINE" as Chapters.
  - Mapped all tabular learning outcomes and concepts as random topics under "COURSE OUTLINE".
- **Parser Limitations:** Like Maths, the `generic_parser` failed to parse the 4-column tables ("Theme", "Outline/Concepts", "Learning Outcomes") on pages 8-14.
- **Status:** **FAIL**

**Specific Investigation (Case 2):** The official CBSE 2026-27 Social Science PDF does **NOT** contain the concepts "French Revolution", "Treaty of Versailles", "Nazism", or "Hitler". The NCF-SE 2023 curriculum for Class 9 History focuses instead on "Early Humans", "State and Society (upto 1000 CE)", "Resistance and Resilience", and "India and the World-I". Therefore, the JSON taxonomy was correct to omit them, and the LLM correctly identified that the 2026-27 taxonomy was too abstract/broad to fit these older syllabus questions. The LLM's fallback to a broad chapter node was the appropriate behavior.

---

## Class 10 Mathematics
- **Status:** **PASS** (Using pre-verified `CLASS10_MATHS_FALLBACK`)

## Class 10 Social Science
- **Status:** **PASS** (Using pre-verified `CLASS10_SST_FALLBACK`)

## Class 9 Science
- **Status:** **WARN** 
- **Notes:** Uses `custom_parser_class9_science`. Successfully extracts chapters like "Matter in Our Surroundings", but topic parsing from bullets is slightly messy (mixes concepts and outcomes). However, it represents the PDF adequately.

## Class 10 Home Science
- **Status:** **WARN**
- **Notes:** The generic parser captured the Unit/Chapter structure decently because it uses a more standard heading format, but missed some nested granularity in tables.

## Class 10 Computer Applications
- **Status:** **WARN**
- **Notes:** Similar to Home Science, basic chapters were captured via the generic parser, but tabular content was partially flattened.

---

## Conclusion
The `generic_parser` is incompatible with the tabular layouts of the Class 9 Maths and Class 9 Social Science syllabuses. The JSONs currently contain malformed hierarchies. 
**Action Required:** Fix the parser (by implementing specific tabular parsers or fallback structures for Class 9 Maths/SST) and rebuild the JSONs. Do not modify the pilot classifications manually.
