"""Load the full_prices CSVs (output of xml_to_csv) into SQL Server as an SCD type 2 table.

One chain at a time: BULK INSERT the chain's CSV (data/<run>/<chain folder>/full_prices_<run>.csv)
into a staging table, merge it into the target (one transaction per chain id) and drop the
staging table before the next chain. Changed items get a new version, removed items are closed,
unchanged items are not touched. Re-running the same CSVs is a no-op, so a failed run can be
started again.

Usage:
    python -m csv_to_sql                                   # latest data/<run>/*/full_prices_<run>.csv
    python -m csv_to_sql 20261110-1100                     # a specific run folder
    python -m csv_to_sql D:\\prices.csv --server localhost\\SQLEXPRESS
    python -m csv_to_sql --method odbc                     # if SQL Server cannot read the file
"""
import argparse
import csv
import glob
import os
import sys
import time
from collections import OrderedDict
from datetime import datetime, timedelta

import pyodbc

from xml_to_csv.convert import resolve_run_dir
from xml_to_csv.schema import COLUMNS

from . import scd

PROD_SERVER = r"PCH80041449\MSSQLSERVER01"


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="csv_to_sql", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", nargs="?",
                        help="CSV path, or run folder under --data (default: latest run)")
    parser.add_argument("--data", default="data", help="data root (default: data)")
    parser.add_argument("--server", default=PROD_SERVER, help="SQL Server (default: %s)" % PROD_SERVER)
    parser.add_argument("--database", default="cpi", help="database (default: cpi)")
    parser.add_argument("--schema", default="dbo", help="schema (default: dbo)")
    parser.add_argument("--table", default="foodChainPricesScd",
                        help="SCD table (default: foodChainPricesScd)")
    parser.add_argument("--driver", default="ODBC Driver 17 for SQL Server", help="ODBC driver")
    parser.add_argument("--method", choices=["bulk", "odbc"], default="bulk",
                        help="bulk = server-side BULK INSERT (fastest), "
                             "odbc = stream from this machine with fast_executemany (default: bulk)")
    parser.add_argument("--batch-size", type=int, default=100000,
                        help="rows per batch for --method odbc (default: 100000)")
    parser.add_argument("--keep-staging", action="store_true",
                        help="keep the <table>_upload staging table of the last chain")
    return parser.parse_args(argv)


def resolve_csvs(source, data_root):
    """[CSV path], or every <chain folder>/full_prices_<run>.csv of a run folder."""
    if source and os.path.isfile(source):
        return [os.path.abspath(source)]
    run_dir = resolve_run_dir(data_root, source)
    run_name = os.path.basename(os.path.normpath(run_dir))
    paths = sorted(glob.glob(os.path.join(glob.escape(run_dir), "*", "full_prices_%s.csv" % run_name)))
    if not paths:
        raise SystemExit("no <chain folder>\\full_prices_%s.csv in %s (run python -m xml_to_csv first)"
                         % (run_name, run_dir))
    return [os.path.abspath(path) for path in paths]


def group_by_chain(paths):
    """Chain id (folder prefix) -> CSVs. Folders with the same chain id (7290055700007_Carrefour,
    7290055700007_Keshet-Teamim) are loaded together, so no store is merged twice in one run."""
    groups = OrderedDict()
    for path in paths:
        folder = os.path.basename(os.path.dirname(path))
        groups.setdefault(folder.split("_", 1)[0], []).append(path)
    return groups


def read_date_inserted(csv_path):
    """valid-from of this load = DateInserted of the CSV (one value per xml_to_csv run);
    None when the CSV has no rows (every file of the chain failed)."""
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        scd.check_header(next(reader, None), csv_path)
        row = next(reader, None)
    if row is None:
        return None
    return datetime.strptime(row[COLUMNS.index("DateInserted")], "%Y-%m-%d %H:%M:%S")


def step(label):
    print("%s..." % label, end=" ", flush=True)
    return time.monotonic()


def done(start, extra=""):
    print("done in %.1f seconds%s" % (time.monotonic() - start, extra))


