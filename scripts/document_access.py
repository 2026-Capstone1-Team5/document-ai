import argparse
import json
from pathlib import Path


VISUAL_TYPES = {"image", "table", "equation"}


def resolve_txt_dir(path):
    path = Path(path).resolve()
    if path.is_file():
        return path.parent
    if not path.is_dir():
        raise FileNotFoundError(f"Could not find MinerU output path: {path}")
    return path


def find_single_file(txt_dir, suffix):
    matches = sorted(txt_dir.glob(f"*{suffix}"))
    if not matches:
        raise FileNotFoundError(f"Missing {suffix} in {txt_dir}")
    if len(matches) > 1:
        raise ValueError(f"Expected one {suffix} file in {txt_dir}, found {len(matches)}")
    return matches[0]


def clean_text(text):
    if not text:
        return ""
    return " ".join(str(text).split()).strip()


def read_mineru_output(txt_dir):
    txt_dir = resolve_txt_dir(txt_dir)
    content_list_path = find_single_file(txt_dir, "_content_list.json")
    middle_path = find_single_file(txt_dir, "_middle.json")
    markdown_path = find_single_file(txt_dir, ".md")

    content_list = json.loads(content_list_path.read_text())
    middle = json.loads(middle_path.read_text())
    markdown = markdown_path.read_text()

    return {
        "txt_dir": txt_dir,
        "content_list_path": content_list_path,
        "middle_path": middle_path,
        "markdown_path": markdown_path,
        "content_list": content_list,
        "middle": middle,
        "markdown": markdown,
    }


def build_document_map(txt_dir):
    data = read_mineru_output(txt_dir)
    txt_dir = data["txt_dir"]
    content_list = data["content_list"]
    middle = data["middle"]
    markdown = data["markdown"]

    pdf_info = middle.get("pdf_info", [])
    page_count = len(pdf_info)

    pages = []
    for page_idx, page in enumerate(pdf_info, start=1):
        page_size = page.get("page_size", [None, None])
        pages.append(
            {
                "page": page_idx,
                "width": page_size[0],
                "height": page_size[1],
                "text": "",
                "section_ids": [],
                "visual_ids": [],
                "item_counts": {},
            }
        )

    def page_entry(page_number):
        while len(pages) < page_number:
            pages.append(
                {
                    "page": len(pages) + 1,
                    "width": None,
                    "height": None,
                    "text": "",
                    "section_ids": [],
                    "visual_ids": [],
                    "item_counts": {},
                }
            )
        return pages[page_number - 1]

    sections = []
    visuals = []
    current_section = None
    section_counter = 0
    visual_counter = 0

    def close_section():
        nonlocal current_section
        if current_section is None:
            return
        current_section["text"] = "\n\n".join(current_section.pop("text_parts")).strip()
        sections.append(current_section)
        current_section = None

    for item in content_list:
        item_type = item.get("type")
        page_number = item.get("page_idx", 0) + 1
        page = page_entry(page_number)
        page["item_counts"][item_type] = page["item_counts"].get(item_type, 0) + 1

        if item_type == "text":
            text = clean_text(item.get("text"))
            if not text:
                continue

            if "text_level" in item:
                close_section()
                section_counter += 1
                section_id = f"section_{section_counter:03d}"
                current_section = {
                    "id": section_id,
                    "title": text,
                    "level": item.get("text_level", 1),
                    "page_start": page_number,
                    "page_end": page_number,
                    "text_parts": [],
                }
                page["section_ids"].append(section_id)
                if page["text"]:
                    page["text"] += "\n\n"
                page["text"] += text
                continue

            if current_section is None:
                section_counter += 1
                section_id = f"section_{section_counter:03d}"
                current_section = {
                    "id": section_id,
                    "title": "Document",
                    "level": 0,
                    "page_start": page_number,
                    "page_end": page_number,
                    "text_parts": [],
                }
                page["section_ids"].append(section_id)

            current_section["page_end"] = page_number
            current_section["text_parts"].append(text)

            if page["text"]:
                page["text"] += "\n\n"
            page["text"] += text
            continue

        if item_type in VISUAL_TYPES:
            visual_counter += 1
            visual_id = f"{item_type}_{visual_counter:03d}"
            caption_key = f"{item_type}_caption"
            footnote_key = f"{item_type}_footnote"
            body_key = f"{item_type}_body"

            image_path = item.get("img_path")
            if image_path:
                image_path = str((txt_dir / image_path).resolve())

            visual = {
                "id": visual_id,
                "type": item_type,
                "page": page_number,
                "bbox": item.get("bbox"),
                "image_path": image_path,
                "section_id": current_section["id"] if current_section else None,
            }

            caption = [clean_text(x) for x in item.get(caption_key, []) if clean_text(x)]
            footnote = [clean_text(x) for x in item.get(footnote_key, []) if clean_text(x)]
            if caption:
                visual["caption"] = " ".join(caption)
            if footnote:
                visual["footnote"] = " ".join(footnote)
            if item_type == "table" and item.get(body_key):
                visual["table_body_html"] = item.get(body_key)
            if item_type == "equation":
                visual["text"] = item.get("text", "")
                visual["text_format"] = item.get("text_format")

            visuals.append(visual)
            page["visual_ids"].append(visual_id)

    close_section()

    document_map = {
        "source": {
            "txt_dir": str(txt_dir),
            "markdown_path": str(data["markdown_path"]),
            "content_list_path": str(data["content_list_path"]),
            "middle_path": str(data["middle_path"]),
        },
        "page_count": page_count or len(pages),
        "outline": [
            {
                "id": section["id"],
                "title": section["title"],
                "level": section["level"],
                "page_start": section["page_start"],
                "page_end": section["page_end"],
            }
            for section in sections
        ],
        "sections": sections,
        "pages": pages,
        "visuals": visuals,
        "markdown_path": str(data["markdown_path"]),
        "markdown_preview": markdown[:2000],
    }
    return document_map


