import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
OMNIDOCBENCH_DIR = SCRIPT_DIR / "omnidocbench"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


datasets_stub = types.ModuleType("datasets")


class DummyImage:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


setattr(datasets_stub, "Image", DummyImage)
setattr(datasets_stub, "load_dataset", lambda *args, **kwargs: None)
sys.modules.setdefault("datasets", datasets_stub)

huggingface_hub_stub = types.ModuleType("huggingface_hub")
setattr(huggingface_hub_stub, "hf_hub_download", lambda *args, **kwargs: "")
sys.modules.setdefault("huggingface_hub", huggingface_hub_stub)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


benchmark_omnidocbench = load_module(
    "benchmark_omnidocbench", OMNIDOCBENCH_DIR / "benchmark_omnidocbench.py"
)
run_omnidocbench_full_eval = load_module(
    "run_omnidocbench_full_eval", OMNIDOCBENCH_DIR / "run_omnidocbench_full_eval.py"
)
simple_omnidocbench_test = load_module(
    "simple_omnidocbench_test", OMNIDOCBENCH_DIR / "simple_omnidocbench_test.py"
)


class BenchmarkSummaryTests(unittest.TestCase):
    def test_summarize_reports_markdown_and_diagnostic_denominators(self):
        results = [
            {
                "status": "succeeded",
                "elapsed_seconds": 1.0,
                "markdown_chars": 100,
                "markdown_similarity": 0.9,
                "markdown_cer": 0.1,
                "has_gt": True,
                "parse_mode": "rasterized",
                "failure_reason": None,
                "has_markdown_output": True,
                "markdown_output_key": "markdown",
            },
            {
                "status": "succeeded",
                "elapsed_seconds": 2.0,
                "markdown_chars": None,
                "markdown_similarity": None,
                "markdown_cer": None,
                "has_gt": True,
                "parse_mode": "normal",
                "failure_reason": None,
                "has_markdown_output": False,
                "markdown_output_key": None,
            },
            {
                "status": "failed",
                "elapsed_seconds": 3.0,
                "markdown_chars": None,
                "markdown_similarity": None,
                "markdown_cer": None,
                "has_gt": False,
                "parse_mode": None,
                "failure_reason": "timeout",
                "has_markdown_output": False,
                "markdown_output_key": None,
            },
        ]

        summary = benchmark_omnidocbench.summarize(results)

        self.assertEqual(summary["attempted_pages"], 3)
        self.assertEqual(summary["parse_succeeded_pages"], 2)
        self.assertEqual(summary["parse_failed_pages"], 1)
        self.assertEqual(summary["markdown_available_pages"], 1)
        self.assertEqual(summary["gt_covered_pages"], 2)
        self.assertEqual(summary["diagnostic_metric_pages"], 1)
        self.assertEqual(summary["markdown_output_key_distribution"], {"markdown": 1})


class MarkdownResolutionTests(unittest.TestCase):
    def test_benchmark_resolve_markdown_output_prefers_selected_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            selected = tmp_path / "selected.md"
            markdown = tmp_path / "plain.md"
            selected.write_text("selected")
            markdown.write_text("plain")

            path, key = benchmark_omnidocbench.resolve_markdown_output(
                {
                    "outputs": {
                        "selected_markdown": str(selected),
                        "markdown": str(markdown),
                    }
                }
            )

        self.assertEqual(path, selected)
        self.assertEqual(key, "selected_markdown")

    def test_full_eval_resolve_markdown_output_falls_back_to_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            markdown = tmp_path / "plain.md"
            markdown.write_text("plain")

            path, key = run_omnidocbench_full_eval.resolve_markdown_output(
                {"outputs": {"markdown": str(markdown)}}
            )

        self.assertEqual(path, markdown)
        self.assertEqual(key, "markdown")


class EvalAccountingTests(unittest.TestCase):
    def test_summarize_eval_accounting_reports_denominators(self):
        accounting = run_omnidocbench_full_eval.summarize_eval_accounting(
            results=[
                {"status": "succeeded"},
                {"status": "succeeded"},
                {"status": "failed"},
            ],
            copied_predictions=1,
            gt_subset_pages=1,
            skip_reasons={"parse_failed": 1, "missing_markdown": 1},
        )

        self.assertEqual(accounting["attempted_pages"], 3)
        self.assertEqual(accounting["parse_succeeded_pages"], 2)
        self.assertEqual(accounting["parse_failed_pages"], 1)
        self.assertEqual(accounting["copied_prediction_pages"], 1)
        self.assertAlmostEqual(accounting["official_eval_coverage_ratio"], 1 / 3)
        self.assertAlmostEqual(accounting["official_eval_success_coverage_ratio"], 0.5)


