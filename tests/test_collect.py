"""Synthetic fixtures for screening mechanics, never shown as real papers."""
import copy
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from scripts.collect import CONFIG, collect, default_collection_date, publication_date, screen


class ScreeningTests(unittest.TestCase):
    def test_baseline_freeze_does_not_advance_automatically(self):
        self.assertEqual(default_collection_date(date(2026, 9, 30)), date(2026, 9, 29))
        self.assertEqual(default_collection_date(date(2026, 10, 1)), date(2026, 9, 29))
        self.assertEqual(default_collection_date(date(2026, 9, 28)), date(2026, 9, 28))

    def setUp(self):
        self.config = json.loads(CONFIG.read_text(encoding="utf-8"))
        self.today = date(2026, 9, 29)
        self.item = {"DOI": "10.1234/TEST", "type": "journal-article",
                     "title": ["Synchronization in temporal networks"],
                     "published-online": {"date-parts": [[2026, 9, 20]]},
                     "container-title": ["Physical Review E"], "ISSN": ["2470-0053"]}

    def result(self, **changes):
        return screen(dict(self.item, **changes), self.config, self.today)

    def test_network_dynamics(self):
        paper, reason = self.result()
        self.assertEqual(reason, "included")
        self.assertEqual(paper["doi"], "10.1234/test")
        self.assertIn("network_collective", paper["categories"])
        self.assertEqual(paper["categories"], ["network_collective"])
        self.assertNotIn("topics", paper)

    def test_biomedical_applications_are_eligible(self):
        for title in ["A structure–function neuronal network model of the rat nervous system",
                      "A network atlas of the mouse brain", "A network model for cancer patients"]:
            paper, reason = self.result(title=[title], abstract="Complex networks, community detection and small-world networks.")
            self.assertIsNotNone(paper)
            self.assertEqual(reason, "included")

    def test_biomedical_mechanisms_are_not_blanket_excluded(self):
        for title in ["Synchronization in brain networks", "Community detection in a network model of the mouse brain",
                      "Percolation in a neuronal network model of the rat nervous system"]:
            self.assertEqual(self.result(title=[title])[1], "included")

    def test_author_placeholder_is_not_a_person_or_publication_status(self):
        paper, _ = self.result(author=[{"family": "Anonymous"}])
        self.assertEqual(paper["authors"], [])
        self.assertEqual(paper["author_metadata_status"], "placeholder")
        self.assertEqual(paper["author_placeholders"], ["Anonymous"])
        self.assertEqual(paper["date_source"], "published-online")
        paper, _ = self.result(author=[{"given": "Ada", "family": "Example"}, {"family": " unknown "}])
        self.assertEqual(paper["authors"], ["Ada Example"])
        self.assertEqual(paper["author_metadata_status"], "partial")
        self.assertEqual(self.result(author=None)[0]["author_metadata_status"], "missing")
        self.assertEqual(self.result(author=[{"name": "Network Research Collaboration"}])[0]["authors"], ["Network Research Collaboration"])

    def test_structure(self):
        self.assertEqual(self.result(title=["Degree distributions of random graphs"])[1], "included")

    def test_whitelist_is_hard_boundary(self):
        for issns in [["2045-2322"], ["1099-4300"], [], ["0000-0000"]]:
            with self.subTest(issns=issns):
                paper, reason = self.result(ISSN=issns, **{"container-title": ["Nature"]})
                self.assertIsNone(paper)
                self.assertEqual(reason, "journal_not_whitelisted")

    def test_whitelist_issns_unique_and_valid(self):
        seen = set()
        for journal in self.config["journals"]:
            for issn in journal["issns"]:
                self.assertNotIn(issn, seen)
                seen.add(issn)
                digits = issn.replace("-", "")
                self.assertEqual(sum((10 if c == "X" else int(c)) * (8 - i) for i, c in enumerate(digits)) % 11, 0, issn)

    def test_topics_and_category_boundaries(self):
        paper, _ = self.result(title=["Community detection in complex networks"])
        self.assertTrue(all(c.startswith("network_") for c in paper["categories"]))
        self.assertEqual(self.result(title=["Bifurcation and chaos in a nonlinear oscillator"])[1], "review_missing_abstract")

    def test_generic_stability_adaptation_and_oscillation_need_context(self):
        for title in ["Stability of a new compound", "Adaptive treatment of disease", "Oscillations of an optical signal"]:
            with self.subTest(title=title):
                self.assertEqual(self.result(title=[title])[1], "review_missing_abstract")
        self.assertEqual(self.result(title=["Stability of a driven oscillator"], abstract="Bifurcation in a nonlinear dynamical system.")[1], "review_context")

    def test_nonlinear_neural_dynamics_not_network_core(self):
        self.assertEqual(self.result(title=["Chaotic dynamics in recurrent neural networks"])[1], "review_missing_abstract")

    def test_hamiltonian_requires_dynamics_context(self):
        self.assertEqual(self.result(title=["Experimental tomography of quantum many-body Hamiltonians in solids via thermalization"])[1], "review_missing_abstract")
        self.assertEqual(self.result(title=["Transport in Hamiltonian systems"])[1], "review_missing_abstract")
        self.assertEqual(self.result(title=["Chaotic many-body quantum dynamics"])[1], "review_missing_abstract")

    def test_review_and_cross_disciplinary_not_featured(self):
        for issn, tier in [("0034-6861", "review"), ("2522-5839", "cross-disciplinary")]:
            paper, _ = self.result(ISSN=[issn])
            self.assertIsNone(paper["featured"])
            self.assertNotIn("journal_tier", paper)

    def test_correct_journal_identity(self):
        for issn, short in [("1432-1467", "J. Nonlinear Sci."), ("1573-269X", "Nonlinear Dynamics"), ("1536-0040", "SIADS")]:
            self.assertEqual(self.result(ISSN=[issn])[0]["journal_short"], short)

    def test_only_research_themes_are_exported(self):
        paper, _ = self.result(title=["Synchronization in multilayer brain networks"])
        self.assertEqual(paper["categories"], ["network_collective"])
        self.assertNotIn("network_types", paper)
        self.assertNotIn("applications", paper)

    def test_other_exclusive_and_multi_label(self):
        self.assertEqual(self.result(title=["Articulation points in multiplex networks"])[0]["categories"], ["other"])
        paper, _ = self.result(title=["Synchronization and percolation in complex networks"])
        self.assertIn("network_collective", paper["categories"])
        self.assertIn("network_spreading", paper["categories"])
        self.assertNotIn("other", paper["categories"])

    def test_spotlight_exclusions_remain_whitelisted(self):
        for issn in ["1476-4687", "1095-9203", "1745-2481"]:
            paper, reason = self.result(ISSN=[issn])
            self.assertEqual(reason, "included")
            self.assertIsNone(paper["featured"])

    def test_featured_order_and_full_names(self):
        self.assertEqual(self.config["featured_journals"], ["NC", "PRX", "SA", "PNAS", "PRL"])
        paper, _ = self.result(ISSN=["1091-6490"])
        self.assertEqual(paper["journal"], "Proceedings of the National Academy of Sciences")

    def test_ordinary_neural_network_excluded(self):
        self.assertEqual(self.result(title=["Robust neural networks for image classification"], abstract="We train a predictor for image classification.")[1], "general_machine_learning")

    def test_neural_dynamics_exception(self):
        self.assertEqual(self.result(title=["Synchronization in neural networks"])[1], "included")

    def test_network_without_mechanism_excluded(self):
        self.assertEqual(self.result(title=["A new wireless network protocol"])[1], "review_missing_abstract")

    def test_structure_substring_not_a_mechanism(self):
        self.assertEqual(self.result(title=["Crop restructuring in a trade network"])[1], "review_missing_abstract")
        self.assertEqual(self.result(title=["Infrastructure spending in a network"])[1], "review_missing_abstract")

    def test_material_network_requires_graph_evidence(self):
        self.assertEqual(self.result(title=["A hydrogel network with enhancement structure"])[1], "review_missing_abstract")
        self.assertEqual(self.result(title=["Percolation in polymer networks"])[1], "included")

    def test_generic_hypergraph_applications_excluded(self):
        for title in ["Hypergraph memory for anomaly detection", "Hypergraph recommendation", "Hypergraph sentiment analysis"]:
            with self.subTest(title=title):
                self.assertEqual(self.result(title=[title], abstract="We train a predictor for this task.")[1], "general_machine_learning")

    def test_top_journal_does_not_bypass_screen(self):
        paper, reason = self.result(title=["A new molecular catalyst"], ISSN=["2041-1723"])
        self.assertIsNone(paper)
        self.assertEqual(reason, "review_missing_abstract")

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
        self.assertEqual(paper["screening_basis"], "network")
        self.assertNotIn("abstract", paper)
        self.assertTrue(paper["abstract_available"])

    def test_missing_doi(self):
        self.assertEqual(self.result(DOI="")[1], "missing_doi")

    def test_title_without_network_can_use_abstract(self):
        paper, reason = self.result(title=["Disorder-promoted stability"], abstract="Network dynamics depend on nodal heterogeneity and stability.")
        self.assertEqual(reason, "included")
        self.assertTrue(all(r["source"] == "abstract" for r in paper["screening_routes"]))

    def test_implicit_relations_without_network_or_graph(self):
        paper, reason = self.result(title=["Diversity promotes consensus"], abstract="We study how nonreciprocal interactions between agents promote collective stability.")
        self.assertEqual(reason, "included")
        self.assertEqual(paper["screening_routes"][0]["route"], "implicit_interaction_dynamics")

    def test_routine_application_methods_count(self):
        paper, reason = self.result(title=["Connections in a local community"], abstract="We calculate degree centrality to identify influential residents.")
        self.assertEqual(reason, "included")
        self.assertEqual(paper["screening_routes"][0]["route"], "network_method")

    def test_abstract_can_override_ml_title_ambiguity(self):
        self.assertEqual(self.result(title=["Graph neural models for image classification"], abstract="We study network topology and percolation in the learned connectivity.")[1], "included")

    def test_generic_stability_not_auto_included(self):
        self.assertEqual(self.result(title=["Stability of a material"], abstract="Disorder changes the stability of a crystal.")[1], "review_context")
        self.assertEqual(self.result(title=["An unknown result"], abstract="We describe a new observation.")[1], "review_no_signal")
        self.assertEqual(self.result(title=["Modularity in software design"], abstract="Software components improve maintainability.")[1], "review_no_signal")

    def test_unrelated_sentences_do_not_join_evidence(self):
        self.assertNotEqual(self.result(title=["A new observation"], abstract="We discuss a professional network. Crystal stability increases with temperature.")[1], "included")

    def test_generic_network_structure_words_need_relational_evidence(self):
        for abstract in ["A topology-aware pruning strategy accelerates a reconstruction network.",
                         "An artificial neural network reconstructs the human cortex.",
                         "A hydrogen-bond network stabilizes the crystal structure."]:
            self.assertEqual(self.result(title=["A new application"], abstract=abstract)[1], "review_context")
        self.assertEqual(self.result(title=["A practical application"], abstract="We measure degree centrality in a small local network.")[1], "included")
        self.assertEqual(self.result(title=["Robustness of small networks"])[1], "included")
        self.assertEqual(self.result(title=["Susceptible-infectious-susceptible epidemics on temporal contact graphs with clique structure"])[1], "included")

    def test_unmatched_candidate_persisted_without_abstract(self):
        config = copy.deepcopy(self.config)
        config["journals"] = [config["journals"][13]]
        item = dict(self.item, title=["An unfamiliar phenomenon"], abstract="An observation requires further investigation.")
        with tempfile.TemporaryDirectory() as directory, patch("scripts.collect.time.sleep"):
            out = Path(directory)
            self.assertTrue(collect(config, self.today, out, lambda _: {"total-results": 1, "items": [item]}))
            report = json.loads((out / "screening-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["decisions"][0]["decision"], "review")
            self.assertNotIn("abstract", report["decisions"][0])

    def test_truncation_preserves_existing_snapshot(self):
        config = copy.deepcopy(self.config)
        config["journals"] = [config["journals"][13]]
        config["max_pages_per_journal"] = 1
        with tempfile.TemporaryDirectory() as directory, patch("scripts.collect.time.sleep"):
            out = Path(directory)
            collect(config, self.today, out, lambda _: {"total-results": 1, "items": [self.item]})
            before = (out / "papers.json").read_bytes()
            self.assertFalse(collect(config, self.today, out, lambda _: {"total-results": 1001, "items": [self.item]}))
            self.assertEqual((out / "papers.json").read_bytes(), before)

    def test_collection_dedup_and_failure_retention(self):
        config = copy.deepcopy(self.config)
        config["journals"] = [{"name":"Physical Review E", "short":"PRE", "tier":"field", "issns":["2470-0053"]}]
        config["max_pages_per_journal"] = 1
        def fake_fetch(url):
            self.assertIn("/journals/2470-0053/works?", url)
            self.assertNotIn("query=", url)
            return {"total-results": 2, "items": [self.item, self.item]}
        with tempfile.TemporaryDirectory() as directory, patch("scripts.collect.time.sleep"):
            out = Path(directory)
            self.assertTrue(collect(config, self.today, out, fake_fetch))
            before = (out / "papers.json").read_bytes()
            data = json.loads(before)
            self.assertEqual(len(data["papers"]), 1)
            self.assertEqual(len(data["papers"][0]["retrieved_by"]), 1)
            def failure(url):
                raise OSError("Synthetic offline failure")
            self.assertFalse(collect(config, self.today, out, failure))
            self.assertEqual(before, (out / "papers.json").read_bytes())
            self.assertFalse(json.loads((out / "status.json").read_text(encoding="utf-8"))["ok"])

    def test_query_limit_reported(self):
        config = copy.deepcopy(self.config)
        config["journals"] = [{"name":"Physical Review E", "short":"PRE", "tier":"field", "issns":["2470-0053"]}]
        config["max_pages_per_journal"] = 1
        with tempfile.TemporaryDirectory() as directory, patch("scripts.collect.time.sleep"):
            out = Path(directory)
            self.assertFalse(collect(config, self.today, out, lambda _: {"total-results": 1000, "items": [self.item]}))
            self.assertFalse((out / "papers.json").exists())
            data = json.loads((out / "status.json").read_text(encoding="utf-8"))
            self.assertTrue(data["coverage"][0]["truncated"])
            self.assertFalse(data["ok"])

    def test_date_sort_uses_bounded_offset_not_cursor(self):
        config = copy.deepcopy(self.config)
        config["journals"] = [config["journals"][13]]
        config["rows_per_page"] = 1
        config["max_pages_per_journal"] = 2
        offsets = []
        def fetch(url):
            params = parse_qs(urlparse(url).query)
            self.assertNotIn("cursor", params)
            self.assertEqual(set(params["select"][0].split(",")), {"DOI", "title", "type", "ISSN", "abstract", "author", "published-online", "published-print", "published", "issued", "update-to", "updated-by"})
            self.assertEqual(params["sort"], ["published"])
            offsets.append(int(params["offset"][0]))
            return {"total-results": 2, "items": [dict(self.item, DOI="10.1234/page" + params["offset"][0])]}
        with tempfile.TemporaryDirectory() as directory, patch("scripts.collect.time.sleep"):
            self.assertTrue(collect(config, self.today, Path(directory), fetch))
            self.assertEqual(offsets, [0, 1])
            data = json.loads((Path(directory) / "papers.json").read_text(encoding="utf-8"))
            self.assertEqual(len(data["papers"]), 2)
            self.assertFalse(data["coverage"][0]["truncated"])


if __name__ == "__main__":
    unittest.main()
