import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import parse_document


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


class FindCliBinaryTests(unittest.TestCase):
    def test_find_cli_binary_checks_user_base_bin(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cli_dir = Path(tmpdir) / "bin"
            cli_dir.mkdir()
            cli_binary = cli_dir / "mineru"
            cli_binary.write_text("#!/bin/sh\n")

            with mock.patch.object(parse_document.shutil, "which", return_value=None), mock.patch.object(
                parse_document.site, "getuserbase", return_value=tmpdir
            ):
                self.assertEqual(parse_document.find_cli_binary("mineru"), str(cli_binary))


class HasLocalMineruTests(unittest.TestCase):
    def test_has_local_mineru_checks_installed_module(self):
        fake_spec = object()
        with mock.patch.object(parse_document, "find_cli_binary", return_value=None), mock.patch.object(
            parse_document.importlib.util, "find_spec", return_value=fake_spec
        ):
            self.assertTrue(parse_document.has_local_mineru())


class ResolveMineruRunnerTests(unittest.TestCase):
    @staticmethod
    def fake_which(mapping):
        return lambda name: mapping.get(name)

    def test_resolve_mineru_runner_prefers_local_cli(self):
        with mock.patch.object(
            parse_document, "has_local_mineru", return_value=True
        ), mock.patch.object(parse_document, "find_compose_file") as find_compose_file:
            runner = parse_document.resolve_mineru_runner()

        self.assertEqual(runner["backend"], "local")
        self.assertEqual(runner["command_prefix"], [])
        find_compose_file.assert_not_called()

    def test_resolve_mineru_runner_uses_docker_compose_plugin(self):
        compose_file = Path("/tmp/compose.yml")
        with mock.patch.object(
            parse_document, "has_local_mineru", return_value=False
        ), mock.patch.object(
            parse_document, "find_compose_file", return_value=compose_file
        ), mock.patch.object(
            parse_document, "has_docker_compose_plugin", return_value=True
        ):
            runner = parse_document.resolve_mineru_runner()

        self.assertEqual(runner["backend"], "docker compose")
        self.assertEqual(
            runner["command_prefix"][:4],
            ["docker", "compose", "-f", str(compose_file)],
        )
        self.assertEqual(runner["cwd"], compose_file.parent)

    def test_resolve_mineru_runner_uses_docker_compose_binary(self):
        compose_file = Path("/tmp/docker-compose.yml")
        with mock.patch.object(
            parse_document, "has_local_mineru", return_value=False
        ), mock.patch.object(
            parse_document.shutil,
            "which",
            side_effect=self.fake_which({"docker-compose": "/usr/local/bin/docker-compose"}),
        ), mock.patch.object(
            parse_document, "find_compose_file", return_value=compose_file
        ), mock.patch.object(
            parse_document, "has_docker_compose_plugin", return_value=False
        ):
            runner = parse_document.resolve_mineru_runner()

        self.assertEqual(runner["backend"], "docker-compose")
        self.assertEqual(
            runner["command_prefix"][:4],
            ["/usr/local/bin/docker-compose", "-f", str(compose_file), "run"],
        )
        self.assertEqual(runner["cwd"], compose_file.parent)

    def test_resolve_mineru_runner_requires_cli_or_compose(self):
        with mock.patch.object(
            parse_document, "has_local_mineru", return_value=False
        ), mock.patch.object(parse_document, "find_compose_file", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Compose file"):
                parse_document.resolve_mineru_runner()


class BuildMineruCommandTests(unittest.TestCase):
    def test_build_mineru_command_for_local_cli(self):
        runner = {
            "backend": "local",
            "command_prefix": ["/usr/local/bin/mineru"],
            "cwd": Path.cwd(),
        }

        command = parse_document.build_mineru_command(
            runner, "benchmark/pdfs/sample2_reciept.pdf", "/tmp/output", "en"
        )

        self.assertEqual(command[:3], ["/usr/local/bin/mineru", "-p", str((Path("benchmark/pdfs/sample2_reciept.pdf")).resolve())])
        self.assertIn("-o", command)
        self.assertIn(str(Path("/tmp/output").resolve()), command)

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
        }

        command = parse_document.build_mineru_command(
            runner, "benchmark/pdfs/sample2_reciept.pdf", "/tmp/output", "en"
        )

        self.assertEqual(command[:6], runner["command_prefix"])
        self.assertIn(parse_document.MINERU_SERVICE, command)
        self.assertIn('/input/sample2_reciept.pdf', command[-1])


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

        with mock.patch.object(parse_document, "invoke_local_mineru", side_effect=fake_invoke):
            parse_document.run_local_mineru("in.pdf", "out", "en", {})

        self.assertEqual(calls, [False, True])


if __name__ == "__main__":
    unittest.main()