def main(argv=None):
    args = parse_args(argv)
    start = time.monotonic()
    groups = group_by_chain(resolve_csvs(args.source, args.data))
    paths = [path for chain_paths in groups.values() for path in chain_paths]
    target = scd.quote_name(args.database, args.schema, args.table)
    staging = scd.quote_name(args.database, args.schema, args.table + "_upload")
    print("%d CSV files, %d chains (%.1f MB) -> %s on %s" % (
        len(paths), len(groups), sum(os.path.getsize(p) for p in paths) / 1024 / 1024,
        target, args.server))

    con = pyodbc.connect(driver=args.driver, server=args.server, database=args.database,
                         trusted_connection="yes", autocommit=False)
    cursor = con.cursor()

    t = step("validating destination")
    scd.create_target(cursor, target, args.table)
    con.commit()
    last = cursor.execute("SELECT MAX(validfrom) FROM %s" % target).fetchone()[0]
    done(t)

    print("\n%-15s %12s %10s %10s %10s %12s %8s" % (
        "chain id", "rows", "new", "changed", "removed", "unchanged", "seconds"))
    loaded, totals, bad_files, empty = 0, [0, 0, 0, 0], [], []
    for key, chain_paths in groups.items():
        t = time.monotonic()
        dates = {read_date_inserted(path) for path in chain_paths} - {None}
        if not dates:
            empty.append(key)
            continue
        if len(dates) > 1:
            raise SystemExit("\ndifferent DateInserted values in %s" % ", ".join(chain_paths))
        valid_from = dates.pop()
        if last is not None and last > valid_from:
            raise SystemExit("\n%s already has a newer load (%s); loading an older CSV would corrupt "
                             "the history" % (target, last))

        scd.create_staging(cursor, staging)
        for path in chain_paths:
            if args.method == "bulk":
                try:
                    scd.bulk_insert(cursor, staging, path)
                except pyodbc.Error as error:
                    raise SystemExit("\nBULK INSERT failed: %s\nThe SQL Server service account must be "
                                     "able to read the file; otherwise use --method odbc" % error)
            else:
                scd.odbc_insert(cursor, staging, path, args.batch_size,
                                lambda n: print("\r%-15s %12s" % (key, "{:,}".format(n)), end="", flush=True))
        con.commit()
        loaded += cursor.execute("SELECT COUNT_BIG(*) FROM %s" % staging).fetchone()[0]
        scd.index_staging(cursor, staging)
        bad_files += scd.load_files(cursor, staging)
        con.commit()

        counts = [0, 0, 0, 0]
        chain_ids = [row[0] for row in cursor.execute("SELECT DISTINCT chainid FROM #files ORDER BY chainid")]
        for chain_id in chain_ids:
            source, changed, removed, inserted = scd.merge_chain(cursor, target, staging, chain_id, valid_from)
            con.commit()
            counts = [a + b for a, b in zip(counts, [source, inserted - changed, changed, removed])]
        cursor.execute("DROP TABLE #files")
        if not args.keep_staging:
            cursor.execute("DROP TABLE %s" % staging)
        con.commit()

        totals = [a + b for a, b in zip(totals, counts)]
        print("\r%-15s %12s %10s %10s %10s %12s %8.1f" % (
            key, *("{:,}".format(n) for n in counts + [counts[0] - counts[1] - counts[2]]),
            time.monotonic() - t))
    con.close()

    print("\n===== summary =====")
    for label, value in [
        ("total time", str(timedelta(seconds=round(time.monotonic() - start)))),
        ("rows loaded", "{:,}".format(loaded)),
        ("rows merged", "{:,} (after removing duplicate / non-numeric item codes)".format(totals[0])),
        ("new", "{:,}".format(totals[1])),
        ("changed", "{:,}".format(totals[2])),
        ("removed", "{:,}".format(totals[3])),
        ("empty CSVs", ", ".join(empty) or "-"),
        ("bad filenames", ", ".join(bad_files) or "-"),
    ]:
        print("%-15s %s" % (label + ":", value))
    return 0


if __name__ == "__main__":
    sys.exit(main())
