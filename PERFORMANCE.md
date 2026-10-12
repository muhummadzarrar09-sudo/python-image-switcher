# Editor performance work — alpha.7 (MUH-55 / MUH-56)

## What is now faster

- The canvas preview decodes only up to the visible canvas size (JPEG decoder draft when applicable). A 100% source view is **not** claimed; full-resolution master export still decodes/renders the original.
- Sliders debounce by 75 ms, then a single background worker coalesces pending renders. Old results cannot overwrite a newer photo/setting/size. Only Pillow/NumPy work happens on that worker; `ImageTk.PhotoImage`, status and canvas changes remain on Tk's UI thread. The worker has one pending request and one completed image at most.
- Alpha.6 keeps **at most 48 numbered thumbnail tiles** mounted in the rail, with explicit previous/next pages while all photos and protected edits remain in the batch. It decodes rail images at thumbnail size; changing pages may need to decode again after eviction from the **192-image LRU**. Import queues at most 24 decoded-file results ahead of the UI, rather than retaining hundreds of pending Pillow images. This bounds widget and pending-decode memory but is not a measured 400+ real-photo guarantee; profiling pagination, queue throughput and peak RSS remains part of MUH-55.
- Unedited full-resolution renders skip RGB float conversion entirely; adjusted renders reuse float buffers for quantization and Sharpness. Untouched originals and `.isphoto` files are unchanged. Pixel hashes for the four tested 8-bit JPEG recipes (default, exposure/contrast, Sharpness, mixed controls) matched the pre-change implementation; other cameras/RAW require verification.

## Repeatable diagnostic

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_editor.py --size 2400x1600
```

For an **over-400-photo** import/UI/RAM diagnostic on Windows 11, with no personal pictures and bounded temporary generated files, run:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_large_batch.py --count 421
```

It reports import duration, process peak RSS, queue depth, mounted thumbnail tiles and boot GPU readiness. On the user's **15.7 GiB Windows 11 laptop**, 421 generated 1600×1200 JPG paths imported in **3.45 s** with **249.8 MiB peak process RSS**, a full **24/24** pending-result queue, **37/48** mounted tiles on the last page and **192/192** thumbnail cache; the source-checkout probe reported `GPU ready: NVIDIA GeForce RTX 4070 Laptop GPU`. This establishes the generated-fixture import/rail bound on that machine, **not** GPU execution during import. Separate paths hardlink the same image bytes, so this does **not** reproduce 421 distinct camera JPG/NEF files, varied disk reads, export memory, Tk p95 responsiveness, or real-photo sign-off. The UI remains operable during the run; keep the window open until its JSON prints. Real-camera and installed-app measurements remain open.

The full-resolution diagnostic above creates a temporary 3.84 MP JPG from the checked-in AI test image. Separate processes measure first full-size CPU render time and **process** peak resident memory; the JSON explicitly says `gpu_used: false`. Windows CI uploads `benchmark.json` next to the UI capture. These numbers exclude Tk latency, repeated batch edits, PNG/TIFF encoding, and actual NEF decode. On one Linux sandbox run, *before → after*: identity ~0.229 s / 205 MiB → ~0.035 s / 81 MiB; exposure/contrast/Sharpness ~0.371 s / 294 MiB → ~0.228 s / 210 MiB. Different CPUs, RAM, image data, drivers and cache temperatures will vary; compare on the same machine with the same input. The critical follow-up is real Windows p50/p95 latency and RSS with 20/100/500 images.

## GPU: automatic at app startup, still not full-editor/export acceleration

The user's Windows 11 report: **15.7 GiB RAM**, Intel Iris Xe (`32.0.101.6790`) and RTX 4070 Laptop (`32.0.16.1692`). WMI-reported 2/4 GiB adapter RAM was inaccurate for the RTX: OpenCL on the actual laptop reports **8 GiB**, driver `616.92`. The user's generated-pixel 2400×1600 OpenCL exposure+contrast probe measured CPU **0.08767 s** versus GPU transfer+kernel+readback **0.00275 s**, with **0 differing channels out of 11,520,000**. That ~32× *isolated math* result is not a prediction for full UI speed, RAW decode or export. PyOpenCL emitted a non-fatal compiler-output warning; repeated-kernel-retrieval overhead in the probe has been fixed.

