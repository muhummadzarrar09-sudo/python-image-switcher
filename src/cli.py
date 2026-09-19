"""
CLI for Image Switcher - for testing without GUI
"""
import argparse
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.converter.engine import ConversionEngine
from src.converter.formats import get_format_by_id, FORMATS, all_formats
from src.converter.validator import validate_conversion

def list_formats():
    print(f"\n{'ID':<10} {'EXTS':<20} {'NAME':<25} {'CAT':<15} {'ALPHA':<6} {'ANIM':<5} {'VEC':<4}")
    print("-"*100)
    for f in FORMATS:
        print(f"{f.id:<10} {','.join(f.exts[:2]):<20} {f.name:<25} {f.category:<15} {str(f.supports_alpha):<6} {str(f.supports_animation):<5} {str(f.is_vector):<4}")

def check_gate(src_id, tgt_id):
    from src.converter.formats import get_format_by_id
    src = get_format_by_id(src_id)
    tgt = get_format_by_id(tgt_id)
    if not src:
        print(f"Unknown source {src_id}")
        return
    if not tgt:
        print(f"Unknown target {tgt_id}")
        return
    gate = validate_conversion(src, tgt)
    print(f"\n{src.id.upper()} -> {tgt.id.upper()}")
    print(f"Allowed: {gate.allowed} | Status: {gate.status}")
    print(f"Reason: {gate.reason}")
    if gate.warnings:
        print("Warnings:")
        for w in gate.warnings:
            print(f"  - {w}")
    if gate.loss_description:
        print(f"Loss: {gate.loss_description}")

def convert_file(src, dst, tgt_id, quality=90):
    engine = ConversionEngine()
    src_fmt = engine.detect_source_format(src)
    print(f"Source detected: {src_fmt.id if src_fmt else 'unknown'}")
    if not os.path.exists(src):
        print(f"Source not found: {src}")
        return
    tgt = get_format_by_id(tgt_id)
    if not tgt:
        print(f"Unknown target {tgt_id}")
        return
    gate = validate_conversion(src_fmt, tgt) if src_fmt else None
    if gate:
        print(f"Gate: {gate.status} - {gate.reason}")
        if gate.warnings:
            for w in gate.warnings:
                print(f"  Warn: {w}")
    success, msg, extra = engine.convert(src, dst, tgt_id, quality=quality)
    print(f"Result: {success} - {msg}")
    if success:
        info = engine.get_image_info(dst)
        print(f"Output: {info}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Image Switcher CLI")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("list", help="List all formats")
    gate_p = sub.add_parser("gate", help="Check acceptance gate")
    gate_p.add_argument("src", help="Source format id (e.g. png)")
    gate_p.add_argument("tgt", help="Target format id (e.g. jpg)")
    conv_p = sub.add_parser("convert", help="Convert file")
    conv_p.add_argument("src", help="Source file")
    conv_p.add_argument("dst", help="Destination file")
    conv_p.add_argument("tgt", help="Target format id")
    conv_p.add_argument("--quality", type=int, default=90, help="Quality 1-100")

    args = parser.parse_args()
    if args.cmd == "list":
        list_formats()
    elif args.cmd == "gate":
        check_gate(args.src, args.tgt)
    elif args.cmd == "convert":
        convert_file(args.src, args.dst, args.tgt, args.quality)
    else:
        parser.print_help()
