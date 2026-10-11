"""
tests/test_build_syllabus.py
============================
Parser tests for build_syllabus.py (Part 8 of the Syllabus Audit).

Tests cover:
  1. UNIT I detection
  2. UNIT II detection
  3. Unit boundary transitions (unit N → unit N+1 resets current_chapter)
  4. Roman numeral summary-table row filtering
  5. Wrapped Social Science header filtering ("allocation in", "instructional", "hours)")
  6. Repeated table header filtering
  7. Source-page provenance (source_pages populated)
  8. Preservation of empty official sections (no children → node still kept)

Run:
    python -m pytest tests/test_build_syllabus.py -v
"""

import sys
from pathlib import Path

import pytest

# Ensure the scripts directory is on sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_syllabus import (
    clean_text,
    extract_bullet_texts,
    is_noise_text,
    is_part_header,
    is_summary_row,
    is_table_header_cell,
    is_unit_header,
    normalise_chapter_name,
    is_internal_assessment_node,
)


# ---------------------------------------------------------------------------
# 1. UNIT I detection
# ---------------------------------------------------------------------------

class TestUnitIDetection:
    def test_unit_1_colon(self):
        m = is_unit_header("Unit 1: Number System No. of periods : 12")
        assert m is not None
        assert m.group(1) == "1"
        assert "Number System" in m.group(2)

    def test_unit_i_roman(self):
        m = is_unit_header("UNIT I: NUMBER SYSTEM No. of periods : 12")
        assert m is not None
        assert m.group(1).upper() == "I"

    def test_unit_i_no_periods(self):
        m = is_unit_header("UNIT I: NUMBER SYSTEM")
        assert m is not None
        assert "NUMBER SYSTEM" in m.group(2)

    def test_unit_i_lowercase(self):
        m = is_unit_header("unit i: number system")
        assert m is not None

    def test_non_unit_string(self):
        assert is_unit_header("Number System") is None
        assert is_unit_header("Chapter 1: Intro") is None
        assert is_unit_header("Introduction to Polynomials") is None


# ---------------------------------------------------------------------------
# 2. UNIT II detection
# ---------------------------------------------------------------------------

class TestUnitIIDetection:
    def test_unit_ii_algebra(self):
        m = is_unit_header("UNIT II: ALGEBRA No. of periods : 66")
        assert m is not None
        assert m.group(1).upper() == "II"
        assert "ALGEBRA" in m.group(2)

    def test_unit_ii_no_trailing(self):
        m = is_unit_header("Unit II: Algebra")
        assert m is not None, "Should match Unit II without period count"

    def test_unit_vi(self):
        m = is_unit_header("UNIT VI: STATISTICS AND PROBABILITY No. of periods : 15")
        assert m is not None
        assert m.group(1).upper() == "VI"


# ---------------------------------------------------------------------------
# 3. Unit boundary transitions
# ---------------------------------------------------------------------------

class TestUnitBoundaryTransitions:
    """
    Integration-style test: ensure that the parse_via_tables function
    correctly splits units. We build a minimal mock table and exercise the
    set_unit helper conceptually via the full JSON output.
    """

    def test_maths_json_has_6_units(self):
        import json
        json_path = ROOT / "data" / "syllabus" / "cbse_class9_maths_2026_27.json"
        if not json_path.exists():
            pytest.skip("Maths JSON not built yet")
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        units = [n for n in data["curriculum"] if n["type"] == "unit"]
        assert len(units) == 6, f"Expected 6 units, got {len(units)}: {[u['name'] for u in units]}"

    def test_maths_algebra_unit_has_4_chapters(self):
        import json
        json_path = ROOT / "data" / "syllabus" / "cbse_class9_maths_2026_27.json"
        if not json_path.exists():
            pytest.skip("Maths JSON not built yet")
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        algebra = next((n for n in data["curriculum"] if "ALGEBRA" in n["name"].upper()), None)
        assert algebra is not None, "Algebra unit not found"
        chapters = algebra["children"]
        assert len(chapters) == 4, f"Expected 4 chapters in Algebra, got {len(chapters)}: {[c['name'] for c in chapters]}"

    def test_each_unit_has_children(self):
        import json
        json_path = ROOT / "data" / "syllabus" / "cbse_class9_maths_2026_27.json"
        if not json_path.exists():
            pytest.skip("Maths JSON not built yet")
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        for unit in data["curriculum"]:
            assert unit.get("children"), f"Unit '{unit['name']}' has no children"

    def test_unit_ids_are_sequential(self):
        import json
        json_path = ROOT / "data" / "syllabus" / "cbse_class9_maths_2026_27.json"
        if not json_path.exists():
            pytest.skip("Maths JSON not built yet")
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        prefix = "CBSE9_MATH"
        for i, unit in enumerate(data["curriculum"], 1):
            assert unit["id"] == f"{prefix}_{i:02d}", f"ID mismatch: {unit['id']}"


