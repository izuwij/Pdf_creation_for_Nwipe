# Pdf_creation_for_Nwipe

Utilities for parsing [NWipe](https://github.com/partialresponse/Nwipe) logs and exporting the results to a human readable PDF report.  The tools included in this repository are intentionally lightweight so that they can run in constrained environments without requiring native PDF libraries.

## Features

- Parse NWipe output provided as JSON, CSV or simple key/value text files.
- Normalise the parsed data into `NwipeRun` objects with helpful helpers such as `to_dict()` and `is_successful`.
- Generate summary text for each run that can be used in reports or logs.
- Create single page PDF summaries without external dependencies.

## Quick start

```python
from pdf_creation_for_nwipe import parse_nwipe_log, create_pdf_report

runs = parse_nwipe_log("nwipe.log")
create_pdf_report(runs, "nwipe-report.pdf")
```

The parser accepts a variety of inputs including paths, text strings, dictionaries and lists of dictionaries.  The PDF generator can write to filesystem paths or to any binary file-like object (for example a `io.BytesIO` buffer).

## Development

Run the tests with:

```bash
pytest
```

The project deliberately avoids external dependencies for PDF creation.  If you encounter an NWipe log format that is not handled by the current parser please open an issue or submit a pull request with a reproducible sample.
