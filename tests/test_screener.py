"""Scoring engine and CV-reading tests. Run:  python -m unittest discover -s tests -v"""
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import parsers  # noqa: E402
from screener import detect_education, detect_years, keyword_found, parse_keywords, screen_cv  # noqa: E402

POS = {p["name"]: p for p in config.DEFAULT_POSITIONS}


def flat(required=(), preferred=(), min_years=0, min_edu="Diploma", w=(0, 0, 1, 0)):
    """A tiny position whose score depends only on the weights given (default: required keywords only)."""
    return {"name": "T", "min_years": min_years, "min_education": min_edu,
            "required_keywords": ",".join(required), "preferred_keywords": ",".join(preferred),
            "w_exp": w[0], "w_edu": w[1], "w_req": w[2], "w_pref": w[3]}


TEN = [f"kw{i}" for i in range(10)]


class RubricTests(unittest.TestCase):
    def test_seven_original_positions_plus_intern_are_configured(self):
        self.assertEqual(set(POS), {"Research Fellow", "Policy Analyst", "Research Assistant", "Data Analyst",
                                    "Communications Officer", "Program Manager", "Administrative Assistant", "Intern"})
        rf = POS["Research Fellow"]
        self.assertEqual((rf["min_years"], rf["min_education"]), (5, "PhD"))
        self.assertEqual((rf["w_exp"], rf["w_edu"], rf["w_req"], rf["w_pref"]), (0.30, 0.25, 0.30, 0.15))

    def test_weights_in_the_brief_ranges(self):
        for name, p in POS.items():
            if name == "Intern":
                continue
            self.assertTrue(0.15 <= p["w_exp"] <= 0.35, name)
            self.assertTrue(0.15 <= p["w_edu"] <= 0.30, name)
            self.assertTrue(0.30 <= p["w_req"] <= 0.40, name)
            self.assertTrue(0.15 <= p["w_pref"] <= 0.20, name)

    def test_score_formula_hand_calculated(self):
        # Data Analyst: 1 of 2 yrs (0.5), Bachelor ok (1.0), 3/3 required (1.0), 2/8 preferred (0.25)
        cv = "Bachelor of Science. 1 year of experience. data, analysis, statistics. python, sql."
        r = screen_cv(cv, POS["Data Analyst"])
        expected = 100 * (0.25 * 0.5 + 0.20 * 1.0 + 0.35 * 1.0 + 0.20 * 0.25) / 1.0
        self.assertAlmostEqual(r["score"], round(expected, 1), places=1)
        self.assertEqual(r["sub_scores"]["experience"], 0.5)

    def test_decision_boundaries_70_and_60(self):
        pos = flat(required=TEN)
        for hits, want in ((7, "Pass"), (6, "Needs Review"), (5, "Reject")):
            cv = "Diploma. " + " ".join(TEN[:hits])
            r = screen_cv(cv, pos)
            self.assertEqual(r["score"], hits * 10.0)
            self.assertEqual(r["status"], want, f"{hits} of 10 keywords")
        twenty = [f"term{chr(97 + i)}x" for i in range(20)]       # 13 of 20 = 65: still inside 60 <= score < 70
        r = screen_cv("Diploma. " + " ".join(twenty[:13]), flat(required=twenty))
        self.assertEqual((r["score"], r["status"]), (65.0, "Needs Review"))

    def test_thresholds_are_editable(self):
        pos = flat(required=TEN)
        cv = "Diploma. " + " ".join(TEN[:5])
        self.assertEqual(screen_cv(cv, pos)["status"], "Reject")
        self.assertEqual(screen_cv(cv, pos, {"pass_threshold": "50", "review_threshold": "40"})["status"], "Pass")

    def test_hard_requirement_min_years_rejects_even_with_a_perfect_score(self):
        pos = flat(required=["alpha"], min_years=5, w=(0, 0, 1, 0))
        r = screen_cv("Diploma. alpha. 2 years of experience.", pos)
        self.assertEqual(r["score"], 100.0)
        self.assertEqual(r["status"], "Reject")
        self.assertFalse(r["hard_requirements_met"])
        self.assertTrue(any("experience" in f for f in r["hard_failures"]))

    def test_hard_requirement_min_education_rejects_even_with_a_perfect_score(self):
        pos = flat(required=["alpha"], min_edu="Master")
        r = screen_cv("Diploma. alpha.", pos)
        self.assertEqual((r["score"], r["status"]), (100.0, "Reject"))
        self.assertTrue(any("education" in f for f in r["hard_failures"]))

    def test_require_all_keywords_setting(self):
        pos = flat(required=["alpha", "beta"])
        cv = "Diploma. alpha."
        self.assertEqual(screen_cv(cv, pos, {"pass_threshold": "40"})["status"], "Pass")
        self.assertEqual(screen_cv(cv, pos, {"pass_threshold": "40", "require_all_required_keywords": "1"})["status"], "Reject")

    def test_empty_cv_is_rejected_not_an_error(self):
        r = screen_cv("", POS["Data Analyst"])
        self.assertEqual(r["status"], "Reject")