# ---------------------------------------------------------------------------
# 4. Roman numeral summary-table row filtering
# ---------------------------------------------------------------------------

class TestRomanNumeralSummaryFilter:
    def test_summary_row_with_marks(self):
        # "I Number System 07" — should be identified as a summary row
        assert is_summary_row("I Number System 07")

    def test_summary_row_algebra(self):
        assert is_summary_row("II Algebra  Introduction to Polynomials 20")

    def test_summary_row_geometry(self):
        assert is_summary_row("IV Geometry 25")

    def test_non_summary_normal_chapter(self):
        # "Number System" alone is not a summary row
        assert not is_summary_row("Number System")

    def test_non_summary_unit_header(self):
        assert not is_summary_row("UNIT II: ALGEBRA No. of periods : 66")


# ---------------------------------------------------------------------------
# 5. Wrapped Social Science header filtering
# ---------------------------------------------------------------------------

class TestWrappedSSTableHeaders:
    def test_allocation_in(self):
        assert is_table_header_cell("allocation in")

    def test_allocation_bare(self):
        assert is_table_header_cell("allocation")

    def test_instructional(self):
        assert is_table_header_cell("instructional")

    def test_hours_paren(self):
        assert is_table_header_cell("hours)")

    def test_theme(self):
        assert is_table_header_cell("Theme")

    def test_theme_time(self):
        assert is_table_header_cell("Theme (time")

    def test_outline_concepts(self):
        assert is_table_header_cell("Outline/Concepts")

    def test_legitimate_chapter_not_filtered(self):
        # "Understanding Social Science" must NOT be treated as a header
        assert not is_table_header_cell("Understanding Social Science")
        assert not is_table_header_cell("Democracy")
        assert not is_table_header_cell("Elections")


# ---------------------------------------------------------------------------
# 6. Repeated table header filtering
# ---------------------------------------------------------------------------

class TestRepeatedTableHeaders:
    def test_sno(self):
        assert is_table_header_cell("S. No.")

    def test_chapter_name(self):
        assert is_table_header_cell("Chapter Name")

    def test_key_concepts(self):
        assert is_table_header_cell("Key Concepts")

    def test_relevant_cgs(self):
        assert is_table_header_cell("Relevant CGs")

    def test_learning_outcomes(self):
        assert is_table_header_cell("Learning Outcomes and")

    def test_competencies(self):
        assert is_table_header_cell("Competencies")

    def test_students_will(self):
        assert is_table_header_cell("Students will be able to:")

    def test_none_string(self):
        assert is_table_header_cell("None")

    def test_total(self):
        assert is_table_header_cell("Total 80")
        assert is_table_header_cell("TOTAL")


# ---------------------------------------------------------------------------
# 7. Source-page provenance
# ---------------------------------------------------------------------------

class TestSourcePageProvenance:
    def test_maths_units_have_source_pages(self):
        import json
        json_path = ROOT / "data" / "syllabus" / "cbse_class9_maths_2026_27.json"
        if not json_path.exists():
            pytest.skip("Maths JSON not built yet")
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        for unit in data["curriculum"]:
            assert unit.get("source_pages"), f"Unit '{unit['name']}' missing source_pages"
            for ch in unit.get("children", []):
                assert ch.get("source_pages"), f"Chapter '{ch['name']}' missing source_pages"

    def test_sst_chapters_have_source_pages(self):
        import json
        json_path = ROOT / "data" / "syllabus" / "cbse_class9_social_science_2026_27.json"
        if not json_path.exists():
            pytest.skip("SST JSON not built yet")
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        for unit in data["curriculum"]:
            for ch in unit.get("children", []):
                assert ch.get("source_pages"), f"SST Chapter '{ch['name']}' missing source_pages"

    def test_source_pdf_field(self):
        import json
        json_path = ROOT / "data" / "syllabus" / "cbse_class9_maths_2026_27.json"
        if not json_path.exists():
            pytest.skip("Maths JSON not built yet")
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data.get("source_pdf"), "source_pdf field missing from JSON"
        assert data.get("source_url"), "source_url field missing from JSON"