def write_document_map(txt_dir, output_path=None):
    document_map = build_document_map(txt_dir)
    txt_dir = resolve_txt_dir(txt_dir)
    if output_path is None:
        output_path = txt_dir / "document_map.json"
    else:
        output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document_map, indent=2))
    return output_path, document_map


def load_document_map(path):
    return json.loads(Path(path).read_text())


def get_page(document_map, page_number):
    for page in document_map["pages"]:
        if page["page"] == page_number:
            return page
    raise KeyError(f"Page {page_number} not found")


def get_section(document_map, section_id):
    for section in document_map["sections"]:
        if section["id"] == section_id:
            return section
    raise KeyError(f"Section {section_id} not found")


def list_visuals(document_map):
    return document_map["visuals"]


def get_visual(document_map, visual_id):
    for visual in document_map["visuals"]:
        if visual["id"] == visual_id:
            return visual
    raise KeyError(f"Visual {visual_id} not found")


def get_outline(document_map):
    return document_map["outline"]


def main():
    parser = argparse.ArgumentParser(
        description="Build and query a document access map from MinerU output."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("txt_dir")
    build_parser.add_argument("output_json", nargs="?")

    page_parser = subparsers.add_parser("page")
    page_parser.add_argument("document_map_json")
    page_parser.add_argument("page_number", type=int)

    section_parser = subparsers.add_parser("section")
    section_parser.add_argument("document_map_json")
    section_parser.add_argument("section_id")

    outline_parser = subparsers.add_parser("outline")
    outline_parser.add_argument("document_map_json")

    visuals_parser = subparsers.add_parser("visuals")
    visuals_parser.add_argument("document_map_json")

    visual_parser = subparsers.add_parser("visual")
    visual_parser.add_argument("document_map_json")
    visual_parser.add_argument("visual_id")

    args = parser.parse_args()

    if args.command == "build":
        output_path, document_map = write_document_map(args.txt_dir, args.output_json)
        print(json.dumps({"document_map_path": str(output_path), "page_count": document_map["page_count"], "sections": len(document_map["sections"]), "visuals": len(document_map["visuals"])}, indent=2))
        return

    document_map = load_document_map(args.document_map_json)

    if args.command == "page":
        print(json.dumps(get_page(document_map, args.page_number), indent=2))
        return
    if args.command == "section":
        print(json.dumps(get_section(document_map, args.section_id), indent=2))
        return
    if args.command == "outline":
        print(json.dumps(get_outline(document_map), indent=2))
        return
    if args.command == "visuals":
        print(json.dumps(list_visuals(document_map), indent=2))
        return
    if args.command == "visual":
        print(json.dumps(get_visual(document_map, args.visual_id), indent=2))


if __name__ == "__main__":
    main()
