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

The user has now reported **15.7 GiB system RAM**, Intel Iris Xe (Windows-reported driver `32.0.101.6790`) and NVIDIA RTX 4070 Laptop GPU (`32.0.16.1692`), and says the editor works on their Windows 11 machine. `Win32_VideoController.AdapterRAM` reported 2/4 GiB, but this value can wrap or be wrong and **is not a VRAM capacity measurement**. A Windows runner cannot emulate this laptop's drivers or thermal/power behavior.

### Optional real-device probe — not an editor GPU feature

On the user's Windows machine, in this branch after pulling, install the **optional diagnostic-only** dependency into the existing ignored editor venv, then run the generated-pixel benchmark:

```powershell
.\.venv\Scripts\python.exe -m pip install "pyopencl==2026.1.4"
.\.venv\Scripts\python.exe scripts\probe_gpu.py --size 2400x1600
```

This runs a representative exposure+contrast OpenCL kernel on a GPU device (prefer NVIDIA, otherwise another OpenCL GPU; never silently label an OpenCL CPU as accelerated), compares channel-by-channel against the editor's current CPU arithmetic on *generated* RGB pixels, and reports median **host-transfer + kernel + readback** time, kernel-only time, CPU time, output differences and device-reported memory. Nothing is enabled in preview/export by installing the probe; if OpenCL is unavailable or the driver fails it prints `gpu_executed: false` and the editor still runs CPU-only. It does not read photos, print paths, or upload results. Please share the JSON, including failures, to decide whether the measured speed/fidelity warrants an optional runtime backend. A successful kernel probe is **not** 16-bit NEF/ICC/Sharpness parity, packaged Windows compatibility, or proof of editor GPU acceleration. Do not mark MUH-56 complete until a real integrated backend, CPU fallback, full-fidelity comparisons and packaged hardware tests pass.
