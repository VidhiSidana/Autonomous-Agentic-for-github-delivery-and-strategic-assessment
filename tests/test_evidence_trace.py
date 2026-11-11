import json
import unittest

from agent.evidence import normalise_code_result


class TestCodeGraphTraceEvidence(unittest.TestCase):

    def test_trace_extracts_direct_and_indirect_callers(self):
        sample = {
            "function": "project.agent.orchestrator.AgentOrchestrator.process_query",
            "direction": "inbound",
            "callers_total": 3,
            "callers_total_relation": "eq",
            "callers": {
                "groups": [
                    {"qn_prefix": "project.agent.main", "rows": [["cli_main", 1]]},
                    {"qn_prefix": "project.benchmarks", "rows": [["run_benchmarks", 1]]},
                    {"qn_prefix": "project.agent", "rows": [["main", 2]]}
                ]
            }
        }

        item = normalise_code_result(
            "trace_path", "code_graph", json.dumps(sample), False
        )

        self.assertIn("Reported total: 3", item.detail)
        self.assertIn("project.agent.main.cli_main", item.detail)
        self.assertIn("project.benchmarks.run_benchmarks", item.detail)
        self.assertIn("project.agent.main", item.detail)
        self.assertIn("Direct relationships", item.detail)
        self.assertIn("Indirect relationships", item.detail)

    def test_trace_handles_zero_callers(self):
        sample = {
            "function": "project.agent.main.process_query",
            "direction": "inbound",
            "callers_total": 0,
            "callers_total_relation": "eq",
            "callers": {"groups": []}
        }

        item = normalise_code_result(
            "trace_path", "code_graph", json.dumps(sample), False
        )

        self.assertIn("Reported total: 0", item.detail)
        self.assertIn("No callers were returned", item.detail)
        self.assertIn("0 callers", item.summary)


if __name__ == "__main__":
    unittest.main()