class OfficialMetricParsingTests(unittest.TestCase):
    def test_compute_table_metrics_treats_nan_strings_as_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            metric_path = Path(tmpdir) / "metric.json"
            metric_path.write_text(
                json.dumps(
                    {
                        "text_block": {"all": {"Edit_dist": {"ALL_page_avg": "nan"}}},
                        "table": {"all": {"TEDS": {"all": "nan"}}},
                        "display_formula": {"all": {"CDM": {"all": "nan"}}},
                        "reading_order": {
                            "all": {"Edit_dist": {"ALL_page_avg": "nan"}}
                        },
                    }
                )
            )

            metrics = run_omnidocbench_full_eval.compute_table_metrics(metric_path)

        self.assertIsNone(metrics["text_edit_dist"])
        self.assertIsNone(metrics["table_teds_pct"])
        self.assertIsNone(metrics["formula_cdm_pct"])
        self.assertIsNone(metrics["reading_order_edit_dist"])
        self.assertIsNone(metrics["overall_pct"])


class OfficialEvalInputTests(unittest.TestCase):
    def test_build_official_eval_inputs_uses_selected_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            official_repo = tmp_path / "official"
            (official_repo / "demo_data").mkdir(parents=True)
            (official_repo / "configs").mkdir(parents=True)

            selected_markdown = tmp_path / "selected.md"
            selected_markdown.write_text("selected output")
            meta_path = tmp_path / "meta.json"
            meta_path.write_text(
                json.dumps({"outputs": {"selected_markdown": str(selected_markdown)}})
            )
            results_path = tmp_path / "results.json"
            results_path.write_text(
                json.dumps(
                    {
                        "results": [
                            {
                                "status": "succeeded",
                                "source_image_ref": "hf://datasets/opendatalab/OmniDocBench/images/sample.png",
                                "meta_path": str(meta_path),
                            }
                        ]
                    }
                )
            )

            gt_rows = [{"page_info": {"image_path": "images/sample.png"}}]

            with mock.patch.object(
                run_omnidocbench_full_eval,
                "hf_hub_download",
                return_value=str(tmp_path / "OmniDocBench.json"),
            ):
                (tmp_path / "OmniDocBench.json").write_text(json.dumps(gt_rows))
                pred_dir, subset_path, config_path, eval_accounting = (
                    run_omnidocbench_full_eval.build_official_eval_inputs(
                        results_path=results_path,
                        official_repo=official_repo,
                        run_label="test",
                        modules={"text"},
                    )
                )

            self.assertTrue((pred_dir / "sample.md").exists())
            self.assertEqual((pred_dir / "sample.md").read_text(), "selected output")
            self.assertEqual(json.loads(subset_path.read_text()), gt_rows)
            self.assertTrue(config_path.exists())
            self.assertEqual(eval_accounting["copied_prediction_pages"], 1)

    def test_build_official_eval_inputs_does_not_require_images_path_segment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            official_repo = tmp_path / "official"
            (official_repo / "demo_data").mkdir(parents=True)
            (official_repo / "configs").mkdir(parents=True)

            markdown = tmp_path / "plain.md"
            markdown.write_text("plain output")
            meta_path = tmp_path / "meta.json"
            meta_path.write_text(json.dumps({"outputs": {"markdown": str(markdown)}}))
            results_path = tmp_path / "results.json"
            results_path.write_text(
                json.dumps(
                    {
                        "results": [
                            {
                                "status": "succeeded",
                                "source_image_ref": "hf://datasets/opendatalab/OmniDocBench/data_diversity.png",
                                "meta_path": str(meta_path),
                            }
                        ]
                    }
                )
            )

            gt_rows = [{"page_info": {"image_path": "images/data_diversity.png"}}]

            with mock.patch.object(
                run_omnidocbench_full_eval,
                "hf_hub_download",
                return_value=str(tmp_path / "OmniDocBench.json"),
            ):
                (tmp_path / "OmniDocBench.json").write_text(json.dumps(gt_rows))
                pred_dir, subset_path, _config_path, eval_accounting = (
                    run_omnidocbench_full_eval.build_official_eval_inputs(
                        results_path=results_path,
                        official_repo=official_repo,
                        run_label="test_no_images_segment",
                        modules={"text"},
                    )
                )

            self.assertTrue((pred_dir / "data_diversity.md").exists())
            self.assertEqual(json.loads(subset_path.read_text()), gt_rows)
            self.assertEqual(eval_accounting["copied_prediction_pages"], 1)

    def test_build_official_eval_inputs_skips_bad_meta_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            official_repo = tmp_path / "official"
            (official_repo / "demo_data").mkdir(parents=True)
            (official_repo / "configs").mkdir(parents=True)

            good_markdown = tmp_path / "good.md"
            good_markdown.write_text("good output")
            good_meta_path = tmp_path / "good_meta.json"
            good_meta_path.write_text(
                json.dumps({"outputs": {"markdown": str(good_markdown)}})
            )
            bad_meta_path = tmp_path / "bad_meta.json"
            bad_meta_path.write_text("{not json")
            results_path = tmp_path / "results.json"
            results_path.write_text(
                json.dumps(
                    {
                        "results": [
                            {
                                "status": "succeeded",
                                "source_image_ref": "hf://datasets/opendatalab/OmniDocBench/images/bad.png",
                                "meta_path": str(bad_meta_path),
                            },
                            {
                                "status": "succeeded",
                                "source_image_ref": "hf://datasets/opendatalab/OmniDocBench/images/good.png",
                                "meta_path": str(good_meta_path),
                            },
                        ]
                    }
                )
            )
            gt_rows = [
                {"page_info": {"image_path": "images/bad.png"}},
                {"page_info": {"image_path": "images/good.png"}},
            ]

            with mock.patch.object(
                run_omnidocbench_full_eval,
                "hf_hub_download",
                return_value=str(tmp_path / "OmniDocBench.json"),
            ):
                (tmp_path / "OmniDocBench.json").write_text(json.dumps(gt_rows))
                pred_dir, subset_path, _config_path, eval_accounting = (
                    run_omnidocbench_full_eval.build_official_eval_inputs(
                        results_path=results_path,
                        official_repo=official_repo,
                        run_label="test_bad_meta",
                        modules={"text"},
                    )
                )

            self.assertFalse((pred_dir / "bad.md").exists())
            self.assertTrue((pred_dir / "good.md").exists())
            self.assertEqual(eval_accounting["copied_prediction_pages"], 1)
            self.assertEqual(eval_accounting["skipped_pages"]["invalid_meta_json"], 1)
            self.assertEqual(json.loads(subset_path.read_text()), [gt_rows[1]])


