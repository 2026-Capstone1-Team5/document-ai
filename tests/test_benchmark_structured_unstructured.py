import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = load_module(
    "benchmark_structured_unstructured",
    SCRIPT_DIR / "benchmark_structured_unstructured.py",
)


class BenchmarkStructuredUnstructuredTests(unittest.TestCase):
    def test_main_summarizes_by_group(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            manifest_path = repo_root / "benchmark/manifests/structured.jsonl"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "doc_id": "doc-a",
                                "input_pdf": "benchmark/pdfs/doc-a.pdf",
                                "benchmark_group": "structured",
                                "language": "en",
                            }
                        ),
                        json.dumps(
                            {
                                "doc_id": "doc-b",
                                "input_pdf": "benchmark/pdfs/doc-b.pdf",
                                "benchmark_group": "unstructured",
                                "language": "en",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            args = SimpleNamespace(
                manifest=str(manifest_path),
                run_root=str(repo_root / "runs"),
                variants="original,rasterized,auto",
                timeout_seconds=10,
                output_json=str(repo_root / "results.json"),
                output_summary=str(repo_root / "summary.json"),
            )
            fake_result = {
                "status": "succeeded",
                "elapsed_seconds": 1.0,
                "requested_mode": "normal",
                "markdown_chars": 50,
            }
            stdout_buffer = io.StringIO()
            with (
                mock.patch.object(module, "REPO_ROOT", repo_root),
                mock.patch.object(module, "parse_args", return_value=args),
                mock.patch.object(module, "run_variant", return_value=fake_result),
                mock.patch("sys.stdout", stdout_buffer),
            ):
                result = module.main()
            self.assertEqual(result, 0)
            summary = json.loads((repo_root / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["total_documents"], 2)
            self.assertIn("structured", summary["benchmark_group_summary"])
            self.assertIn("unstructured", summary["benchmark_group_summary"])


if __name__ == "__main__":
    unittest.main()
