# Excel workbook activities

Open RPA Studio provides `xlsx_read` and `xlsx_write` for local `.xlsx` workbooks. They run in the desktop Python engine, use `openpyxl` with its `defusedxml` hardened parser, resolve paths beneath the project's approved file roots, and are recorded in the normal file audit history. The isolated browser preview has no filesystem access and reports this limitation at run time.

## Read a worksheet

`xlsx_read` reads one worksheet as a list of dictionaries:

```json
{
  "id": "read-orders",
  "type": "xlsx_read",
  "path": "input/orders.xlsx",
  "sheetName": "Orders",
  "headerRow": 1,
  "dataOnly": true,
  "result": "orders"
}
```

`headerRow` is one-based. Header cells must be non-empty and unique. Blank data rows are skipped. Dates and times are returned as ISO 8601 text. With `dataOnly: true` (the default), formula cells return the cached result saved by the workbook's last calculation; that value may be missing or stale if Excel has not recalculated the file. Set `dataOnly` to false to read formula text.

## Write a workbook

`xlsx_write` creates a new workbook from an array of records:

```json
{
  "id": "write-orders",
  "type": "xlsx_write",
  "path": "output/orders.xlsx",
  "sheetName": "Orders",
  "rows": "orders",
  "fields": ["order_id", "amount"]
}
```

If `fields` is omitted, column order follows first appearance across the input records. An explicit field list sets column order; records with keys absent from `fields` fail rather than silently losing data. Cell values must be scalar. Strings beginning with `=` are stored as literal text, not formulas. The activity creates a new workbook and does not edit or append to an existing workbook.

## Limits and compatibility

- `.xlsx` only. Legacy `.xls`, macro-enabled `.xlsm`, password-protected workbooks, macros, and preservation of pivot tables, charts, external links, formatting, or embedded objects are not supported.
- A read is limited by the project's `maxFileBytes`, at most 100,000 non-empty rows, 2,000 columns, and two million data cells. XLSX ZIP archives are checked for entry count and expanded size before parsing.
- A write is limited by `maxFileBytes`, 100,000 records, 2,000 columns, and two million cells. Output is serialized before an atomic file replacement.
- Cancellation is checked during row processing. A currently executing XLSX serialization or XML parser operation is not preempted mid-call.
- Browser preview can validate and save these activity definitions but cannot execute them because it has no local filesystem permission or spreadsheet runtime.

The Python engine tests exercise a real workbook round trip, formula-like literal text, worksheet selection, non-default header rows, audit entries, archive expansion limits, malformed settings, DTD/entity-declaration rejection before XML parsing, and the hardened parser runtime. The packaged bridge acceptance fixture verifies that the frozen desktop runtime includes the spreadsheet dependency.
