"""Regression tests for negation-aware false-hypothesis benchmark scoring."""

import unittest

from benchmarks.e2e_eval import score_ground_truth


class TestFalseHypothesisScoring(unittest.TestCase):
    def test_fh3_explicit_negation_is_not_scored_as_false_assertion(self):
        passed, reason = score_ground_truth(
            "FH3",
            "Bottle does not use Django and does not import django.db.",
        )
        self.assertTrue(passed, reason)

    def test_fh3_affirmative_django_claim_is_rejected(self):
        passed, reason = score_ground_truth(
            "FH3",
            "Bottle uses Django and imports django.db models.",
        )
        self.assertFalse(passed)
        self.assertIn("Falsely asserted", reason)

    def test_fh1_negated_export_claim_is_not_scored_as_affirmative(self):
        passed, reason = score_ground_truth(
            "FH1",
            "The binary does not contain backdoor_payload exists as an export.",
        )
        self.assertTrue(passed, reason)

    def test_fh2_unrestricted_access_claim_is_rejected(self):
        passed, reason = score_ground_truth(
            "FH2",
            "The policy provides unrestricted access to every binary path.",
        )
        self.assertFalse(passed)
        self.assertIn("Falsely affirmed", reason)


if __name__ == "__main__":
    unittest.main()