Alpha.7 **starts GPU capability detection at boot in a background thread**; Tk and CPU previews are not blocked while an OpenCL context compiles. The Windows updater best-effort installs the optional pyopencl wheel and the packaged editor bundles it if available; a missing wheel, ICD, GPU or driver failure leaves the app running on CPU. `IMAGE_SWITCHER_GPU=off` is an explicit troubleshooting override. The numbered rail shows `GPU ready: …`, `checking`, or `CPU fallback`, while the selected image says `experimental GPU` **only when that render used it**. The GPU handles canvas-size, 8-bit RGB **exposure and/or contrast only**. Sharpness, backgrounds, crop/rotation, alpha, NEF and unsupported settings run on CPU. In alpha.7, a batch export of 8-bit **RGB exposure/contrast-only** photos may also run its **full-resolution color math on the GPU** (not just the selected preview). Before the first master for each recipe, it checks **all 256 possible 8-bit channel inputs** for exact CPU/GPU equality; a mismatch, device failure or unsupported recipe re-renders the entire photo on CPU, never a partial GPU result. The worker processes one photo at a time and copies GPU data in 1-million-pixel tiles to bound VRAM; original bytes, protected numbers, ICC and portable projects use the established paths. PNG/TIFF encoding, NEF/16-bit processing, Sharpness and other controls stay CPU. The user has **not yet verified this new installed alpha.7 batch-export GPU path on the RTX 4070**. Neither boot detection nor an isolated-preview benchmark proves 400-photo export throughput or low peak RAM. MUH-56 stays open for packaged device execution, varied settings/formats, 16-bit fidelity and failure validation.

To check the new **full-resolution batch math** (not files/encoding) on the real GPU without private photos:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_gpu_batch.py --count 20 --size 2400x1600
```

The JSON says how many numbered images actually used GPU, median and total CPU-vs-GPU **full-resolution render** times, process peak RAM and whether every decoded pixel hash matched. CPU/GPU passes run sequentially in one process; caching, heat and throttling can affect timings. A CPU-only PC exits with a diagnostic, not a blocked editor. For the **installed** executable use the generated `--gpu-report` in `BUILD.md` after in-place updating alpha.7; it now also verifies one numbered PNG master and reports actual export GPU execution. Neither check measures 400 different real photos, TIFF/NEF, Tk slider p95 or PNG/.isphoto writing speed.

The user ran `scripts/probe_integrated_preview.py` on their RTX 4070 laptop at a 1200×800 preview size: **CPU median 0.03448 s → GPU opt-in median 0.01564 s** (about **2.2×** faster for this complete worker preview, including JPEG draft/decode and waiting), with the **same SHA-256** and **0 differing channels of 2,880,000**. `gpu_used: true`, `gpu_error: null`. This verifies this fixture and exposure/contrast recipe on their hardware, **not** Tk repaint latency, every slider value, every input format, installed-app support or full-resolution export. The probe is repeatable after pulling:

```powershell
.\.venv\Scripts\python.exe scripts\probe_integrated_preview.py
```

It does not display a UI or export a photo. Alpha.6 no longer requires an opt-in variable: startup attempts GPU readiness automatically in both the source and installed editor if pyopencl is available. For driver troubleshooting only, launch a **single** CPU-only process from PowerShell with `$env:IMAGE_SWITCHER_GPU = 'off'` before starting the editor, then `Remove-Item Env:\IMAGE_SWITCHER_GPU` afterward. The status label distinguishes a GPU-ready device from a CPU fallback and identifies actual accelerated previews separately. LibRaw decode, Pillow resize/codec, Tk canvas and PNG/TIFF writing remain CPU-bound; a small preview can still be slower on GPU due to driver setup. Optional GPU packaging on the user's laptop still requires in-place update and manual validation.

### Original isolated real-device kernel probe (different from integrated preview)

On the user's Windows machine, in this branch after pulling, install the **optional diagnostic-only** dependency into the existing ignored editor venv, then run the generated-pixel benchmark:

```powershell
.\.venv\Scripts\python.exe -m pip install "pyopencl==2026.1.4"
.\.venv\Scripts\python.exe scripts\probe_gpu.py --size 2400x1600
```

This runs a representative exposure+contrast OpenCL kernel on a GPU device (prefer NVIDIA, otherwise another OpenCL GPU; never silently label an OpenCL CPU as accelerated), compares channel-by-channel against the editor's current CPU arithmetic on *generated* RGB pixels, and reports median **host-transfer + kernel + readback** time, kernel-only time, CPU time, output differences and device-reported memory. Nothing is enabled in preview/export by installing the probe; if OpenCL is unavailable or the driver fails it prints `gpu_executed: false` and the editor still runs CPU-only. It does not read photos, print paths, or upload results. The user already ran this and the integrated source-preview probe, with results above. The next GPU gate is the **installed executable's generated `--gpu-report`** described in `BUILD.md`, not another isolated math probe. A successful kernel probe is **not** 16-bit NEF/ICC/Sharpness parity or packaged Windows compatibility. Do not mark MUH-56 complete until the optional backend and CPU fallback pass integrated hardware checks and full-fidelity comparisons.