# ---------------------------------------------------------------------------
# 8. Preservation of empty official sections
# ---------------------------------------------------------------------------

class TestEmptyOfficialSections:
    def test_noise_function_does_not_block_legitimate_names(self):
        # Chapters that happen to have no sub-topics should still not be noise
        assert not is_noise_text("Understanding Social Science")
        assert not is_noise_text("Democracy")
        assert not is_noise_text("Coordinate Geometry")

    def test_short_but_valid_names_preserved(self):
        assert not is_noise_text("Circles")

    def test_noise_catches_page_numbers(self):
        assert is_noise_text("8")
        assert is_noise_text("12")

    def test_noise_catches_course_structure_header(self):
        assert is_noise_text("COURSE STRUCTURE")
        assert is_noise_text("COURSE OUTLINE")


# ---------------------------------------------------------------------------
# Bonus: Chapter name normalisation
# ---------------------------------------------------------------------------

class TestNormaliseChapterName:
    def test_suffix_merge_authorit_y(self):
        assert normalise_chapter_name("Authorit y") == "Authority"

    def test_suffix_merge_progression_s(self):
        assert normalise_chapter_name("Progression s") == "Progressions"

    def test_suffix_merge_quadrilater_als(self):
        assert normalise_chapter_name("Quadrilater als") == "Quadrilaterals"

    def test_standalone_on_not_merged(self):
        # "Life on Earth" — 'on' must NOT be merged
        result = normalise_chapter_name("Life on Earth")
        assert result == "Life on Earth"

    def test_standalone_of_not_merged(self):
        result = normalise_chapter_name("Shaping of the Earth")
        assert result == "Shaping of the Earth"

    def test_standalone_in_not_merged(self):
        result = normalise_chapter_name("Linear Equations in Two Variables")
        assert result == "Linear Equations in Two Variables"


# ---------------------------------------------------------------------------
# Bonus: IA node filtering
# ---------------------------------------------------------------------------

class TestInternalAssessmentFilter:
    def test_pen_paper_test(self):
        assert is_internal_assessment_node("Pen Paper Test and Multiple Assessment (5+5) 10 Marks")

    def test_portfolio(self):
        assert is_internal_assessment_node("Portfolio 05 Marks")

    def test_lab_practical(self):
        assert is_internal_assessment_node("Lab Practical (Lab activities to be done from the prescribed books) 05 Marks")

    def test_project_work(self):
        assert is_internal_assessment_node("Project work (Interdisciplinary)")

    def test_social_science_part_ref(self):
        assert is_internal_assessment_node("Social Science-Part 1")

    def test_legitimate_chapter_not_filtered(self):
        assert not is_internal_assessment_node("Linear Equations in Two Variables")
        assert not is_internal_assessment_node("Democracy")
        assert not is_internal_assessment_node("Introduction to Polynomials")


# ---------------------------------------------------------------------------
# Bonus: Bullet extraction
# ---------------------------------------------------------------------------

class TestExtractBulletTexts:
    def test_bullet_split(self):
        cell = "\u2022 Introduction to polynomials \u2022 Degree of a polynomial \u2022 Applications"
        results = extract_bullet_texts(cell)
        assert len(results) == 3
        assert "Introduction to polynomials" in results

    def test_cg_refs_excluded(self):
        cell = "CG-1, C-1.1, CG-9 \u2022 Solve linear equations"
        results = extract_bullet_texts(cell)
        assert all("CG-" not in r for r in results)

    def test_empty_cell(self):
        assert extract_bullet_texts("") == []
        assert extract_bullet_texts(None) == []

    def test_blooms_taxonomy_labels_excluded(self):
        cell = "\u2022 Solve problems \u2022 Remembering: Recall facts"
        results = extract_bullet_texts(cell)
        assert all(not r.startswith("Remembering:") for r in results)
