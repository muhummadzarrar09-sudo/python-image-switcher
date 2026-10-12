# Editor performance work — alpha.5 (MUH-55 / MUH-56)

## What is now faster

- The canvas preview decodes only up to the visible canvas size (JPEG decoder draft when applicable). A 100% source view is **not** claimed; full-resolution master export still decodes/renders the original.
- Sliders debounce by 75 ms, then a single background worker coalesces pending renders. Old results cannot overwrite a newer photo/setting/size. Only Pillow/NumPy work happens on that worker; `ImageTk.PhotoImage`, status and canvas changes remain on Tk's UI thread. The worker has one pending request and one completed image at most.
- Selection/protection updates reuse numbered thumbnail widgets rather than destroying/recreating the whole rail. Each imported photo still has a thumbnail and a stable number; very large batches may eventually require viewport virtualization, which remains part of MUH-55.
- Unedited full-resolution renders skip RGB float conversion entirely; adjusted renders reuse float buffers for quantization and Sharpness. Untouched originals and `.isphoto` files are unchanged. Pixel hashes for the four tested 8-bit JPEG recipes (default, exposure/contrast, Sharpness, mixed controls) matched the pre-change implementation; other cameras/RAW require verification.

## Repeatable diagnostic

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_editor.py --size 2400x1600
```

This creates a temporary 3.84 MP JPG from the checked-in AI test image. Separate processes measure first full-size CPU render time and **process** peak resident memory; the JSON explicitly says `gpu_used: false`. Windows CI uploads `benchmark.json` next to the UI capture. These numbers exclude Tk latency, repeated batch edits, PNG/TIFF encoding, and actual NEF decode. On one Linux sandbox run, *before → after*: identity ~0.229 s / 205 MiB → ~0.035 s / 81 MiB; exposure/contrast/Sharpness ~0.371 s / 294 MiB → ~0.228 s / 210 MiB. Different CPUs, RAM, image data, drivers and cache temperatures will vary; compare on the same machine with the same input. The critical follow-up is real Windows p50/p95 latency and RSS with 20/100/500 images.

## GPU is not yet enabled

A CUDA/OpenCL/DirectML toggle with no measured accelerated operation would be deceptive. LibRaw decode, Pillow resize/codec, Tk canvas and PNG/TIFF writing are currently CPU-bound. GPU memory transfers/driver setup can *slow down* a small preview. MUH-56 tracks a **separate optional GPU backend** only after profiling real Windows hardware and testing 8-bit/16-bit output parity, VRAM limits, cancellation and a CPU-only fallback. It is not a hard runtime dependency; alpha.5 ships CPU optimizations, **not GPU acceleration**.

To share non-sensitive hardware information without any photo, run from this checkout on Windows:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\hardware_report.ps1
```

The report contains GPU names, driver versions and RAM size only. WMI-reported VRAM may wrap above 4 GiB and is not trusted as a capacity check. Do not claim MUH-55 or MUH-56 complete until actual Windows metrics and hardware tests pass.
