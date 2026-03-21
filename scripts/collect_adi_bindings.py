#!/usr/bin/env python3
"""Collect ADI-compatible bindings from a Linux kernel checkout."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from adi_binding_lib import (
    build_collection_report,
    collect_bindings,
    generate_template_artifacts,
    audit_bindings,
    resolve_linux_source,
    write_json,
    write_markdown,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect ADI-compatible bindings from Linux devicetree bindings.",
    )
    parser.add_argument("--linux-path", type=Path, help="Path to a local linux checkout.")
    parser.add_argument("--linux-url", help="Clone URL for linux checkout.")
    parser.add_argument("--linux-ref", help="Optional git branch/tag when cloning.")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Path to the pyadi-dt repository root.",
    )
    parser.add_argument(
        "--include-yaml",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Search .yaml/.yml files.",
    )
    parser.add_argument(
        "--include-txt",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Search .txt binding docs.",
    )
    parser.add_argument(
        "--only-adi",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Keep only bindings with ADI-compatible entries.",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON report path.")
    parser.add_argument("--report", type=Path, help="Optional markdown summary path.")
    parser.add_argument(
        "--generate-templates",
        action="store_true",
        default=False,
        help="Generate starter board templates for undocumented bindings.",
    )
    parser.add_argument(
        "--template-out-dir",
        type=Path,
        help="Directory for generated board templates (default: adidt/templates/boards).",
    )
    parser.add_argument(
        "--template-json-out",
        type=Path,
        help="Optional JSON manifest path for template generation results.",
    )
    parser.add_argument(
        "--template-doc-out",
        type=Path,
        help="Optional Markdown path for template generation documentation.",
    )
    parser.add_argument(
        "--reference-targets",
        type=Path,
        help="Optional reference_dts_targets.json override.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Overwrite existing generated templates.",
    )
    parser.add_argument("--quiet", action="store_true", default=False)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.linux_path and not args.linux_url:
        raise SystemExit("--linux-path or --linux-url is required.")

    linux_root, cleanup_dir = resolve_linux_source(
        linux_path=args.linux_path,
        linux_url=args.linux_url,
        linux_ref=args.linux_ref,
    )
    try:
        records = collect_bindings(
            linux_root=linux_root,
            include_yaml=args.include_yaml,
            include_txt=args.include_txt,
            only_adi=args.only_adi,
        )
        report = build_collection_report(records, linux_root=linux_root)

        if args.output:
            write_json(args.output, report)
        if args.report:
            write_markdown(args.report, report, kind="collect")

        template_report = None
        if args.generate_templates:
            audit_report = audit_bindings(
                linux_root=linux_root,
                project_root=args.project_root,
                include_yaml=args.include_yaml,
                include_txt=args.include_txt,
                only_adi=args.only_adi,
            )
            template_report = generate_template_artifacts(
                audit_report,
                project_root=args.project_root,
                template_out_dir=args.template_out_dir,
                reference_targets_path=args.reference_targets,
                template_doc_out=args.template_doc_out,
                linux_ref=args.linux_ref,
                force=args.force,
            )
            if args.template_json_out:
                write_json(args.template_json_out, template_report)
            if args.template_doc_out:
                write_markdown(args.template_doc_out, template_report, kind="template-audit")

        if not args.quiet:
            summary = report["summary"]
            print(f"Parsed {summary['total_bindings']} ADI binding files")
            print(f"Total compatibles: {summary['total_compatibles']}")
            if args.output:
                print(f"JSON: {args.output}")
            if args.report:
                print(f"Markdown: {args.report}")
            if template_report is not None:
                template_summary = template_report["summary"]
                print(f"Generated templates: {template_summary['generated_templates']}")
                print(
                    "Skipped existing templates: "
                    f"{template_summary['skipped_existing_templates']}"
                )
                print(
                    "Not generated templates: "
                    f"{template_summary['not_generated_templates']}"
                )
                if args.template_json_out:
                    print(f"Template JSON: {args.template_json_out}")
                if args.template_doc_out:
                    print(f"Template Markdown: {args.template_doc_out}")
        return 0
    finally:
        if cleanup_dir is not None:
            shutil.rmtree(cleanup_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
