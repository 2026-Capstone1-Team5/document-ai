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
    "build_structured_benchmark_manifest",
    SCRIPT_DIR / "build_structured_benchmark_manifest.py",
)
utils = load_module("benchmark_manifest_utils_for_build", SCRIPT_DIR / "benchmark_manifest_utils.py")


class BuildStructuredBenchmarkManifestTests(unittest.TestCase):
    def test_main_writes_manifest_and_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            manifest_csv = repo_root / "benchmark/manifest.csv"
            pdf_dir = repo_root / "benchmark/pdfs"
            pdf_dir.mkdir(parents=True)
            (pdf_dir / "a.pdf").write_bytes(b"%PDF-1.4")
            manifest_csv.parent.mkdir(parents=True, exist_ok=True)
            manifest_csv.write_text(
                "filename,language,digital_type,contains_tables,contains_formulas,contains_figures\n"
                "benchmark/pdfs/a.pdf,en,digital,yes,no,no\n",
                encoding="utf-8",
            )
            output_path = repo_root / "benchmark/manifests/out.jsonl"
            args = SimpleNamespace(csv=manifest_csv, output=output_path)
            stdout_buffer = io.StringIO()
            with (
                mock.patch.object(module, "REPO_ROOT", repo_root),
                mock.patch.object(utils, "REPO_ROOT", repo_root),
                mock.patch.object(module, "load_benchmark_manifest_csv", wraps=utils.load_benchmark_manifest_csv),
                mock.patch.object(module, "parse_args", return_value=args),
                mock.patch("sys.stdout", stdout_buffer),
            ):
                result = module.main()
            self.assertEqual(result, 0)
            rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(rows[0]["benchmark_group"], "structured")
            summary = json.loads(stdout_buffer.getvalue())
            self.assertEqual(summary["total_rows"], 1)


if __name__ == "__main__":
    unittest.main()
