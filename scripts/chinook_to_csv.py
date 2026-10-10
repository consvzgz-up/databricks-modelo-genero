"""Extract five Chinook tables from the Postgres dump of pipeline-db-ml into CSV files.

Reads only `INSERT INTO <table> (<cols>) VALUES` blocks (one tuple per line) for the tables
genre, track, invoice_line, invoice and customer, and writes data/<table>.csv with the column
names from the INSERT header. NULL becomes an empty field; strings are kept as they are.

    python scripts/chinook_to_csv.py                 # writes ./data/*.csv
    python scripts/chinook_to_csv.py --self-test     # parse the dump and check the counts

Standard library only.
"""
import argparse
import csv
import io
import os
import re
import sys

sys.dont_write_bytecode = True

TABLES = ("genre", "track", "invoice_line", "invoice", "customer")
EXPECTED = {"genre": 25, "track": 3503, "invoice_line": 2240, "invoice": 412, "customer": 59}

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DUMP = os.path.join(os.path.dirname(REPO), "pipeline-db-ml", "db", "init", "01_chinook.sql")
DEFAULT_OUT = os.path.join(REPO, "data")

HEADER = re.compile(r"^INSERT INTO (\w+) \(([^)]*)\) VALUES\s*$")
NULL = "\x00NULL\x00"  # sentinel, cannot appear in the dump


def normalise(body: str) -> str:
    """Drop the N prefix of N'...' literals and mark bare NULLs, outside quotes only.

    A value starts at the beginning of the body or after a comma (plus spaces). Inside a
    quoted string nothing is touched; '' is an escaped quote and keeps the string open.
    """
    out = []
    i, n = 0, len(body)
    in_quote = False
    at_value_start = True
    while i < n:
        ch = body[i]
        if in_quote:
            out.append(ch)
            if ch == "'":
                if i + 1 < n and body[i + 1] == "'":
                    out.append("'")
                    i += 2
                    continue
                in_quote = False
            i += 1
            continue
        if at_value_start and ch == " ":
            out.append(ch)
            i += 1
            continue
        if at_value_start and ch == "N" and i + 1 < n and body[i + 1] == "'":
            i += 1  # drop the N; the quote is handled on the next pass
            continue
        if at_value_start and body.startswith("NULL", i) and (i + 4 == n or body[i + 4] in ", "):
            out.append(NULL)
            i += 4
            at_value_start = False
            continue
        if ch == "'":
            in_quote = True
            at_value_start = False
        elif ch == ",":
            at_value_start = True
        else:
            at_value_start = False
        out.append(ch)
        i += 1
    if in_quote:
        raise ValueError(f"unterminated string in: {body[:80]}")
    return "".join(out)


def parse_row(line: str):
    s = line.strip()
    if not s.startswith("("):
        raise ValueError(f"not a tuple line: {s[:80]}")
    if not (s.endswith("),") or s.endswith(");")):
        raise ValueError(f"tuple line does not end in ), or );: {s[-40:]}")
    s = s[1:-2]
    fields = next(csv.reader([normalise(s)], quotechar="'", doublequote=True, skipinitialspace=True))
    return [None if f == NULL else f for f in fields]


def parse_dump(path: str):
    """Return {table: (columns, rows)} for the five tables."""
    tables = {t: (None, []) for t in TABLES}
    current = None
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\r\n")
            m = HEADER.match(line)
            if m:
                name = m.group(1)
                current = name if name in tables else None
                if current:
                    cols = [c.strip() for c in m.group(2).split(",")]
                    known = tables[current][0]
                    if known is not None and known != cols:
                        raise ValueError(f"{current}: column list changed between INSERT blocks")
                    tables[current] = (cols, tables[current][1])
                continue
            if current is None:
                continue
            if not line.strip():
                current = None
                continue
            row = parse_row(line)
            cols = tables[current][0]
            if len(row) != len(cols):
                raise ValueError(f"{current}: {len(row)} values for {len(cols)} columns: {line[:80]}")
            tables[current][1].append(row)
            if line.rstrip().endswith(");"):
                current = None
    return tables


def to_csv_text(cols, rows) -> str:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for r in rows:
        w.writerow(["" if v is None else v for v in r])
    return buf.getvalue()


def write_all(tables, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    for t in TABLES:
        cols, rows = tables[t]
        with open(os.path.join(out_dir, f"{t}.csv"), "w", encoding="utf-8", newline="") as fh:
            fh.write(to_csv_text(cols, rows))


def self_test(dump) -> int:
    tables = parse_dump(dump)
    ok = True
    for t in TABLES:
        count = len(tables[t][1])
        good = count == EXPECTED[t]
        ok &= good
        print(f"{t:<13} {count:>5}  {'ok' if good else f'MISMATCH (expected {EXPECTED[t]})'}")

    def row_by_id(table, rid):
        cols, rows = tables[table]
        for r in rows:
            if r[0] == str(rid):
                return dict(zip(cols, r))
        return {}

    checks = [
        ("customer 1 email", row_by_id("customer", 1).get("email"), "luisg@embraer.com.br"),
        ("customer 1 first_name", row_by_id("customer", 1).get("first_name"), "Luís"),
        ("customer 2 company is NULL", row_by_id("customer", 2).get("company"), None),
        ("track 1 name", row_by_id("track", 1).get("name"), "For Those About To Rock (We Salute You)"),
        ("track 2001 name (escaped quote)", row_by_id("track", 2001).get("name"), "Tourette's"),
        ("N and NULL inside strings untouched", parse_row("    (1, N'a, N''b', NULL, 'NULL', 2),"),
         ["1", "a, N'b", None, "NULL", "2"]),
    ]
    for label, got, want in checks:
        good = got == want
        ok &= good
        print(f"{label}: {'ok' if good else f'MISMATCH got {got!r} want {want!r}'}")

    cols, rows = tables["customer"]
    back = list(csv.reader(io.StringIO(to_csv_text(cols, rows))))
    good = back[0] == cols and len(back) == len(rows) + 1 and back[1][cols.index("email")] == "luisg@embraer.com.br"
    ok &= good
    print(f"csv round trip: {'ok' if good else 'MISMATCH'}")

    print("self-test passed" if ok else "self-test FAILED")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dump", default=DEFAULT_DUMP, help="path to 01_chinook.sql")
    ap.add_argument("--out", default=DEFAULT_OUT, help="output directory for the CSVs")
    ap.add_argument("--self-test", action="store_true", help="check the counts and a few known values")
    args = ap.parse_args(argv)
    if not os.path.exists(args.dump):
        print(f"dump not found: {args.dump}", file=sys.stderr)
        return 2
    if args.self_test:
        return self_test(args.dump)
    tables = parse_dump(args.dump)
    write_all(tables, args.out)
    for t in TABLES:
        print(f"{t:<13} {len(tables[t][1]):>5} rows -> {os.path.join(args.out, t + '.csv')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
