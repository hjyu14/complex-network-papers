"""Synthetic fixtures for screening mechanics, never shown as real papers."""
import copy
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.collect import CONFIG, collect, publication_date, screen


class ScreeningTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(CONFIG.read_text(encoding="utf-8"))
        self.today = date(2026, 9, 29)
        self.item = {"DOI": "10.1234/TEST", "type": "journal-article",
                     "title": ["Synchronization in temporal networks"],
                     "published-online": {"date-parts": [[2026, 9, 20]]},
                     "container-title": ["Synthetic test journal"], "ISSN": ["0000-0000"]}

    def result(self, **changes):
        return screen(dict(self.item, **changes), self.config, self.today)

    def test_network_dynamics(self):
        paper, reason = self.result()
        self.assertEqual(reason, "included")
        self.assertEqual(paper["doi"], "10.1234/test")
        self.assertEqual(paper["categories"], ["collective", "higher"])

    def test_structure(self):
        self.assertEqual(self.result(title=["Degree distributions of random graphs"])[1], "included")

    def test_ordinary_neural_network_excluded(self):
        self.assertEqual(self.result(title=["Robust neural networks for image classification"])[1], "general_machine_learning")

    def test_neural_dynamics_exception(self):
        self.assertEqual(self.result(title=["Synchronization in neural networks"])[1], "included")

    def test_network_without_mechanism_excluded(self):
        self.assertEqual(self.result(title=["A new wireless network protocol"])[1], "not_core")

    def test_structure_substring_not_a_mechanism(self):
        self.assertEqual(self.result(title=["Crop restructuring in a trade network"])[1], "not_core")
        self.assertEqual(self.result(title=["Infrastructure spending in a network"])[1], "not_core")

    def test_material_network_requires_graph_evidence(self):
        self.assertEqual(self.result(title=["A hydrogel network with enhancement structure"])[1], "material_network_without_graph_evidence")
        self.assertEqual(self.result(title=["Percolation in polymer networks"])[1], "included")

    def test_generic_hypergraph_applications_excluded(self):
        for title in ["Hypergraph memory for anomaly detection", "Hypergraph recommendation", "Hypergraph sentiment analysis"]:
            with self.subTest(title=title):
                self.assertEqual(self.result(title=[title])[1], "general_machine_learning")

    def test_top_journal_does_not_bypass_screen(self):
        paper, reason = self.result(title=["A new molecular catalyst"], ISSN=["2041-1723"])
        self.assertIsNone(paper)
        self.assertEqual(reason, "not_core")

    def test_top_journal_requires_issn_not_name(self):
        paper, _ = self.result(**{"container-title": ["Nature"]})
        self.assertIsNone(paper["featured"])
        paper, _ = self.result(ISSN=["2041-1723"])
        self.assertEqual(paper["featured"], "NC")

    def test_online_date_takes_precedence(self):
        _, reason = self.result(**{"published-online": {"date-parts": [[2025, 9, 1]]},
                                  "published-print": {"date-parts": [[2026, 9, 20]]}})
        self.assertEqual(reason, "outside_window")

    def test_partial_preferred_date_not_replaced(self):
        _, reason = self.result(**{"published-online": {"date-parts": [[2026, 9]]},
                                  "published-print": {"date-parts": [[2026, 9, 20]]}})
        self.assertEqual(reason, "missing_or_partial_date")

    def test_print_fallback_explicit(self):
        paper, _ = self.result(**{"published-online": {}, "published-print": {"date-parts": [[2026, 9, 20]]}})
        self.assertEqual(paper["date_source"], "published-print")

    def test_invalid_date(self):
        self.assertIsNone(publication_date({"published": {"date-parts": [[2026, 2, 30]]}})[0])

    def test_future_excluded(self):
        self.assertEqual(self.result(**{"published-online": {"date-parts": [[2026, 9, 30]]}})[1], "outside_window")

    def test_90_calendar_days_boundary(self):
        for parts, reason in [([2026, 7, 2], "included"), ([2026, 7, 1], "outside_window"), ([2026, 9, 29], "included")]:
            with self.subTest(parts=parts):
                self.assertEqual(self.result(**{"published-online": {"date-parts": [parts]}})[1], reason)

    def test_preprint_excluded(self):
        self.assertEqual(self.result(type="posted-content")[1], "not_article")

    def test_correction_excluded(self):
        self.assertEqual(self.result(title=["Correction: Synchronization in networks"])[1], "notice")

    def test_abstract_not_stored(self):
        paper, _ = self.result(title=["Behavior of networks"], abstract="<p>Complex networks exhibit synchronization.</p>")
        self.assertEqual(paper["screening_basis"], "abstract_support")
        self.assertNotIn("abstract", paper)
        self.assertTrue(paper["abstract_available"])

    def test_missing_doi(self):
        self.assertEqual(self.result(DOI="")[1], "missing_doi")

    def test_collection_dedup_and_failure_retention(self):
        config = copy.deepcopy(self.config)
        config.update(queries=["test one", "test two"], featured_journals=[], max_pages_per_query=1)
        def fake_fetch(url):
            return {"total-results": 1, "items": [self.item]}
        with tempfile.TemporaryDirectory() as directory, patch("scripts.collect.time.sleep"):
            out = Path(directory)
            self.assertTrue(collect(config, self.today, out, fake_fetch))
            before = (out / "papers.json").read_bytes()
            data = json.loads(before)
            self.assertEqual(len(data["papers"]), 1)
            self.assertEqual(len(data["papers"][0]["retrieved_by"]), 2)
            def failure(url):
                raise OSError("Synthetic offline failure")
            self.assertFalse(collect(config, self.today, out, failure))
            self.assertEqual(before, (out / "papers.json").read_bytes())
            self.assertFalse(json.loads((out / "status.json").read_text(encoding="utf-8"))["ok"])

    def test_query_limit_reported(self):
        config = copy.deepcopy(self.config)
        config.update(queries=["test"], featured_journals=[], max_pages_per_query=1)
        with tempfile.TemporaryDirectory() as directory, patch("scripts.collect.time.sleep"):
            out = Path(directory)
            collect(config, self.today, out, lambda _: {"total-results": 1000, "items": [self.item], "next-cursor": "next"})
            data = json.loads((out / "papers.json").read_text(encoding="utf-8"))
            self.assertTrue(data["coverage"][0]["truncated"])


if __name__ == "__main__":
    unittest.main()