class ExtractionTests(unittest.TestCase):
    def test_education_takes_the_highest_level(self):
        self.assertEqual(detect_education("BSc then MSc then PhD"), 4)
        self.assertEqual(detect_education("Master of Arts, bachelor of arts"), 3)
        self.assertEqual(detect_education("B.Eng degree"), 2)
        self.assertEqual(detect_education("National diploma"), 1)
        self.assertEqual(detect_education("matric only"), 0)

    def test_education_does_not_match_inside_other_words(self):
        self.assertEqual(detect_education("database administration and a barista job"), 0)

    def test_years_takes_the_maximum(self):
        self.assertEqual(detect_years("3 years at A, 7+ yrs overall, 2.5 years at B"), 7.0)
        self.assertEqual(detect_years("no numbers here"), 0.0)

    def test_short_keywords_need_a_whole_token(self):
        self.assertFalse(keyword_found("r", "researcher with strong analysis"))
        self.assertTrue(keyword_found("r", "python, r and sql"))
        self.assertTrue(keyword_found("power bi", "uses power bi daily"))

    def test_keyword_parsing(self):
        self.assertEqual(parse_keywords(" Python, SQL ,python\n R "), ["python", "sql", "r"])


class CvFileTests(unittest.TestCase):
    TEXT = "Jane Doe. Data analyst with 6 years of experience. Bachelor of Science in Statistics."

    def test_txt_utf8_and_latin1(self):
        self.assertIn("Data analyst", parsers.extract_text("cv.txt", self.TEXT.encode()))
        self.assertIn("Caf", parsers.extract_text("cv.txt", "Café manager 5 years".encode("latin-1")))

    def test_docx(self):
        import docx
        d = docx.Document()
        d.add_paragraph(self.TEXT)
        buf = io.BytesIO()
        d.save(buf)
        self.assertIn("6 years", parsers.extract_text("cv.docx", buf.getvalue()))

    def test_pdf(self):
        from reportlab.pdfgen import canvas
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        c.drawString(72, 750, self.TEXT)
        c.save()
        text = parsers.extract_text("cv.pdf", buf.getvalue())
        self.assertIn("Bachelor of Science", text)
        r = screen_cv(text, POS["Data Analyst"])
        self.assertEqual(r["years_found"], 6.0)

    def test_bad_files_give_friendly_errors(self):
        for name, data, fragment in (("cv.exe", b"x", "Unsupported file type"), ("cv.pdf", b"", "empty"),
                                     ("cv.pdf", b"not a pdf", "Could not read"), ("cv.txt", b"   \n ", "No text")):
            with self.assertRaises(ValueError) as cm:
                parsers.extract_text(name, data)
            self.assertIn(fragment, str(cm.exception), name)


class BatchOfTwentyCvs(unittest.TestCase):
    """The 20 fictional CVs (PDFs) with a known expected decision each. Skipped if the folder is not present."""
    ROOT = os.environ.get("TEST_CV_DIR", "/home/claude/test_cvs")

    def test_all_twenty(self):
        import json
        idx = os.path.join(self.ROOT, "cv_index.json")
        if not os.path.exists(idx):
            self.skipTest("test CV folder not found")
        bad = []
        for c in json.load(open(idx)):
            with open(os.path.join(self.ROOT, "CVs", c["file"]), "rb") as fh:
                text = parsers.extract_text(c["file"], fh.read())
            got = screen_cv(text, POS[c["position"]])["status"]
            if got != c["expected"]:
                bad.append((c["name"], c["expected"], got))
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
