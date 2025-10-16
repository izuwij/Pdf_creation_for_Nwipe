from datetime import datetime


import pytest

from pdf_creation_for_nwipe import NwipeRun, parse_nwipe_log


def test_parse_json_data():
    data = """
    [
        {
            "Device": "/dev/sda",
            "Result": "Success",
            "Passes": "3",
            "Start Time": "2024-01-01 12:00:00",
            "End Time": "2024-01-01 13:00:00"
        }
    ]
    """
    runs = parse_nwipe_log(data)
    assert len(runs) == 1
    run = runs[0]
    assert isinstance(run, NwipeRun)
    assert run.device == "/dev/sda"
    assert run.passes == 3
    assert run.is_successful is True
    assert run.start_time == datetime(2024, 1, 1, 12, 0, 0)
    assert run.end_time == datetime(2024, 1, 1, 13, 0, 0)


def test_parse_key_value_text_handles_multiple_runs():
    log_text = """
    Device: /dev/sdb
    Method: DoD Short
    Result: Failed
    Errors: verify mismatch; write error
    Notes: manual check required

    Device: /dev/sdc
    Method: Quick Wipe
    Result: Success
    Passes: 1
    """
    runs = parse_nwipe_log(log_text)
    assert len(runs) == 2
    first, second = runs
    assert first.device == "/dev/sdb"
    assert first.method == "DoD Short"
    assert first.errors == ["verify mismatch", "write error"]
    assert first.notes == "manual check required"
    assert first.is_successful is False
    assert second.device == "/dev/sdc"
    assert second.passes == 1
    assert second.is_successful is True


def test_parse_sequence_of_mappings():
    runs = parse_nwipe_log([
        {"Device": "/dev/sda", "Result": "Success"},
        {"Device": "/dev/sdb", "Result": "Failed", "Errors": "I/O error"},
    ])
    assert len(runs) == 2
    assert [run.device for run in runs] == ["/dev/sda", "/dev/sdb"]
    assert runs[1].errors == ["I/O error"]
    assert runs[0].extra == {}


def test_parse_file_like_object(tmp_path):
    sample = "Device: /dev/sdz\nResult: Success\n"
    path = tmp_path / "sample.log"
    path.write_text(sample)
    with path.open("r", encoding="utf-8") as handle:
        runs = parse_nwipe_log(handle)
    assert runs[0].device == "/dev/sdz"
