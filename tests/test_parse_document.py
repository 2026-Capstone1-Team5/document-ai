import os
import sys
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

_parse_document_spec = importlib.util.spec_from_file_location(
    "parse_document", str(SCRIPT_DIR / "parse_document.py")
)
if _parse_document_spec is None:
    raise RuntimeError("Unable to load parse_document module for tests")

parse_document = importlib.util.module_from_spec(_parse_document_spec)
if _parse_document_spec.loader is None:
    raise RuntimeError("Unable to load parse_document module for tests")
_parse_document_spec.loader.exec_module(parse_document)

_rasterize_pdf_spec = importlib.util.spec_from_file_location(
    "rasterize_pdf", str(SCRIPT_DIR / "rasterize_pdf.py")
)
if _rasterize_pdf_spec is None:
    raise RuntimeError("Unable to load rasterize_pdf module for tests")

rasterize_pdf = importlib.util.module_from_spec(_rasterize_pdf_spec)
if _rasterize_pdf_spec.loader is None:
    raise RuntimeError("Unable to load rasterize_pdf module for tests")
_rasterize_pdf_spec.loader.exec_module(rasterize_pdf)


class FindComposeFileTests(unittest.TestCase):
    def test_find_compose_file_uses_environment_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            compose_file = Path(tmpdir) / "custom-compose.yml"
            compose_file.write_text("services: {}\n")

            with mock.patch.dict(
                os.environ, {"MINERU_COMPOSE_FILE": str(compose_file)}, clear=False
            ):
                self.assertEqual(
                    parse_document.find_compose_file(), compose_file.resolve()
                )

    def test_find_compose_file_raises_for_missing_environment_override(self):
        with mock.patch.dict(
            os.environ,
            {"MINERU_COMPOSE_FILE": "/tmp/does-not-exist-compose.yml"},
            clear=False,
        ):
            with self.assertRaisesRegex(RuntimeError, "MINERU_COMPOSE_FILE"):
                parse_document.find_compose_file()

    def test_find_compose_file_scans_repo_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            compose_file = Path(tmpdir) / "docker-compose.yml"
            compose_file.write_text("services: {}\n")

            with mock.patch.dict(os.environ, {}, clear=False):
                self.assertEqual(
                    parse_document.find_compose_file(repo_root=tmpdir),
                    compose_file.resolve(),
                )


class ComposeConfigTests(unittest.TestCase):
    def test_compose_file_avoids_repo_bind_mount_in_nested_docker(self):
        compose_text = (SCRIPT_DIR.parent / "compose.yaml").read_text()

        self.assertNotIn("- .:/workspace", compose_text)
        self.assertIn("- mineru-cache:/opt/mineru-cache", compose_text)
        self.assertIn("mineru-gpu:", compose_text)
        self.assertIn("gpus: all", compose_text)


