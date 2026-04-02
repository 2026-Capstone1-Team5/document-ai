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
    def test_build_official_eval_inputs_prefers_official_image_path_from_results(self):
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
                                "source_image_ref": "hf://datasets/opendatalab/OmniDocBench@rev/data_diversity.png",
                                "official_image_path": "images/real_sample.png",
                                "meta_path": str(meta_path),
                            }
                        ]
                    }
                )
            )

            gt_rows = [{"page_info": {"image_path": "images/real_sample.png"}}]

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
                        run_label="test_official_path",
                        modules={"text"},
                    )
                )

            self.assertTrue((pred_dir / "real_sample.md").exists())
            self.assertEqual(json.loads(subset_path.read_text()), gt_rows)
            self.assertEqual(eval_accounting["official_gt_subset_pages"], 1)

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

    def test_build_official_eval_inputs_raises_when_gt_subset_is_empty(self):
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
                                "source_image_ref": "hf://datasets/opendatalab/OmniDocBench@rev/data_diversity.png",
                                "meta_path": str(meta_path),
                            }
                        ]
                    }
                )
            )

            with mock.patch.object(
                run_omnidocbench_full_eval,
                "hf_hub_download",
                return_value=str(tmp_path / "OmniDocBench.json"),
            ):
                (tmp_path / "OmniDocBench.json").write_text(json.dumps([]))
                with self.assertRaises(RuntimeError) as ctx:
                    run_omnidocbench_full_eval.build_official_eval_inputs(
                        results_path=results_path,
                        official_repo=official_repo,
                        run_label="test_empty_subset",
                        modules={"text"},
                    )

        self.assertIn("No ground-truth rows matched", str(ctx.exception))

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

    def test_simple_wrapper_calls_benchmark_without_split(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            args = types.SimpleNamespace(
                limit=2,
                offset=3,
                name="simple_run",
                official_repo=str(tmp_path / "official"),
            )
            temp_json = (
                Path(tempfile.gettempdir()) / "omnidocbench_simple_run_summary.json"
            )
            commands = []

            def fake_run_cmd(cmd):
                commands.append(cmd)
                if "run_omnidocbench_full_eval.py" in " ".join(cmd):
                    temp_json.write_text(
                        json.dumps(
                            {
                                "table_metrics": {
                                    "text_edit_dist": 0.1,
                                    "formula_cdm_pct": 0.2,
                                    "table_teds_pct": 0.3,
                                    "reading_order_edit_dist": 0.4,
                                    "overall_pct": 0.5,
                                }
                            }
                        )
                    )

            with (
                mock.patch.object(
                    simple_omnidocbench_test.argparse.ArgumentParser,
                    "parse_args",
                    return_value=args,
                ),
                mock.patch.object(
                    simple_omnidocbench_test, "run_cmd", side_effect=fake_run_cmd
                ),
                mock.patch.object(
                    simple_omnidocbench_test,
                    "repo_root_from_script",
                    return_value=tmp_path,
                ),
            ):
                simple_omnidocbench_test.main()

            benchmark_cmd = commands[0]
            self.assertNotIn("--split", benchmark_cmd)
            self.assertFalse(temp_json.exists())


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


class ProvenanceOutputTests(unittest.TestCase):
    def test_write_outputs_includes_evaluator_and_dataset_provenance(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            output_json = tmp_path / "summary.json"
            output_md = tmp_path / "summary.md"
            parse_results_path = tmp_path / "results.json"
            metric_path = tmp_path / "metric.json"
            pred_dir = tmp_path / "pred"
            subset_path = tmp_path / "subset.json"
            config_path = tmp_path / "config.yaml"
            for path in [parse_results_path, metric_path, subset_path, config_path]:
                path.write_text("{}")
            pred_dir.mkdir()

            run_omnidocbench_full_eval.write_outputs(
                output_json=output_json,
                output_md=output_md,
                run_label="provenance",
                parse_results_path=parse_results_path,
                metric_path=metric_path,
                pred_dir=pred_dir,
                subset_path=subset_path,
                config_path=config_path,
                table_metrics={
                    "text_edit_dist": 0.1,
                    "text_score_pct": 90.0,
                    "table_teds_raw": 0.8,
                    "table_teds_pct": 80.0,
                    "formula_cdm_raw": 0.7,
                    "formula_cdm_pct": 70.0,
                    "reading_order_edit_dist": 0.2,
                    "overall_pct": 80.0,
                },
                parse_summary={},
                eval_accounting={
                    "attempted_pages": 1,
                    "parse_succeeded_pages": 1,
                    "parse_failed_pages": 0,
                    "copied_prediction_pages": 1,
                    "official_gt_subset_pages": 1,
                    "official_eval_coverage_ratio": 1.0,
                    "official_eval_success_coverage_ratio": 1.0,
                    "skipped_pages": {},
                },
                evaluator_ref="eval-ref-123",
                dataset_revision="dataset-rev-456",
                dataset_source="hf://datasets/opendatalab/OmniDocBench",
            )

            payload = json.loads(output_json.read_text())
            markdown = output_md.read_text()

        self.assertEqual(payload["official_evaluator_ref"], "eval-ref-123")
        self.assertEqual(payload["dataset_revision"], "dataset-rev-456")
        self.assertEqual(payload["dataset_source"], "hf://datasets/opendatalab/OmniDocBench")
        self.assertIn("Evaluator ref", markdown)
        self.assertIn("Dataset revision", markdown)


class BenchmarkExplicitIndexTests(unittest.TestCase):
    def test_main_raises_when_requested_indices_are_missing(self):
        args = types.SimpleNamespace(
            limit=5,
            offset=0,
            language="en",
            timeout_seconds=30,
            run_root=tempfile.mkdtemp(),
            report_dir=tempfile.mkdtemp(),
            indices_file=None,
        )

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
                    benchmark_omnidocbench,
                    "load_gt_rows",
                    return_value=[
                        {"page_info": {"image_path": "images/0.png"}, "layout_dets": []}
                    ],
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
                    "load_gt_rows",
                    side_effect=AssertionError("GT map should not load for limit=0"),
                ),
            ):
                benchmark_omnidocbench.main()

            report = json.loads((run_root / "results.json").read_text())
            self.assertEqual(report["limit"], 0)
            self.assertNotIn("split", report)
            self.assertEqual(report["summary"]["total_samples"], 0)
            self.assertEqual(report["results"], [])


class EnsureParseResultsTests(unittest.TestCase):
    def test_ensure_parse_results_omits_split_argument(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            scripts_dir = tmp_path / "scripts" / "omnidocbench"
            scripts_dir.mkdir(parents=True)
            run_root = tmp_path / "run"
            report_dir = tmp_path / "reports"
            recorded = []

            def fake_run_cmd(cmd, cwd=None, env=None):
                recorded.append(cmd)
                run_root.mkdir(parents=True, exist_ok=True)
                (run_root / "results.json").write_text(json.dumps({"results": []}))

            with mock.patch.object(
                run_omnidocbench_full_eval, "run_cmd", side_effect=fake_run_cmd
            ):
                result_path = run_omnidocbench_full_eval.ensure_parse_results(
                    scripts_dir=scripts_dir,
                    offset=4,
                    limit=7,
                    language="en",
                    timeout_seconds=30,
                    run_root=run_root,
                    report_dir=report_dir,
                    skip_parse=False,
                )

        self.assertEqual(result_path, run_root / "results.json")
        self.assertNotIn("--split", recorded[0])


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
