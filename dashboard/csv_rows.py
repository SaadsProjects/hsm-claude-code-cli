"""
CsvReader for the dashboard's bulk upload (unit U4, WF6, BR4.2, NFR1.6).

``read_upload`` reads an uploaded file into the rows ``HsmClient.bulk_add``
sends, or refuses the file locally so nothing is sent (and so nothing is
audited). Cell values are never converted or judged: the backend checks them.
``encoded_bulk_size`` measures the request body exactly as the client will
encode it, so an oversized file never meets the backend's 1 MiB body limit.
No Streamlit import.
"""
import csv
import io
import json
from typing import NamedTuple

# NFR1.6: the largest bulk request body the dashboard sends. The backend reads
# at most 1 MiB (mock_hsm.writes.MAX_BODY_BYTES); this leaves room to spare.
MAX_BULK_BYTES = 960 * 1024

# Placeholder id lengths for measuring a body before the real ids are known:
# secrets.token_urlsafe(32) session ids and uuid4().hex request ids.
SESSION_ID_LENGTH = 43
REQUEST_ID_LENGTH = 32

TOO_LARGE = "The file is too large to upload in one go; split it into smaller files."
NOT_UTF8 = "The file is not UTF-8 text."
EMPTY = "The file is empty."


class ReadResult(NamedTuple):
    """Either ``rows`` (``{row, record}`` or ``{row, parse_error}``, numbered
    from 1) or a local ``refusal`` message, never both."""

    rows: list | None
    refusal: str | None


def _refused(message):
    return ReadResult(None, message)


def read_upload(data, columns):
    """Read an uploaded CSV file (bytes) against the template's ``columns``.

    Refused locally: a raw size over ``MAX_BULK_BYTES`` (before parsing, since
    JSON never makes the body smaller), text that is not UTF-8, an empty file,
    invalid CSV, or a header that does not match ``columns`` (trimmed,
    case-sensitive, in order). Otherwise every record after the header is a
    row numbered from 1; blank records are skipped but keep their numbers,
    and a record with the wrong cell count becomes a ``parse_error`` row."""
    if len(data) > MAX_BULK_BYTES:
        return _refused(TOO_LARGE)
    try:
        text = data.decode("utf-8-sig")  # a leading byte-order mark is ignored
    except UnicodeDecodeError:
        return _refused(NOT_UTF8)
    if not text.strip():
        return _refused(EMPTY)
    # One cell can be as large as the whole file; the csv module's default
    # field limit (128 KiB) would refuse a valid file under MAX_BULK_BYTES.
    # Raising the process-wide limit only ever loosens it.
    csv.field_size_limit(max(csv.field_size_limit(), MAX_BULK_BYTES))
    try:
        # newline="" leaves CR/LF to the csv module, so quoted line breaks and
        # CRLF endings are read as the CSV standard says.
        records = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except csv.Error as e:
        return _refused(f"The file could not be read as CSV: {e}.")
    header, body = records[0], records[1:]
    if [cell.strip() for cell in header] != list(columns):
        return _refused(f"The header must be: {','.join(columns)}.")
    rows = []
    for number, cells in enumerate(body, start=1):
        if not cells:
            continue  # a blank record keeps its number
        if len(cells) != len(columns):
            rows.append({"row": number, "parse_error": f"expected {len(columns)} values, found {len(cells)}"})
        else:
            rows.append({"row": number, "record": dict(zip(columns, cells, strict=True))})
    return ReadResult(rows, None)


def encoded_bulk_size(rows, file_name, session_id=None, request_id=None):
    """Bytes in the bulk request body as ``HsmClient._write`` encodes it
    (``json.dumps`` defaults: non-ASCII is escaped). Ids not yet known are
    measured with placeholders of their real length."""
    body = {"session_id": session_id or "x" * SESSION_ID_LENGTH,
            "request_id": request_id or "x" * REQUEST_ID_LENGTH,
            "source": "csv", "file_name": file_name, "rows": rows}
    return len(json.dumps(body).encode())


def fits(rows, file_name, session_id=None, request_id=None):
    return encoded_bulk_size(rows, file_name, session_id, request_id) <= MAX_BULK_BYTES
