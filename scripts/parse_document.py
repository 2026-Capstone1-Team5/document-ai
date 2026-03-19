#!/usr/bin/env python3

import argparse
import importlib.util
import json
import os
import re
import shutil
import site
import subprocess
import tempfile
from pathlib import Path

from rasterize_pdf import rasterize_pdf


BAD_CHAR_RE = re.compile(r"[^\x09\x0A\x0D\x20-\x7EÀ-ÿ]")
REPLACEMENT_CHAR_RE = re.compile(r"\uFFFD")
MULTISPACE_RE = re.compile(r"\s{3,}")
COMPOSE_FILENAMES = (
    "compose.yml",
    "compose.yaml",
    "docker-compose.yml",
    "docker-compose.yaml",
)
MINERU_SERVICE = "mineru-cpu"
REPO_ROOT = Path(__file__).resolve().parent.parent


def inspect_pdf(pdf_path):
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError(
            "parse_document requires PyMuPDF for PDF inspection. Install it with: pip install pymupdf"
        ) from exc

    pdf_path = Path(pdf_path)

    with fitz.open(pdf_path) as doc:
        text_chars = 0
        image_pages = 0
        page_count = len(doc)
        sample_text = []

        for page in doc:
            text = page.get_text("text")
            text_chars += len(text.strip())
            if text.strip():
                sample_text.append(text.strip())
            if page.get_images(full=True):
                image_pages += 1

    joined_text = "\n".join(sample_text[:3])
    bad_chars = len(BAD_CHAR_RE.findall(joined_text))
    total_chars = max(len(joined_text), 1)
    bad_ratio = bad_chars / total_chars

    suspicious_reasons = []

    if text_chars == 0 and image_pages > 0:
        suspicious_reasons.append("image_only_pdf")

    if image_pages == page_count and 0 < text_chars < 3000 and page_count <= 3:
        suspicious_reasons.append("image_pages_with_text_layer")

    if bad_ratio > 0.02:
        suspicious_reasons.append("noisy_text_layer")

    return {
        "page_count": page_count,
        "text_chars": text_chars,
        "image_pages": image_pages,
        "bad_char_ratio": round(bad_ratio, 4),
        "suspicious": bool(suspicious_reasons),
        "reasons": suspicious_reasons,
    }


def split_pdf_into_pages(input_pdf, output_dir):
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError(
            "parse_document requires PyMuPDF for page splitting. Install it with: pip install pymupdf"
        ) from exc

    input_pdf = Path(input_pdf)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    page_paths = []
    with fitz.open(input_pdf) as source_doc:
        for page_index in range(len(source_doc)):
            single_page_path = output_dir / f"{input_pdf.stem}_page_{page_index + 1:03d}.pdf"
            single_page_doc = fitz.open()
            single_page_doc.insert_pdf(
                source_doc, from_page=page_index, to_page=page_index
            )
            single_page_doc.save(single_page_path)
            single_page_doc.close()
            page_paths.append(single_page_path)

    return page_paths


def find_compose_file(repo_root=None):
    configured_path = os.environ.get("MINERU_COMPOSE_FILE")
    if configured_path:
        compose_file = Path(configured_path).expanduser().resolve()
        if not compose_file.exists():
            raise RuntimeError(
                f"MINERU_COMPOSE_FILE points to a missing file: {compose_file}"
            )
        return compose_file

    search_root = REPO_ROOT if repo_root is None else Path(repo_root).resolve()
    for name in COMPOSE_FILENAMES:
        compose_file = search_root / name
        if compose_file.exists():
            return compose_file

    return None


