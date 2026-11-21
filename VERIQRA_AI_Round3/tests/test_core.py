import unittest
from compliance import analyze_content, calculate_score

class ComplianceTests(unittest.TestCase):
    def setUp(self):
        self.profile={"prohibited_words":["guaranteed"],"preferred_terms":{"cheap":"affordable"},
          "required_disclaimer":"Terms apply.","approved_facts":["Founded in 2024"]}
    def test_prohibited(self):
        r=analyze_content("We have guaranteed success.",self.profile)
        self.assertTrue(any(x["db_category"]=="Prohibited Terminology" for x in r["findings"]))
    def test_preferred(self):
        r=analyze_content("This is cheap.",self.profile)
        self.assertIn("affordable",r["corrected_content"])
    def test_disclaimer(self):
        r=analyze_content("Our product is here.",self.profile)
        self.assertEqual(r["disclaimer_status"],"missing")
    def test_negated_phrase_not_high_confidence_live_claim(self):
        r=analyze_content("Do not say guaranteed results.",self.profile)
        self.assertTrue(any("negated" in x["reason"].lower() for x in r["findings"]))
    def test_score(self):
        self.assertEqual(calculate_score([{"severity":"High"},{"severity":"Medium"}]),77)

if __name__=="__main__": unittest.main()
