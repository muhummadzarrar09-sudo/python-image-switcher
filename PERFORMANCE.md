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

## GPU: opt-in preview experiment, not full-editor/export acceleration

The user's Windows 11 report: **15.7 GiB RAM**, Intel Iris Xe (`32.0.101.6790`) and RTX 4070 Laptop (`32.0.16.1692`). WMI-reported 2/4 GiB adapter RAM was inaccurate for the RTX: OpenCL on the actual laptop reports **8 GiB**, driver `616.92`. The user's generated-pixel 2400×1600 OpenCL exposure+contrast probe measured CPU **0.08767 s** versus GPU transfer+kernel+readback **0.00275 s**, with **0 differing channels out of 11,520,000**. That ~32× *isolated math* result is not a prediction for full UI speed, RAW decode or export. PyOpenCL emitted a non-fatal compiler-output warning; repeated-kernel-retrieval overhead in the probe has been fixed.

The source checkout now contains an **experimental, explicitly opt-in** OpenCL fast path for canvas-size, 8-bit RGB **exposure and/or contrast only**. It runs inside the existing coalescing preview worker and labels a result `experimental GPU` only if that request really used the GPU. Unsupported edits (including Sharpness, backgrounds, crop/rotation, alpha, NEF), unavailable devices or runtime failures use the unchanged CPU preview. Full-resolution render/export, source bytes and projects **always** use CPU. GPU is **off by default**, pyopencl is not a mandatory dependency or validated part of the PyInstaller/installer build. This cannot be called completed MUH-56: actual integrated UI speed, varying slider parity, installer packaging, 16-bit/ICC and CPU fallback still require coverage.

The user ran `scripts/probe_integrated_preview.py` on their RTX 4070 laptop at a 1200×800 preview size: **CPU median 0.03448 s → GPU opt-in median 0.01564 s** (about **2.2×** faster for this complete worker preview, including JPEG draft/decode and waiting), with the **same SHA-256** and **0 differing channels of 2,880,000**. `gpu_used: true`, `gpu_error: null`. This verifies this fixture and exposure/contrast recipe on their hardware, **not** Tk repaint latency, every slider value, every input format, installed-app support or full-resolution export. The probe is repeatable after pulling:

```powershell
.\.venv\Scripts\python.exe scripts\probe_integrated_preview.py
```

It does not display a UI or export a photo. To try the source editor experimentally (not the installed executable), set the environment variable for that PowerShell session and open it:

```powershell
$env:IMAGE_SWITCHER_EXPERIMENTAL_GPU_PREVIEW = '1'
.\.venv\Scripts\python.exe src\editor_app.py
Remove-Item Env:\IMAGE_SWITCHER_EXPERIMENTAL_GPU_PREVIEW
```

The final cleanup command runs after the app exits. Without the variable, even with pyopencl installed, the editor stays CPU-only. LibRaw decode, Pillow resize/codec, Tk canvas and PNG/TIFF writing remain CPU-bound; a small preview can still be slower on GPU due to driver setup. This is not a supported GPU toggle or a full Windows installer feature.

### Original isolated real-device kernel probe (different from integrated preview)

On the user's Windows machine, in this branch after pulling, install the **optional diagnostic-only** dependency into the existing ignored editor venv, then run the generated-pixel benchmark:

```powershell
.\.venv\Scripts\python.exe -m pip install "pyopencl==2026.1.4"
.\.venv\Scripts\python.exe scripts\probe_gpu.py --size 2400x1600
```

This runs a representative exposure+contrast OpenCL kernel on a GPU device (prefer NVIDIA, otherwise another OpenCL GPU; never silently label an OpenCL CPU as accelerated), compares channel-by-channel against the editor's current CPU arithmetic on *generated* RGB pixels, and reports median **host-transfer + kernel + readback** time, kernel-only time, CPU time, output differences and device-reported memory. Nothing is enabled in preview/export by installing the probe; if OpenCL is unavailable or the driver fails it prints `gpu_executed: false` and the editor still runs CPU-only. It does not read photos, print paths, or upload results. The user already ran this and reported the RTX 4070 result above. The next gate is `probe_integrated_preview.py`, **not** a repeat of this isolated math test. A successful kernel probe is **not** 16-bit NEF/ICC/Sharpness parity or packaged Windows compatibility. Do not mark MUH-56 complete until the optional backend and CPU fallback pass integrated hardware checks and full-fidelity comparisons.
