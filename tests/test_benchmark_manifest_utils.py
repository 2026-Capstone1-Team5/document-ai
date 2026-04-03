import csv
import importlib.util
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


utils = load_module("benchmark_manifest_utils", SCRIPT_DIR / "benchmark_manifest_utils.py")


class BenchmarkManifestUtilsTests(unittest.TestCase):
    def test_load_benchmark_manifest_csv_derives_groups(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            csv_path = repo_root / "benchmark/manifest.csv"
            pdf_dir = repo_root / "benchmark/pdfs"
            pdf_dir.mkdir(parents=True)
            (pdf_dir / "doc-a.pdf").write_bytes(b"%PDF-1.4 a")
            (pdf_dir / "doc-b.pdf").write_bytes(b"%PDF-1.4 b")
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [
                        "filename",
                        "language",
                        "digital_type",
                        "contains_tables",
                        "contains_formulas",
                        "contains_figures",
                    ]
                )
                writer.writerow(
                    ["benchmark/pdfs/doc-a.pdf", "en", "digital", "yes", "no", "yes"]
                )
                writer.writerow(
                    ["benchmark/pdfs/doc-b.pdf", "en", "scanned", "no", "no", "no"]
                )
            with mock.patch.object(utils, "REPO_ROOT", repo_root):
                rows = utils.load_benchmark_manifest_csv(csv_path)
            self.assertEqual(rows[0]["benchmark_group"], "structured")
            self.assertTrue(rows[0]["contains_tables"])
            self.assertEqual(rows[1]["benchmark_group"], "unstructured")


if __name__ == "__main__":
    unittest.main()