class FindCliBinaryTests(unittest.TestCase):
    def test_find_cli_binary_checks_user_base_bin(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cli_dir = Path(tmpdir) / "bin"
            cli_dir.mkdir()
            cli_binary = cli_dir / "mineru"
            cli_binary.write_text("#!/bin/sh\n")

            with (
                mock.patch.object(parse_document.shutil, "which", return_value=None),
                mock.patch.object(
                    parse_document.site, "getuserbase", return_value=tmpdir
                ),
            ):
                self.assertEqual(
                    parse_document.find_cli_binary("mineru"), str(cli_binary)
                )


class HasLocalMineruTests(unittest.TestCase):
    def test_has_local_mineru_checks_installed_module(self):
        fake_spec = object()
        with (
            mock.patch.object(parse_document, "find_cli_binary", return_value=None),
            mock.patch.object(
                parse_document.importlib.util, "find_spec", return_value=fake_spec
            ),
        ):
            self.assertTrue(parse_document.has_local_mineru())


class ResolveMineruRunnerTests(unittest.TestCase):
    @staticmethod
    def fake_which(mapping):
        return lambda name: mapping.get(name)

    def test_resolve_mineru_runner_prefers_local_cli(self):
        with (
            mock.patch.object(parse_document, "has_local_mineru", return_value=True),
            mock.patch.object(parse_document, "find_compose_file") as find_compose_file,
            mock.patch.dict(os.environ, {}, clear=False),
        ):
            runner = parse_document.resolve_mineru_runner()

        self.assertEqual(runner["backend"], "local")
        self.assertEqual(runner["command_prefix"], [])
        self.assertEqual(runner["device_mode"], "cpu")
        self.assertEqual(runner["service_name"], parse_document.MINERU_CPU_SERVICE)
        find_compose_file.assert_called_once()

    def test_resolve_mineru_runner_prefers_compose_for_cuda_requests(self):
        compose_file = Path("/tmp/compose.yml")
        with (
            mock.patch.object(parse_document, "has_local_mineru", return_value=True),
            mock.patch.object(
                parse_document, "find_compose_file", return_value=compose_file
            ),
            mock.patch.object(
                parse_document, "has_docker_compose_plugin", return_value=True
            ),
            mock.patch.dict(os.environ, {"MINERU_DEVICE_MODE": "cuda"}, clear=False),
        ):
            runner = parse_document.resolve_mineru_runner()

        self.assertEqual(runner["backend"], "docker compose")
        self.assertEqual(runner["device_mode"], "cuda")
        self.assertEqual(runner["service_name"], parse_document.MINERU_GPU_SERVICE)

    def test_resolve_mineru_runner_prefers_local_for_cuda_without_compose_backend(self):
        compose_file = Path("/tmp/compose.yml")
        with (
            mock.patch.object(parse_document, "has_local_mineru", return_value=True),
            mock.patch.object(
                parse_document, "find_compose_file", return_value=compose_file
            ),
            mock.patch.object(
                parse_document, "has_docker_compose_plugin", return_value=False
            ),
            mock.patch.object(parse_document.shutil, "which", return_value=None),
            mock.patch.dict(os.environ, {"MINERU_DEVICE_MODE": "cuda"}, clear=False),
        ):
            runner = parse_document.resolve_mineru_runner()

        self.assertEqual(runner["backend"], "local")
        self.assertEqual(runner["device_mode"], "cuda")
        self.assertEqual(runner["service_name"], parse_document.MINERU_GPU_SERVICE)

    def test_resolve_mineru_runner_uses_docker_compose_plugin(self):
        compose_file = Path("/tmp/compose.yml")
        with (
            mock.patch.object(parse_document, "has_local_mineru", return_value=False),
            mock.patch.object(
                parse_document, "find_compose_file", return_value=compose_file
            ),
            mock.patch.object(
                parse_document, "has_docker_compose_plugin", return_value=True
            ),
        ):
            runner = parse_document.resolve_mineru_runner()

        self.assertEqual(runner["backend"], "docker compose")
        self.assertEqual(
            runner["command_prefix"][:4],
            ["docker", "compose", "-f", str(compose_file)],
        )
        self.assertEqual(runner["cwd"], compose_file.parent)
        self.assertEqual(runner["service_name"], parse_document.MINERU_CPU_SERVICE)

    def test_resolve_mineru_runner_uses_docker_compose_binary(self):
        compose_file = Path("/tmp/docker-compose.yml")
        with (
            mock.patch.object(parse_document, "has_local_mineru", return_value=False),
            mock.patch.object(
                parse_document.shutil,
                "which",
                side_effect=self.fake_which(
                    {"docker-compose": "/usr/local/bin/docker-compose"}
                ),
            ),
            mock.patch.object(
                parse_document, "find_compose_file", return_value=compose_file
            ),
            mock.patch.object(
                parse_document, "has_docker_compose_plugin", return_value=False
            ),
        ):
            runner = parse_document.resolve_mineru_runner()

        self.assertEqual(runner["backend"], "docker-compose")
        self.assertEqual(
            runner["command_prefix"][:4],
            ["/usr/local/bin/docker-compose", "-f", str(compose_file), "run"],
        )
        self.assertEqual(runner["cwd"], compose_file.parent)
        self.assertEqual(runner["service_name"], parse_document.MINERU_CPU_SERVICE)

    def test_resolve_mineru_runner_requires_cli_or_compose(self):
        with (
            mock.patch.object(parse_document, "has_local_mineru", return_value=False),
            mock.patch.object(parse_document, "find_compose_file", return_value=None),
        ):
            with self.assertRaisesRegex(RuntimeError, "Compose file"):
                parse_document.resolve_mineru_runner()


class BuildMineruCommandTests(unittest.TestCase):
    def test_build_mineru_command_for_local_cli(self):
        runner = {
            "backend": "local",
            "command_prefix": ["/usr/local/bin/mineru"],
            "cwd": Path.cwd(),
            "device_mode": "cuda",
            "service_name": parse_document.MINERU_GPU_SERVICE,
        }

        command = parse_document.build_mineru_command(
            runner, "benchmark/pdfs/sample2_reciept.pdf", "/tmp/output", "en"
        )

        self.assertEqual(
            command[:3],
            [
                "/usr/local/bin/mineru",
                "-p",
                str((Path("benchmark/pdfs/sample2_reciept.pdf")).resolve()),
            ],
        )
        self.assertIn("-o", command)
        self.assertIn(str(Path("/tmp/output").resolve()), command)
        self.assertEqual(command[-1], "cuda")

    def test_build_mineru_command_for_docker(self):
        runner = {
            "backend": "docker-compose",
            "command_prefix": [
                "/usr/local/bin/docker-compose",
                "-f",
                "/tmp/docker-compose.yml",
                "run",
                "--rm",
                "-T",
            ],
            "cwd": Path("/tmp"),
            "device_mode": "cuda",
            "service_name": parse_document.MINERU_GPU_SERVICE,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            host_input_dir = Path(tmpdir) / "host_input"
            host_output_dir = Path(tmpdir) / "host_output"
            host_input_dir.mkdir(parents=True, exist_ok=True)
            host_output_dir.mkdir(parents=True, exist_ok=True)

            def fake_host_path(container_path: Path):
                if str(container_path) == str(
                    Path("benchmark/pdfs/sample2_reciept.pdf").resolve().parent
                ):
                    return host_input_dir
                if str(container_path) == str(Path("/tmp/output").resolve()):
                    return host_output_dir
                return None

            with mock.patch.object(
                parse_document, "_resolve_host_path", side_effect=fake_host_path
            ):
                command = parse_document.build_mineru_command(
                    runner,
                    "benchmark/pdfs/sample2_reciept.pdf",
                    "/tmp/output",
                    "en",
                    compose_override_path=Path(tmpdir) / "override.yaml",
                )

        self.assertEqual(
            command[:7],
            [
                "/usr/local/bin/docker-compose",
                "-f",
                "/tmp/docker-compose.yml",
                "-f",
                str(Path(tmpdir) / "override.yaml"),
                "run",
                "--rm",
            ],
        )
        self.assertIn(parse_document.MINERU_GPU_SERVICE, command)
        self.assertIn("-v", command)
        self.assertIn(f"{host_input_dir}:/input:ro", command)
        self.assertIn(f"{host_output_dir}:/output", command)
        self.assertIn("/input/sample2_reciept.pdf", command[-1])
        self.assertIn("-d cuda", command[-1])

    def test_build_mineru_command_for_docker_fails_when_host_paths_missing(self):
        runner = {
            "backend": "docker-compose",
            "command_prefix": [
                "docker-compose",
                "-f",
                "/tmp/docker-compose.yml",
                "run",
                "--rm",
                "-T",
            ],
            "cwd": Path("/tmp"),
            "device_mode": "cpu",
            "service_name": parse_document.MINERU_CPU_SERVICE,
        }

        with mock.patch.object(
            parse_document,
            "_resolve_host_path",
            side_effect=lambda _: None,
        ):
            with mock.patch.object(
                parse_document, "_is_running_in_container", return_value=True
            ):
                with self.assertRaisesRegex(RuntimeError, "host-visible path"):
                    parse_document.build_mineru_command(
                        runner,
                        "benchmark/pdfs/sample2_reciept.pdf",
                        "/tmp/output",
                        "en",
                    )

    def test_build_mineru_command_for_docker_uses_local_paths_on_host(self):
        runner = {
            "backend": "docker-compose",
            "command_prefix": [
                "docker-compose",
                "-f",
                "/tmp/docker-compose.yml",
                "run",
                "--rm",
                "-T",
            ],
            "cwd": Path("/tmp"),
            "device_mode": "cpu",
            "service_name": parse_document.MINERU_CPU_SERVICE,
        }

        with mock.patch.object(
            parse_document,
            "_resolve_host_path",
            side_effect=lambda _: None,
        ):
            with mock.patch.object(
                parse_document, "_is_running_in_container", return_value=False
            ):
                command = parse_document.build_mineru_command(
                    runner,
                    "benchmark/pdfs/sample2_reciept.pdf",
                    "/tmp/output",
                    "en",
                )

        self.assertIn(
            f"{Path('benchmark/pdfs/sample2_reciept.pdf').resolve().parent}:/input:ro",
            command,
        )
        self.assertIn(f"{Path('/tmp/output').resolve()}:/output", command)


class ResolveHostPathTests(unittest.TestCase):
    def test_resolve_host_path_prefers_worker_host_temp_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            container_root = Path(tmpdir) / "worker-root"
            host_root = Path(tmpdir) / "host-root"
            container_root.mkdir()

            container_path = container_root / "a" / "b.pdf"

            with mock.patch.dict(
                os.environ,
                {
                    "WORKER_TEMP_ROOT": str(container_root),
                    "WORKER_HOST_TEMP_ROOT": str(host_root),
                },
                clear=False,
            ):
                resolved = parse_document._resolve_host_path(container_path)

            self.assertEqual(resolved, host_root / "a" / "b.pdf")

    def test_resolve_host_path_allows_missing_source_mount_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            container_root = Path(tmpdir) / "container"
            host_root = Path(tmpdir) / "host"
            container_root.mkdir()
            container_path = container_root / "missing.pdf"
            container_path_resolved = container_path.resolve()

            with (
                mock.patch.object(
                    parse_document, "_running_container_ids", return_value=["cid"]
                ),
                mock.patch.object(
                    parse_document,
                    "_docker_inspect_ids_with_mounts",
                    return_value=[
                        (
                            "cid",
                            [
                                {
                                    "Destination": str(container_path_resolved.parent),
                                    "Source": str(host_root),
                                }
                            ],
                        )
                    ],
                ),
            ):
                with mock.patch.dict(
                    os.environ,
                    {
                        "WORKER_TEMP_ROOT": "",
                        "WORKER_HOST_TEMP_ROOT": "",
                    },
                    clear=False,
                ):
                    resolved = parse_document._resolve_host_path(container_path)

            self.assertEqual(resolved, (host_root / "missing.pdf").resolve())

    def test_running_container_ids_returns_empty_when_docker_missing(self):
        with mock.patch.object(
            parse_document.subprocess,
            "run",
            side_effect=FileNotFoundError,
        ):
            self.assertEqual(parse_document._running_container_ids(), [])

    def test_docker_inspect_ids_with_mounts_returns_empty_when_docker_missing(self):
        with mock.patch.object(
            parse_document.subprocess,
            "run",
            side_effect=FileNotFoundError,
        ):
            self.assertEqual(
                parse_document._docker_inspect_ids_with_mounts(["cid"]), []
            )


class BuildRuntimeEnvTests(unittest.TestCase):
    def test_build_runtime_env_sets_local_cache_dirs(self):
        runner = {
            "backend": "local",
            "command_prefix": ["/usr/local/bin/mineru"],
            "cwd": Path.cwd(),
        }

        with mock.patch.dict(os.environ, {}, clear=True):
            env = parse_document.build_runtime_env(runner)

        self.assertIn("MPLCONFIGDIR", env)
        self.assertIn("YOLO_CONFIG_DIR", env)
        self.assertTrue(env["MPLCONFIGDIR"].startswith("/"))
        self.assertTrue(env["YOLO_CONFIG_DIR"].startswith("/"))


class MineruDeviceSelectionTests(unittest.TestCase):
    def test_get_mineru_device_mode_defaults_to_cpu(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(parse_document.get_mineru_device_mode(), "cpu")

    def test_get_mineru_service_uses_gpu_service_for_cuda(self):
        self.assertEqual(
            parse_document.get_mineru_service("cuda"),
            parse_document.MINERU_GPU_SERVICE,
        )
        self.assertEqual(
            parse_document.get_mineru_service("cuda:0"),
            parse_document.MINERU_GPU_SERVICE,
        )
        self.assertEqual(
            parse_document.get_mineru_service("cpu"),
            parse_document.MINERU_CPU_SERVICE,
        )

    def test_compose_override_targets_selected_service(self):
        override = parse_document._compose_override_for_mineru("mineru-gpu")
        self.assertIn("mineru-gpu", override)
        self.assertNotIn("mineru-cpu", override)


class LocalMineruRetryTests(unittest.TestCase):
    def test_should_retry_local_mineru_sequential_matches_permission_error(self):
        self.assertTrue(
            parse_document.should_retry_local_mineru_sequential(
                PermissionError("[Errno 1] Operation not permitted")
            )
        )

    def test_run_local_mineru_retries_once_with_sequential_render(self):
        calls = []

        def fake_invoke(pdf_path, output_dir, language, env, sequential_pdf_render):
            calls.append(sequential_pdf_render)
            if not sequential_pdf_render:
                raise PermissionError("[Errno 1] Operation not permitted")

        with mock.patch.object(
            parse_document, "invoke_local_mineru", side_effect=fake_invoke
        ):
            parse_document.run_local_mineru("in.pdf", "out", "en", {})

        self.assertEqual(calls, [False, True])


class RasterizePdfTests(unittest.TestCase):
    def test_rasterize_pdf_writes_output_pdf(self):
        try:
            import fitz
        except ImportError as exc:
            self.skipTest(f"Rasterize PDF dependencies missing: {exc}")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_pdf = tmp_path / "input.pdf"
            output_pdf = tmp_path / "output.pdf"

            doc = fitz.open()
            page = doc.new_page(width=72, height=72)
            page.insert_text((12, 36), "hello")
            doc.save(input_pdf)
            doc.close()

            rasterize_pdf.rasterize_pdf(input_pdf, output_pdf, dpi=72)

            self.assertTrue(output_pdf.exists())
            with fitz.open(output_pdf) as doc:
                self.assertEqual(len(doc), 1)


if __name__ == "__main__":
    unittest.main()
