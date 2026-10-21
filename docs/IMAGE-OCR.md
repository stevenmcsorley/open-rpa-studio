# Local image OCR activity

**OCR Image** extracts text from a local PNG, JPEG or BMP with the Tesseract executable. It does not send the image to an AI provider or any network service. The input path is checked against the project's approved file roots and both the file read and OCR attempt are written to the local audit history. Recognized text is kept in the workflow result, not copied into the audit log.

OCR is optional. Install the Python image preflight dependency with `uv sync --extra ocr`, and install Tesseract separately using the operating system's trusted package manager. Studio checks for both at launch and reports the runtime version and availability. The Windows installer includes the optional Pillow dependency but does not bundle Tesseract or its language data.

The activity accepts one image with at most 30 megapixels and the project `maxFileBytes` input limit. OCR time is bounded from 1 to 300 seconds; output is bounded by the same project byte limit. It checks cancellation while the local OCR process runs and terminates the process when cancelled or over quota. Language names are restricted to Tesseract identifier characters, and the activity uses an argument array without a shell. Only the installed language packs are available. Page segmentation mode is passed through as an integer from 0 to 13.

The browser preview can save and validate an OCR activity but cannot read local images; execution requires the desktop engine. Tesseract and image decoder versions affect recognition, so OCR output is not guaranteed to be bit-for-bit deterministic across different installations. Use the recognized output as untrusted input and validate it before consequential actions.

Example:

```json
{"id":"read-label","type":"image_ocr","path":"scans/label.png","language":"eng","pageSegmentationMode":6,"timeoutSeconds":30,"result":"labelText"}
```