def find_cli_binary(name):
    path_binary = shutil.which(name)
    if path_binary is not None:
        return path_binary

    user_base = Path(site.getuserbase())
    candidates = [
        user_base / "bin" / name,
        user_base / "Scripts" / f"{name}.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return None


def has_local_mineru():
    return find_cli_binary("mineru") is not None or importlib.util.find_spec("mineru") is not None


def has_docker_compose_plugin():
    if shutil.which("docker") is None:
        return False

    result = subprocess.run(
        ["docker", "compose", "version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return result.returncode == 0


def resolve_mineru_runner():
    if has_local_mineru():
        return {
            "backend": "local",
            "command_prefix": [],
            "cwd": REPO_ROOT,
        }

    compose_file = find_compose_file()
    if compose_file is None:
        raise RuntimeError(
            "MinerU execution requires either a local 'mineru' CLI in PATH or a "
            "Compose file that defines the 'mineru-cpu' service. Add one of "
            f"{', '.join(COMPOSE_FILENAMES)} to the repo root or set "
            "MINERU_COMPOSE_FILE=/abs/path/to/compose.yml."
        )

    if has_docker_compose_plugin():
        return {
            "backend": "docker compose",
            "command_prefix": [
                "docker",
                "compose",
                "-f",
                str(compose_file),
                "run",
                "--rm",
                "-T",
            ],
            "cwd": compose_file.parent,
        }

    docker_compose_binary = shutil.which("docker-compose")
    if docker_compose_binary is not None:
        return {
            "backend": "docker-compose",
            "command_prefix": [
                docker_compose_binary,
                "-f",
                str(compose_file),
                "run",
                "--rm",
                "-T",
            ],
            "cwd": compose_file.parent,
        }

    raise RuntimeError(
        "Neither a local 'mineru' CLI nor Docker Compose is available. Install "
        "'mineru', enable 'docker compose', or install 'docker-compose'."
    )


def build_mineru_command(runner, pdf_path, output_dir, language):
    if runner["backend"] == "local":
        return runner["command_prefix"] + [
            "-p",
            str(Path(pdf_path).resolve()),
            "-o",
            str(Path(output_dir).resolve()),
            "-b",
            "pipeline",
            "-m",
            "txt",
            "-l",
            language,
            "-d",
            "cpu",
        ]

    input_dir = Path(pdf_path).resolve().parent
    output_dir = Path(output_dir).resolve()
    input_name = Path(pdf_path).name

    return runner["command_prefix"] + [
        "-v",
        f"{input_dir}:/input:ro",
        "-v",
        f"{output_dir}:/output",
        MINERU_SERVICE,
        (
            f'mineru -p "/input/{input_name}" '
            f'-o /output -b pipeline -m txt -l "{language}" -d cpu'
        ),
    ]


def build_runtime_env(runner):
    env = os.environ.copy()
    if runner["backend"] != "local":
        return env

    cache_root = Path(tempfile.gettempdir()) / "document-ai-runtime-cache"
    matplotlib_dir = cache_root / "matplotlib"
    ultralytics_dir = cache_root / "ultralytics"
    matplotlib_dir.mkdir(parents=True, exist_ok=True)
    ultralytics_dir.mkdir(parents=True, exist_ok=True)
    env.setdefault("MPLCONFIGDIR", str(matplotlib_dir))
    env.setdefault("YOLO_CONFIG_DIR", str(ultralytics_dir))
    return env


def configure_local_mineru_env(env):
    os.environ.update(env)
    os.environ.setdefault("MINERU_DEVICE_MODE", "cpu")

    from mineru.utils.model_utils import get_vram

    os.environ.setdefault(
        "MINERU_VIRTUAL_VRAM_SIZE", str(get_vram(os.environ["MINERU_DEVICE_MODE"]))
    )
    os.environ.setdefault("MINERU_MODEL_SOURCE", "huggingface")


def should_retry_local_mineru_sequential(exc):
    message = str(exc)
    return "SC_SEM_NSEMS_MAX" in message or "Operation not permitted" in message


def invoke_local_mineru(pdf_path, output_dir, language, env, sequential_pdf_render):
    configure_local_mineru_env(env)

    from mineru.backend.pipeline import pipeline_analyze
    from mineru.cli.common import do_parse
    from mineru.utils import pdf_image_tools

    original_is_windows_environment = pdf_image_tools.is_windows_environment
    if sequential_pdf_render:
        pdf_image_tools.is_windows_environment = lambda: True

    try:
        pipeline_analyze.load_images_from_pdf = pdf_image_tools.load_images_from_pdf
        do_parse(
            output_dir=str(Path(output_dir).resolve()),
            pdf_file_names=[Path(pdf_path).stem],
            pdf_bytes_list=[Path(pdf_path).read_bytes()],
            p_lang_list=[language],
            backend="pipeline",
            parse_method="txt",
            formula_enable=True,
            table_enable=True,
        )
    finally:
        pdf_image_tools.is_windows_environment = original_is_windows_environment
        pipeline_analyze.load_images_from_pdf = pdf_image_tools.load_images_from_pdf


def run_local_mineru(pdf_path, output_dir, language, env):
    try:
        invoke_local_mineru(
            pdf_path, output_dir, language, env, sequential_pdf_render=False
        )
    except PermissionError as exc:
        if not should_retry_local_mineru_sequential(exc):
            raise
        invoke_local_mineru(
            pdf_path, output_dir, language, env, sequential_pdf_render=True
        )


def run_mineru(pdf_path, output_dir, language):
    runner = resolve_mineru_runner()
    env = build_runtime_env(runner)

    if runner["backend"] == "local":
        run_local_mineru(pdf_path, output_dir, language, env)
        return

    command = build_mineru_command(runner, pdf_path, output_dir, language)

    try:
        subprocess.run(command, check=True, cwd=runner["cwd"], env=env)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"MinerU execution failed via {runner['backend']}. "
            "If you are using Docker, ensure the daemon is running and that the "
            f"'{MINERU_SERVICE}' service is defined in the selected Compose file."
        ) from exc


def find_output_stem(result_root, preferred_stem):
    preferred_txt = Path(result_root) / preferred_stem / "txt"
    if preferred_txt.exists():
        return preferred_stem

    candidates = sorted(p.name for p in Path(result_root).iterdir() if p.is_dir())
    if len(candidates) == 1:
        return candidates[0]

    raise FileNotFoundError(
        f"Could not determine MinerU output directory under {result_root}"
    )


def find_txt_dir(output_dir, stem):
    txt_dir = Path(output_dir) / stem / "txt"
    if not txt_dir.exists():
        raise FileNotFoundError(f"MinerU output not found at {txt_dir}")
    return txt_dir


def build_output_map(txt_dir, stem):
    files = {
        "markdown": txt_dir / f"{stem}.md",
        "content_list": txt_dir / f"{stem}_content_list.json",
        "middle_json": txt_dir / f"{stem}_middle.json",
        "model_json": txt_dir / f"{stem}_model.json",
        "layout_pdf": txt_dir / f"{stem}_layout.pdf",
        "origin_pdf": txt_dir / f"{stem}_origin.pdf",
        "span_pdf": txt_dir / f"{stem}_span.pdf",
        "images_dir": txt_dir / "images",
    }

    output_map = {}
    for key, path in files.items():
        if path.exists():
            output_map[key] = str(path)

    return output_map


def score_markdown_output(markdown_path):
    markdown_path = Path(markdown_path)
    if not markdown_path.exists():
        return -10**9

    text = markdown_path.read_text(errors="ignore")
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    bad_chars = len(BAD_CHAR_RE.findall(text))
    replacement_chars = len(REPLACEMENT_CHAR_RE.findall(text))
    long_lines = sum(1 for line in lines if len(line) > 180)
    noisy_spacing = sum(1 for line in lines if MULTISPACE_RE.search(line))
    heading_count = sum(1 for line in lines if line.startswith("#"))
    table_count = text.count("<table>") + sum(1 for line in lines if line.startswith("|"))
    printable_chars = sum(1 for char in text if char.isprintable() or char in "\n\r\t")

    score = 0.0
    score += min(printable_chars, 6000) / 120.0
    score += heading_count * 2.0
    score += min(table_count, 20) * 0.75
    score -= bad_chars * 8.0
    score -= replacement_chars * 12.0
    score -= long_lines * 1.5
    score -= noisy_spacing * 0.5
    return round(score, 3)


def parse_one_variant(input_pdf, output_dir, language, dpi, parse_mode):
    input_pdf = Path(input_pdf).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    parse_input = input_pdf
    rasterized_pdf = None

    if parse_mode == "rasterized":
        rasterized_dir = output_dir / "intermediate"
        rasterized_dir.mkdir(parents=True, exist_ok=True)
        rasterized_pdf = rasterized_dir / f"{input_pdf.stem}_rasterized.pdf"
        rasterize_pdf(input_pdf, rasterized_pdf, dpi=dpi)
        parse_input = rasterized_pdf

    result_root = output_dir / "mineru_output"
    result_root.mkdir(parents=True, exist_ok=True)
    run_mineru(parse_input, result_root, language)

    output_stem = find_output_stem(result_root, parse_input.stem)
    txt_dir = find_txt_dir(result_root, output_stem)
    outputs = build_output_map(txt_dir, output_stem)
    markdown_path = outputs.get("markdown")
    quality_score = score_markdown_output(markdown_path) if markdown_path else -10**9

    variant_result = {
        "parse_mode": parse_mode,
        "parse_input": str(parse_input),
        "outputs": outputs,
        "quality_score": quality_score,
    }

    if rasterized_pdf is not None:
        variant_result["rasterized_pdf"] = str(rasterized_pdf)

    return variant_result


def write_combined_markdown(page_results, output_path):
    parts = []
    for page_result in page_results:
        markdown_path = page_result["selected"]["outputs"].get("markdown")
        if not markdown_path:
            continue
        text = Path(markdown_path).read_text(errors="ignore").strip()
        if text:
            parts.append(text)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n\n".join(parts) + "\n")
    return output_path


def run_page_adaptive_parse(input_pdf, output_dir, language, dpi):
    output_dir = Path(output_dir).resolve()
    page_input_dir = output_dir / "page_inputs"
    page_run_dir = output_dir / "page_runs"
    page_paths = split_pdf_into_pages(input_pdf, page_input_dir)

    page_results = []
    for page_index, page_pdf in enumerate(page_paths, start=1):
        original_dir = page_run_dir / f"page_{page_index:03d}" / "original"
        rasterized_dir = page_run_dir / f"page_{page_index:03d}" / "rasterized"

        original_result = parse_one_variant(page_pdf, original_dir, language, dpi, "normal")
        rasterized_result = parse_one_variant(page_pdf, rasterized_dir, language, dpi, "rasterized")

        selected = original_result
        if rasterized_result["quality_score"] > original_result["quality_score"]:
            selected = rasterized_result

        page_results.append(
            {
                "page_number": page_index,
                "original": original_result,
                "rasterized": rasterized_result,
                "selected": selected,
            }
        )

    combined_markdown = write_combined_markdown(
        page_results, output_dir / "selected_markdown.md"
    )

    return {
        "outputs": {
            "selected_markdown": str(combined_markdown),
            "page_runs_dir": str(page_run_dir),
        },
        "page_results": page_results,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Parse a PDF with MinerU and optionally rasterize first if the text layer looks suspicious."
    )
    parser.add_argument("input_pdf")
    parser.add_argument("output_dir")
    parser.add_argument("--language", default="en")
    parser.add_argument("--force-rasterize", action="store_true")
    parser.add_argument("--force-normal", action="store_true")
    parser.add_argument("--page-adaptive", action="store_true")
    parser.add_argument("--dpi", type=int, default=300)
    args = parser.parse_args()

    if args.force_rasterize and args.force_normal:
        raise ValueError("Choose only one of --force-rasterize or --force-normal")
    if args.page_adaptive and (args.force_rasterize or args.force_normal):
        raise ValueError(
            "--page-adaptive cannot be combined with --force-rasterize or --force-normal"
        )

    input_pdf = Path(args.input_pdf).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    inspection = inspect_pdf(input_pdf)

    if args.page_adaptive:
        adaptive_result = run_page_adaptive_parse(
            input_pdf, output_dir, args.language, args.dpi
        )
        metadata = {
            "input_pdf": str(input_pdf),
            "parse_mode": "page_adaptive",
            "language": args.language,
            "inspection": inspection,
            "outputs": adaptive_result["outputs"],
            "page_results": adaptive_result["page_results"],
        }
        metadata_path = output_dir / "meta.json"
        metadata_path.write_text(json.dumps(metadata, indent=2))
        print(json.dumps(metadata, indent=2))
        return

    parse_mode = "normal"
    parse_input = input_pdf
    rasterized_pdf = None

    if args.force_rasterize:
        parse_mode = "rasterized"
    elif args.force_normal:
        parse_mode = "normal"
    elif inspection["suspicious"]:
        parse_mode = "rasterized"

    if parse_mode == "rasterized":
        rasterized_dir = output_dir / "intermediate"
        rasterized_dir.mkdir(parents=True, exist_ok=True)
        rasterized_pdf = rasterized_dir / f"{input_pdf.stem}_rasterized.pdf"
        rasterize_pdf(input_pdf, rasterized_pdf, dpi=args.dpi)
        parse_input = rasterized_pdf

    result_root = output_dir / "mineru_output"
    result_root.mkdir(parents=True, exist_ok=True)
    run_mineru(parse_input, result_root, args.language)

    output_stem = find_output_stem(result_root, parse_input.stem)
    txt_dir = find_txt_dir(result_root, output_stem)
    outputs = build_output_map(txt_dir, output_stem)

    metadata = {
        "input_pdf": str(input_pdf),
        "parse_input": str(parse_input),
        "parse_mode": parse_mode,
        "language": args.language,
        "inspection": inspection,
        "outputs": outputs,
    }

    if rasterized_pdf is not None:
        metadata["rasterized_pdf"] = str(rasterized_pdf)

    metadata_path = output_dir / "meta.json"
    metadata_path.write_text(json.dumps(metadata, indent=2))

    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
