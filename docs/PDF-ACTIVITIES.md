# PDF text activity

**Read PDF Text** extracts selectable text from a local `.pdf` file inside the project or an approved file root. The input path is included in the pre-run impact review and file-read audit. Output is a UTF-8 string; form-feed separators (`\f`) preserve page boundaries. A second output variable receives the page count.

The activity can use pypdf's layout-oriented extraction mode when approximate horizontal layout is useful. This does not preserve all visual formatting and is not a table reconstruction feature. The default page limit is 500 and can be configured from 1 through 5,000. Input bytes and extracted text are both limited by the project's configured `maxFileBytes` quota (20 MB by default, with a 100 MB hard cap).

Encrypted PDFs are rejected. The activity does not decrypt documents, execute PDF JavaScript, or perform OCR. Scanned pages and pages containing only images may return no text; use an authorised OCR system for those documents. Malformed PDFs fail with an activity-specific error. Keep the input within an approved project root and avoid processing untrusted documents with unusually complex structures.

Example activity:

```json
{"id":"read-invoice","type":"pdf_read_text","path":"input/invoice.pdf","result":"invoiceText","pageCountResult":"invoicePages","maxPages":100,"layoutMode":false}
```

The browser preview validates PDF activities but cannot access local files; execution requires the desktop filesystem engine.
