import io

from pdf_creation_for_nwipe import build_report_lines, create_pdf_report, parse_nwipe_log


SAMPLE_LOG = """
Device: /dev/sda
Result: Success
Passes: 3
Method: Quick Wipe

Device: /dev/sdb
Result: Failed
Errors: verification failed, disk timeout
Notes: Requires manual inspection
"""


def test_build_report_lines_uses_custom_title():
    runs = parse_nwipe_log(SAMPLE_LOG)
    lines = build_report_lines(runs, title="Custom NWipe Report")
    assert lines[0] == "Custom NWipe Report"
    assert any("Run 1" in line for line in lines)
    assert not any("Additional information:" in line for line in lines)


def test_create_pdf_report_to_bytes_io():
    runs = parse_nwipe_log(SAMPLE_LOG)
    buffer = io.BytesIO()
    result = create_pdf_report(runs, buffer, title="Buffer Report")
    assert result is buffer
    pdf_bytes = buffer.getvalue()
    assert pdf_bytes.startswith(b"%PDF-")
    assert b"Buffer Report" in pdf_bytes


def test_create_pdf_report_to_path(tmp_path):
    runs = parse_nwipe_log(SAMPLE_LOG)
    output = tmp_path / "nwipe.pdf"
    result = create_pdf_report(runs, output)
    assert result == output
    data = output.read_bytes()
    assert data.startswith(b"%PDF-")
    assert b"NWipe Report" in data
