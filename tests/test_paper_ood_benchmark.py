import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


paper_ood_benchmark = load_module(
    "paper_ood_benchmark", SCRIPT_DIR / "paper_ood_benchmark.py"
)


class ManifestTests(unittest.TestCase):
    def test_load_manifest_reads_required_gold_contract(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            manifest = tmp_path / "manifest.jsonl"
            gold = tmp_path / "gold.json"
            gold.write_text("{}")
            manifest.write_text(
                json.dumps(
                    {
                        "doc_id": "receipt-001",
                        "input_pdf": "docs/receipt-001.pdf",
                        "subgroup": "receipt",
                        "gold_path": str(gold),
                        "gold_format": "fields_json",
                        "metric_family": "token_f1",
                        "annotation_source": "manual",
                        "canonicalization_version": "v1",
                    }
                )
                + "\n"
            )

            rows = paper_ood_benchmark.load_manifest(manifest)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["language"], "en")
        self.assertEqual(rows[0]["doc_id"], "receipt-001")

    def test_load_manifest_rejects_missing_gold_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = Path(tmpdir) / "manifest.jsonl"
            manifest.write_text(
                json.dumps(
                    {
                        "doc_id": "receipt-001",
                        "input_pdf": "docs/receipt-001.pdf",
                        "subgroup": "receipt",
                    }
                )
                + "\n"
            )

            with self.assertRaises(ValueError):
                paper_ood_benchmark.load_manifest(manifest)


class VariantExecutionTests(unittest.TestCase):
    def make_row(self, tmp_path: Path) -> dict:
        source = tmp_path / "source.pdf"
        stripped = tmp_path / "source_stripped.pdf"
        gold = tmp_path / "gold.json"
        source.write_bytes(b"pdf")
        stripped.write_bytes(b"pdf")
        gold.write_text("{}")
        return {
            "doc_id": "doc-001",
            "input_pdf": str(source),
            "stripped_pdf": str(stripped),
            "subgroup": "receipt",
            "gold_path": str(gold),
            "gold_format": "fields_json",
            "metric_family": "exact_match",
            "annotation_source": "manual",
            "canonicalization_version": "v1",
            "language": "en",
        }

    def test_run_variant_uses_stripped_input_for_text_layer_variant(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            row = self.make_row(tmp_path)
            output_dir = tmp_path / "out"
            recorded = {}

            def fake_run(cmd, **_kwargs):
                recorded["cmd"] = cmd
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / "meta.json").write_text(
                    json.dumps(
                        {
                            "parse_mode": "normal",
                            "inspection": {"suspicious": False},
                            "outputs": {"markdown": str(output_dir / "doc.md")},
                        }
                    )
                )
                (output_dir / "doc.md").write_text("markdown")
                return mock.Mock(returncode=0, stdout="", stderr="")

            with mock.patch.object(
                paper_ood_benchmark.subprocess, "run", side_effect=fake_run
            ):
                result = paper_ood_benchmark.run_variant(
                    row=row,
                    variant="text_layer_stripped",
                    output_dir=output_dir,
                    timeout_seconds=30,
                )

        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["requested_mode"], "normal")
        self.assertEqual(recorded["cmd"][2], row["stripped_pdf"])
        self.assertIn("--force-normal", recorded["cmd"])

    def test_summarize_tracks_completeness_and_failures(self):
        results = [
            {
                "subgroup": "receipt",
                "paired_complete": True,
                "variants": {
                    "original": {"status": "succeeded", "elapsed_seconds": 1.0},
                    "rasterized": {"status": "succeeded", "elapsed_seconds": 2.0},
                    "auto": {"status": "succeeded", "elapsed_seconds": 1.5},
                },
            },
            {
                "subgroup": "ticket",
                "paired_complete": False,
                "variants": {
                    "original": {
                        "status": "failed",
                        "failure_reason": "timeout",
                    },
                    "rasterized": {"status": "succeeded", "elapsed_seconds": 2.5},
                    "auto": {"status": "succeeded", "elapsed_seconds": 2.0},
                },
            },
        ]

        summary = paper_ood_benchmark.summarize(
            results, ["original", "rasterized", "auto"]
        )

        self.assertEqual(summary["attempted_documents"], 2)
        self.assertEqual(summary["fully_completed_documents"], 1)
        self.assertAlmostEqual(summary["paired_completeness_rate"], 0.5)
        self.assertEqual(summary["variant_success_counts"]["original"], 1)
        self.assertEqual(summary["subgroup_counts"]["receipt"], 1)
        self.assertEqual(summary["failure_reasons"]["original:timeout"], 1)

    def test_validate_variant_requirements_requires_stripped_pdf_for_causal_variant(self):
        rows = [
            {
                "doc_id": "doc-001",
                "input_pdf": "/tmp/source.pdf",
                "gold_path": "/tmp/gold.json",
                "gold_format": "fields_json",
                "metric_family": "exact_match",
                "annotation_source": "manual",
                "canonicalization_version": "v1",
                "subgroup": "receipt",
            }
        ]

        with self.assertRaises(ValueError):
            paper_ood_benchmark.validate_variant_requirements(
                rows, ["original", "text_layer_stripped"]
            )

    def test_write_report_writes_latest_summary_alias(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            report = {
                "manifest": "manifest.jsonl",
                "run_root": str(tmp_path / "run"),
                "variants": ["original", "auto"],
                "summary": {"paired_completeness_rate": 1.0},
                "results": [],
            }
            run_root = tmp_path / "run"
            run_root.mkdir()
            report_dir = tmp_path / "reports"

            results_path, summary_path = paper_ood_benchmark.write_report(
                report, run_root, report_dir
            )
            results_exists = results_path.exists()
            summary_exists = summary_path.exists()
            latest_exists = (
                report_dir / "latest_paper_ood_benchmark_summary.json"
            ).exists()

        self.assertTrue(results_exists)
        self.assertTrue(summary_exists)
        self.assertTrue(latest_exists)


if __name__ == "__main__":
    unittest.main()
