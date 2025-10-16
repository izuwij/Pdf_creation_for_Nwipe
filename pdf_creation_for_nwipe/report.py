"""Generate PDF summaries for NWipe execution logs."""
from __future__ import annotations

from datetime import timezone
from pathlib import Path
from typing import List, Mapping, Sequence, Union, Any
import io
import os

from .parser import NwipeRun, parse_nwipe_log


def _normalize_runs(data: Union[str, os.PathLike[str], os.PathLike[bytes], bytes, NwipeRun, Mapping[str, Any], Sequence[Any]]) -> List[NwipeRun]:
    if isinstance(data, NwipeRun):
        return [data]
    if isinstance(data, (str, bytes, os.PathLike)) or hasattr(data, "read"):
        return parse_nwipe_log(data)  # type: ignore[arg-type]
    if isinstance(data, Mapping):
        return [NwipeRun.from_mapping(data)]
    if isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
        runs: List[NwipeRun] = []
        for item in data:
            if isinstance(item, NwipeRun):
                runs.append(item)
            elif isinstance(item, Mapping):
                runs.append(NwipeRun.from_mapping(item))
            else:
                raise TypeError("Unsupported element in run sequence; expected mapping or NwipeRun")
        return runs
    raise TypeError("Unsupported data type for NWipe runs")


def _format_datetime(value):
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).isoformat()
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _append_field(lines: List[str], label: str, value: Any) -> None:
    if value is None:
        return
    text = str(value).strip()
    if not text:
        return
    lines.append(f"{label}: {text}")


def build_report_lines(entries: Union[Sequence[NwipeRun], NwipeRun, Mapping[str, Any], Sequence[Any], str, bytes, os.PathLike[str], os.PathLike[bytes]], *, title: str = "NWipe Report") -> List[str]:
    """Return human-readable lines that summarise NWipe runs."""
    runs = _normalize_runs(entries)
    title = title or "NWipe Report"
    lines: List[str] = [title, "=" * len(title)]
    if not runs:
        lines.append("No NWipe runs were found.")
        return lines
    for idx, run in enumerate(runs, start=1):
        if idx > 1:
            lines.append("")
        heading = f"Run {idx}: {run.device or 'Unknown device'}"
        lines.append(heading)
        lines.append("-" * len(heading))
        _append_field(lines, "Method", run.method)
        _append_field(lines, "Result", run.result)
        if run.passes is not None:
            _append_field(lines, "Passes", run.passes)
        if run.verify_passes is not None:
            _append_field(lines, "Verify passes", run.verify_passes)
        _append_field(lines, "Started", _format_datetime(run.start_time))
        _append_field(lines, "Finished", _format_datetime(run.end_time))
        _append_field(lines, "Duration", run.duration)
        if run.notes:
            lines.append("Notes:")
            lines.append(f"  {run.notes}")
        if run.errors:
            lines.append("Errors:")
            for message in run.errors:
                lines.append(f"  - {message}")
        if run.warnings:
            lines.append("Warnings:")
            for message in run.warnings:
                lines.append(f"  - {message}")
        if run.extra:
            lines.append("Additional information:")
            for key in sorted(run.extra):
                value = run.extra[key]
                if value:
                    lines.append(f"  {key}: {value}")
    return lines


def _escape_pdf_text(text: str) -> str:
    safe_text = text.encode("latin-1", "replace").decode("latin-1")
    return safe_text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_pdf_bytes(lines: Sequence[str]) -> bytes:
    content_lines = ["BT", "/F1 12 Tf", "1 0 0 1 72 750 Tm"]
    first = True
    for line in lines if lines else [""]:
        escaped = _escape_pdf_text(line)
        if first:
            content_lines.append(f"({escaped}) Tj")
            first = False
        else:
            content_lines.append(f"0 -16 Td ({escaped}) Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1")
    buffer = bytearray(b"%PDF-1.4\n")
    offsets = [0]

    def emit(obj_num: int, body: bytes) -> None:
        offsets.append(len(buffer))
        buffer.extend(f"{obj_num} 0 obj\n".encode("ascii"))
        buffer.extend(body)
        buffer.extend(b"\nendobj\n")

    emit(1, b"<< /Type /Catalog /Pages 2 0 R >>")
    emit(2, b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    emit(3, b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 5 0 R /Resources << /Font << /F1 4 0 R >> >> >>")
    emit(4, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    content_body = b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream"
    emit(5, content_body)

    xref_pos = len(buffer)
    buffer.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    buffer.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        buffer.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    buffer.extend(b"trailer\n<< /Size " + str(len(offsets)).encode("ascii") + b" /Root 1 0 R >>\nstartxref\n")
    buffer.extend(str(xref_pos).encode("ascii"))
    buffer.extend(b"\n%%EOF\n")
    return bytes(buffer)


def create_pdf_report(entries: Union[Sequence[NwipeRun], NwipeRun, Mapping[str, Any], Sequence[Any], str, bytes, os.PathLike[str], os.PathLike[bytes]], output: Union[str, os.PathLike[str], os.PathLike[bytes], io.BufferedIOBase, io.RawIOBase, io.BytesIO], *, title: str = "NWipe Report") -> Union[Path, io.BufferedIOBase, io.RawIOBase, io.BytesIO]:
    """Create a PDF file summarising NWipe runs.

    Parameters
    ----------
    entries:
        The NWipe data to report on. Accepts iterables of :class:`NwipeRun`, mappings,
        or textual representations (JSON, CSV, or key/value logs).
    output:
        Either a filesystem path (``str`` or ``Path``) or a binary file-like object.

    Returns
    -------
    Union[Path, io.BufferedIOBase, io.RawIOBase, io.BytesIO]
        The output destination for convenience. For paths the resolved :class:`Path`
        is returned; for file-like objects the original handle is returned.
    """
    runs = _normalize_runs(entries)
    lines = build_report_lines(runs, title=title)
    pdf_bytes = _build_pdf_bytes(lines)

    if hasattr(output, "write"):
        output.write(pdf_bytes)
        if hasattr(output, "flush"):
            output.flush()
        return output

    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pdf_bytes)
    return path


def create_pdf_report_from_log(log_source: Union[str, os.PathLike[str], os.PathLike[bytes], bytes], output: Union[str, os.PathLike[str], os.PathLike[bytes], io.BufferedIOBase, io.RawIOBase, io.BytesIO], *, title: str = "NWipe Report") -> Union[Path, io.BufferedIOBase, io.RawIOBase, io.BytesIO]:
    """Convenience wrapper that parses the log before generating the PDF."""
    runs = parse_nwipe_log(log_source)
    return create_pdf_report(runs, output, title=title)
