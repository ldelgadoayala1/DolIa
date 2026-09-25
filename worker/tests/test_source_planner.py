"""
Tests del planificador de fuentes (HU-06). No llaman al gateway LLM:
call_llm_json se reemplaza por un mock.

Correr desde worker/:  python -m unittest discover -s tests
"""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

WORKER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKER_DIR))
os.environ.setdefault("LLM_CONFIG_PATH", str(WORKER_DIR.parent / "config" / "llm_config.json"))

from services.ai import source_planner  # noqa: E402
from services.ai.source_planner import (  # noqa: E402
    fallback_allocations,
    normalize_allocations,
    plan_sources,
    pool_budget,
)

CAP = 30


def _posts(n):
    return [{"title": f"post {i}", "url": f"https://x/{i}"} for i in range(n)]


def _probes(hits):
    return [{"name": name, "description": "desc", "posts": _posts(n)} for name, n in hits.items()]


class NormalizeAllocationsTest(unittest.TestCase):
    def test_source_without_probe_hits_gets_zero_even_if_llm_assigns(self):
        # El caso real que motivó el sondeo: el LLM le asignó 12 a HN, que
        # en ese tema devuelve 0.
        raw = {"allocations": [{"source": "hackernews", "posts": 12},
                               {"source": "rss", "posts": 12}]}
        alloc = normalize_allocations(raw, {"hackernews": 0, "rss": 5}, max_results=16, per_source_cap=CAP)
        self.assertEqual(alloc["hackernews"], 0)
        self.assertGreater(alloc["rss"], 0)

    def test_exhausted_source_capped_at_what_it_returned(self):
        # GitHub devolvió 2 de 5 en el sondeo: pedir 20 no trae más.
        raw = {"allocations": [{"source": "github", "posts": 20}, {"source": "rss", "posts": 10}]}
        alloc = normalize_allocations(raw, {"github": 2, "rss": 5}, max_results=16, per_source_cap=CAP)
        self.assertEqual(alloc["github"], 2)

    def test_per_source_cap_respected(self):
        raw = {"allocations": [{"source": "rss", "posts": 500}]}
        alloc = normalize_allocations(raw, {"rss": 5}, max_results=30, per_source_cap=CAP)
        self.assertEqual(alloc["rss"], CAP)

    def test_total_scaled_down_to_budget(self):
        raw = {"allocations": [{"source": "rss", "posts": 30}, {"source": "crossref", "posts": 30}]}
        alloc = normalize_allocations(raw, {"rss": 5, "crossref": 5}, max_results=16, per_source_cap=CAP)
        self.assertEqual(sum(alloc.values()), pool_budget(16))
        self.assertEqual(alloc["rss"], alloc["crossref"])

    def test_topped_up_to_max_results_when_llm_is_stingy(self):
        raw = {"allocations": [{"source": "rss", "posts": 3}, {"source": "crossref", "posts": 1}]}
        alloc = normalize_allocations(raw, {"rss": 5, "crossref": 5}, max_results=16, per_source_cap=CAP)
        self.assertEqual(sum(alloc.values()), 16)
        # Se completa respetando la preferencia del LLM.
        self.assertGreater(alloc["rss"], alloc["crossref"])

    def test_all_zero_returns_none(self):
        raw = {"allocations": [{"source": "rss", "posts": 0}]}
        self.assertIsNone(normalize_allocations(raw, {"rss": 5}, max_results=16, per_source_cap=CAP))

    def test_accepts_dict_format_and_case_insensitive_names(self):
        alloc = normalize_allocations({"RSS": 10, "CrossRef": 8}, {"rss": 5, "crossref": 5},
                                      max_results=16, per_source_cap=CAP)
        self.assertEqual(alloc, {"rss": 10, "crossref": 8})

    def test_malformed_response_returns_none(self):
        for raw in ({"allocations": "rss"}, None, 42, {"allocations": [{"source": "rss", "posts": "muchos"}]}):
            self.assertIsNone(normalize_allocations(raw, {"rss": 5}, max_results=16, per_source_cap=CAP))

    def test_unknown_sources_ignored(self):
        raw = {"allocations": [{"source": "twitter", "posts": 20}, {"source": "rss", "posts": 10}]}
        alloc = normalize_allocations(raw, {"rss": 5}, max_results=16, per_source_cap=CAP)
        self.assertEqual(set(alloc), {"rss"})


class FallbackAllocationsTest(unittest.TestCase):
    def test_proportional_to_probe_hits_and_uses_budget(self):
        alloc = fallback_allocations({"rss": 5, "crossref": 5, "github": 1, "stackoverflow": 0},
                                     max_results=16, per_source_cap=CAP)
        self.assertEqual(alloc["stackoverflow"], 0)
        self.assertEqual(alloc["github"], 1)  # agotada: devolvió 1 de 5
        self.assertEqual(sum(alloc.values()), pool_budget(16))

    def test_limited_by_total_capacity(self):
        alloc = fallback_allocations({"github": 2, "hackernews": 1}, max_results=16, per_source_cap=CAP)
        self.assertEqual(alloc, {"github": 2, "hackernews": 1})


class PlanSourcesTest(unittest.TestCase):
    def test_uses_llm_plan(self):
        with mock.patch.object(source_planner, "call_llm_json",
                               return_value={"allocations": [{"source": "rss", "posts": 14},
                                                             {"source": "crossref", "posts": 10}]}):
            alloc, error = plan_sources("q", _probes({"rss": 5, "crossref": 5, "hackernews": 0}),
                                        max_results=16, per_source_cap=CAP)
        self.assertIsNone(error)
        self.assertEqual(alloc, {"rss": 14, "crossref": 10, "hackernews": 0})

    def test_llm_failure_falls_back_with_error(self):
        with mock.patch.object(source_planner, "call_llm_json", side_effect=RuntimeError("504")):
            alloc, error = plan_sources("q", _probes({"rss": 5, "crossref": 5}),
                                        max_results=16, per_source_cap=CAP)
        self.assertIn("504", error)
        self.assertEqual(sum(alloc.values()), pool_budget(16))

    def test_llm_all_zero_falls_back(self):
        with mock.patch.object(source_planner, "call_llm_json",
                               return_value={"allocations": [{"source": "rss", "posts": 0}]}):
            alloc, error = plan_sources("q", _probes({"rss": 5}), max_results=16, per_source_cap=CAP)
        self.assertIsNotNone(error)
        self.assertGreater(alloc["rss"], 0)

    def test_no_probe_hits_skips_llm(self):
        with mock.patch.object(source_planner, "call_llm_json") as llm:
            alloc, error = plan_sources("q", _probes({"rss": 0, "crossref": 0}),
                                        max_results=16, per_source_cap=CAP)
        llm.assert_not_called()
        self.assertIsNone(error)
        self.assertEqual(alloc, {"rss": 0, "crossref": 0})


class StripCodeFenceTest(unittest.TestCase):
    def test_strips_json_fence(self):
        from services.ai.llm_client import _strip_code_fence
        self.assertEqual(_strip_code_fence('```json\n{"a": 1}\n```'), '{"a": 1}')
        self.assertEqual(_strip_code_fence('{"a": 1}'), '{"a": 1}')


if __name__ == "__main__":
    unittest.main()