class SimpleWrapperTests(unittest.TestCase):
    def test_repo_root_from_script_points_to_apps_ai_root(self):
        repo_root = simple_omnidocbench_test.repo_root_from_script()

        self.assertEqual(repo_root, SCRIPT_DIR.parent)
        self.assertEqual(repo_root / "scripts" / "omnidocbench", OMNIDOCBENCH_DIR)

    def test_format_metric_returns_na_for_missing_values(self):
        self.assertEqual(simple_omnidocbench_test.format_metric(None, 2), "N/A")
        self.assertEqual(simple_omnidocbench_test.format_metric(1.2345, 2), "1.23")


class OfficialRepoPinningTests(unittest.TestCase):
    def test_ensure_official_repo_uses_pinned_ref(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            official_repo = Path(tmpdir) / "official"
            recorded = []

            def fake_run_cmd(cmd, cwd=None, env=None):
                recorded.append(cmd)
                if cmd[:2] == ["git", "clone"]:
                    official_repo.mkdir(parents=True, exist_ok=True)
                    (official_repo / "pdf_validation.py").write_text("print('ok')")

            with mock.patch.object(
                run_omnidocbench_full_eval, "run_cmd", side_effect=fake_run_cmd
            ):
                run_omnidocbench_full_eval.ensure_official_repo(official_repo)

        self.assertEqual(recorded[0][:4], ["git", "clone", "--depth", "1"])
        self.assertEqual(recorded[1][:4], ["git", "-C", str(official_repo), "fetch"])
        self.assertEqual(recorded[2][:2], ["git", "-C"])
        self.assertIn(run_omnidocbench_full_eval.OMNIDOCBENCH_OFFICIAL_REF, recorded[2])

    def test_ensure_official_repo_repins_existing_checkout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            official_repo = Path(tmpdir) / "official"
            official_repo.mkdir(parents=True, exist_ok=True)
            (official_repo / "pdf_validation.py").write_text("print('ok')")
            recorded = []

            def fake_run_cmd(cmd, cwd=None, env=None):
                recorded.append(cmd)

            completed = mock.Mock(stdout="deadbeef\n", returncode=0)

            with (
                mock.patch.object(
                    run_omnidocbench_full_eval, "run_cmd", side_effect=fake_run_cmd
                ),
                mock.patch.object(
                    run_omnidocbench_full_eval.subprocess, "run", return_value=completed
                ),
            ):
                run_omnidocbench_full_eval.ensure_official_repo(official_repo)

        self.assertEqual(recorded[0][:4], ["git", "-C", str(official_repo), "fetch"])
        self.assertEqual(recorded[1][:2], ["git", "-C"])
        self.assertIn(run_omnidocbench_full_eval.OMNIDOCBENCH_OFFICIAL_REF, recorded[1])


class BenchmarkExplicitIndexTests(unittest.TestCase):
    def test_main_raises_when_requested_indices_are_missing(self):
        args = types.SimpleNamespace(
            split="train",
            limit=5,
            offset=0,
            language="en",
            timeout_seconds=30,
            run_root=tempfile.mkdtemp(),
            report_dir=tempfile.mkdtemp(),
            indices_file=None,
        )

        class FakeImage:
            def save(self, *_args, **_kwargs):
                return None

            def convert(self, _mode):
                return self

        class FakeStreamingDataset:
            def __iter__(self):
                yield {"image": FakeImage()}

            def cast_column(self, *_args, **_kwargs):
                return self

        class FakeRawStreamingDataset:
            def __iter__(self):
                yield {"image": {"path": "images/0.png"}}

            def cast_column(self, *_args, **_kwargs):
                return self

        with tempfile.TemporaryDirectory() as tmpdir:
            indices_path = Path(tmpdir) / "indices.json"
            indices_path.write_text(json.dumps([0, 5]))
            args.indices_file = str(indices_path)

            with (
                mock.patch.object(
                    benchmark_omnidocbench.argparse.ArgumentParser,
                    "parse_args",
                    return_value=args,
                ),
                mock.patch.object(benchmark_omnidocbench, "configure_local_hf_cache"),
                mock.patch.object(
                    benchmark_omnidocbench, "load_omnidocbench_gt_map", return_value={}
                ),
                mock.patch.object(
                    benchmark_omnidocbench,
                    "load_dataset",
                    side_effect=[FakeStreamingDataset(), FakeRawStreamingDataset()],
                ),
                mock.patch.object(
                    benchmark_omnidocbench,
                    "parse_one_sample",
                    return_value={
                        "index": 0,
                        "status": "succeeded",
                        "elapsed_seconds": 1.0,
                        "parse_mode": "normal",
                        "failure_reason": None,
                        "markdown_chars": None,
                        "markdown_similarity": None,
                        "markdown_cer": None,
                        "has_gt": False,
                        "has_markdown_output": False,
                        "markdown_output_key": None,
                    },
                ),
            ):
                with self.assertRaises(ValueError) as ctx:
                    benchmark_omnidocbench.main()

        self.assertIn("Missing requested indices", str(ctx.exception))


class BenchmarkLimitZeroTests(unittest.TestCase):
    def test_main_limit_zero_skips_gt_and_dataset_loading(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir) / "run"
            report_dir = Path(tmpdir) / "reports"
            args = types.SimpleNamespace(
                split="train",
                limit=0,
                offset=0,
                language="en",
                timeout_seconds=30,
                run_root=str(run_root),
                report_dir=str(report_dir),
                indices_file=None,
            )

            with (
                mock.patch.object(
                    benchmark_omnidocbench.argparse.ArgumentParser,
                    "parse_args",
                    return_value=args,
                ),
                mock.patch.object(benchmark_omnidocbench, "configure_local_hf_cache"),
                mock.patch.object(
                    benchmark_omnidocbench,
                    "load_omnidocbench_gt_map",
                    side_effect=AssertionError("GT map should not load for limit=0"),
                ),
                mock.patch.object(
                    benchmark_omnidocbench,
                    "load_dataset",
                    side_effect=AssertionError("Dataset should not load for limit=0"),
                ),
            ):
                benchmark_omnidocbench.main()

            report = json.loads((run_root / "results.json").read_text())
            self.assertEqual(report["limit"], 0)
            self.assertEqual(report["summary"]["total_samples"], 0)
            self.assertEqual(report["results"], [])


class ParseOneSampleMetaTests(unittest.TestCase):
    def test_parse_one_sample_marks_invalid_meta_as_failed(self):
        class FakeImage:
            def save(self, path, *_args, **_kwargs):
                Path(path).write_bytes(b"png")

            def convert(self, _mode):
                return self

        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)

            def fake_run(*_args, **_kwargs):
                meta_path = run_root / "00000" / "parse_output" / "meta.json"
                meta_path.parent.mkdir(parents=True, exist_ok=True)
                meta_path.write_text("{bad json")
                return mock.Mock(returncode=0, stderr="", stdout="")

            with mock.patch.object(
                benchmark_omnidocbench.subprocess, "run", side_effect=fake_run
            ):
                result = benchmark_omnidocbench.parse_one_sample(
                    sample={"image": FakeImage()},
                    sample_ref_path="hf://datasets/opendatalab/OmniDocBench/images/sample.png",
                    gt_text=None,
                    index=0,
                    run_root=run_root,
                    language="en",
                    timeout_seconds=30,
                )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_reason"], "invalid_meta_json")


if __name__ == "__main__":
    unittest.main()
