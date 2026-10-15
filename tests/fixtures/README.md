# UI visual smoke fixture

`ui-camera.jpg` is an AI-generated, unbranded, 1536 × 1024 **test image**, created for this repository's still-photo editor visual development. It is not a source photograph, a representation of a Nikon NEF, an ownership claim, a signed credential, or part of the app's shipped photo collection. The Windows CI capture script loads it as two numbered entries to exercise populated, protected and export-dialog states without using personal photos. It is small (~156 KB); do not add large RAW fixtures here.

A capture made with this fixture does **not** close MUH-45: user-approved viewport/DPI and real Windows screenshot review are still required for a visual sign-off. `scripts/capture_editor_baseline.py --photo PATH` can override it later.
