"""
Batch Conversion Engine - Convert entire folders at once
The RHHHAAAAAA mode for power users
"""

import os
import threading
from pathlib import Path
from typing import List, Callable, Optional, Tuple, Dict
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

from .engine import ConversionEngine
from .formats import get_format_by_id, get_format_by_ext, FORMATS

@dataclass
class BatchItem:
    source_path: str
    target_path: str
    status: str = "pending"  # pending, converting, done, failed, skipped
    message: str = ""
    progress: float = 0.0

@dataclass
class BatchResult:
    total: int
    succeeded: int
    failed: int
    skipped: int
    items: List[BatchItem]
    output_dir: str

class BatchEngine:
    def __init__(self, max_workers: int = 4):
        self.engine = ConversionEngine()
        self.max_workers = max_workers
        self._stop_requested = False
        self._items: List[BatchItem] = []

    def stop(self):
        self._stop_requested = True

    def discover_images(self, input_path: str, recursive: bool = True) -> List[str]:
        """Find all images in a folder or single file"""
        p = Path(input_path)
        if p.is_file():
            return [str(p)]

        exts = set()
        for fmt in FORMATS:
            for ext in fmt.exts:
                exts.add(ext.lower())
                exts.add(ext.upper())

        files = []
        if recursive:
            for root, _, filenames in os.walk(p):
                for fn in filenames:
                    if Path(fn).suffix.lower() in exts:
                        files.append(str(Path(root) / fn))
        else:
            for fn in os.listdir(p):
                fp = Path(p) / fn
                if fp.is_file() and fp.suffix.lower() in exts:
                    files.append(str(fp))

        return sorted(files)

    def prepare_batch(self, sources: List[str], output_dir: str, target_format_id: str,
                      keep_structure: bool = False, input_root: str = None) -> List[BatchItem]:
        """Prepare target paths for batch"""
        target_fmt = get_format_by_id(target_format_id)
        if not target_fmt:
            raise ValueError(f"Unknown target format {target_format_id}")

        items = []
        for src in sources:
            src_p = Path(src)
            if keep_structure and input_root:
                # Preserve relative structure
                rel = src_p.relative_to(Path(input_root))
                target = Path(output_dir) / rel.with_suffix(target_fmt.exts[0])
            else:
                target = Path(output_dir) / f"{src_p.stem}{target_fmt.exts[0]}"

            # Avoid overwriting source if same folder and same ext
            if str(target).lower() == str(src_p).lower():
                target = target.with_name(f"{src_p.stem}_converted{target_fmt.exts[0]}")

            items.append(BatchItem(
                source_path=str(src_p),
                target_path=str(target),
                status="pending"
            ))

        self._items = items
        return items

    def convert_batch(self, items: List[BatchItem],
                      target_format_id: str,
                      quality: int = 90,
                      background_color: Tuple[int,int,int] = (255,255,255),
                      resize: Optional[Tuple[int,int]] = None,
                      overwrite: bool = False,
                      on_progress: Optional[Callable[[BatchItem, int, int], None]] = None,
                      on_item_complete: Optional[Callable[[BatchItem], None]] = None) -> BatchResult:
        """
        Convert batch with threading
        Callbacks: on_progress(item, current_index, total)
        """
        self._stop_requested = False
        total = len(items)
        succeeded = 0
        failed = 0
        skipped = 0

        # Ensure output dirs exist
        for it in items:
            os.makedirs(os.path.dirname(it.target_path), exist_ok=True)

        def convert_one(idx_item):
            idx, item = idx_item
            if self._stop_requested:
                item.status = "skipped"
                item.message = "Stopped by user"
                return item

            if os.path.exists(item.target_path) and not overwrite:
                item.status = "skipped"
                item.message = "Already exists"
                return item

            item.status = "converting"
            if on_progress:
                on_progress(item, idx+1, total)

            try:
                success, msg, _ = self.engine.convert(
                    item.source_path,
                    item.target_path,
                    target_format_id,
                    background_color=background_color,
                    quality=quality,
                    resize=resize
                )
                if success:
                    item.status = "done"
                    item.message = msg
                else:
                    item.status = "failed"
                    item.message = msg
            except Exception as e:
                item.status = "failed"
                item.message = str(e)

            if on_item_complete:
                on_item_complete(item)

            return item

        # Use ThreadPool for speed, but limit workers to avoid Pillow race
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(convert_one, (i, it)): i for i, it in enumerate(items)}

            for future in as_completed(futures):
                if self._stop_requested:
                    # Cancel remaining
                    for f in futures:
                        f.cancel()
                    break

                item = future.result()
                if item.status == "done":
                    succeeded += 1
                elif item.status == "failed":
                    failed += 1
                elif item.status == "skipped":
                    skipped += 1

        # Final count
        succeeded = sum(1 for it in items if it.status == "done")
        failed = sum(1 for it in items if it.status == "failed")
        skipped = sum(1 for it in items if it.status == "skipped")

        return BatchResult(
            total=total,
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            items=items,
            output_dir=os.path.dirname(items[0].target_path) if items else ""
        )

    def quick_convert_folder(self, input_folder: str, output_folder: str,
                             target_format: str = "png",
                             quality: int = 90,
                             recursive: bool = True,
                             keep_structure: bool = True,
                             overwrite: bool = False,
                             on_progress=None) -> BatchResult:
        """One-call folder conversion"""
        sources = self.discover_images(input_folder, recursive=recursive)
        if not sources:
            return BatchResult(0,0,0,0,[],output_folder)

        items = self.prepare_batch(sources, output_folder, target_format,
                                   keep_structure=keep_structure,
                                   input_root=input_folder if keep_structure else None)

        return self.convert_batch(items, target_format, quality=quality,
                                  overwrite=overwrite, on_progress=on_progress)
