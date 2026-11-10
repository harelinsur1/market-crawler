"""Combine all PriceFull XML files of a crawler run into one CSV.

Usage:
    python -m xml_to_csv                         # latest data/<yyyymmdd-HHMM> folder
    python -m xml_to_csv 20261110-1100           # a specific run folder
    python -m xml_to_csv 20261110-1100 --out D:\\prices.csv --workers 4
"""
import argparse
import csv
import os
import sys
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from multiprocessing import Pool

from .convert import chain_names, convert_file, find_xml_files, folder_chain_name, resolve_run_dir
from .schema import COLUMNS


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="xml_to_csv", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run", nargs="?", help="folder name (or path) under --data (default: latest)")
    parser.add_argument("--data", default="data", help="data root (default: data)")
    parser.add_argument("--out", help="output CSV (default: <run folder>/full_prices_<run>.csv)")
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1,
                        help="parallel parser processes (default: number of CPUs)")
    return parser.parse_args(argv)


def report(start, run_dir, out_path, per_chain, errors, unknown):
    """Print an end-of-run summary: totals and a per-chain-folder breakdown."""
    files = sum(c["files"] for c in per_chain.values())
    rows = sum(c["rows"] for c in per_chain.values())
    size = os.path.getsize(out_path) if os.path.isfile(out_path) else 0
    failed_chains = [name for name, c in per_chain.items() if c["failed"]]
    lines = [
        ("total time", str(timedelta(seconds=round(time.monotonic() - start)))),
        ("run folder", run_dir),
        ("chain folders", "%d (%d with failed files)" % (len(per_chain), len(failed_chains))),
        ("XML files", "%d (%d ok, %d failed)" % (files, files - len(errors), len(errors))),
        ("rows written", "{:,}".format(rows)),
        ("output", "%s (%.1f MB)" % (out_path, size / 1024 / 1024)),
        ("unmapped tags", ", ".join(sorted(unknown)) or "-"),
    ]
    print("\n===== summary =====")
    for label, value in lines:
        print("%-15s %s" % (label + ":", value))

    print("\n%-45s %6s %6s %12s" % ("chain folder", "files", "failed", "rows"))
    for name, c in per_chain.items():
        print("%-45s %6d %6d %12s" % (name, c["files"], c["failed"], "{:,}".format(c["rows"])))

    if errors:
        print("\nfailed files:")
        for path, error in errors:
            print("  %s: %s" % (path, error))


def main(argv=None):
    args = parse_args(argv)
    start = time.monotonic()
    run_dir = resolve_run_dir(args.data, args.run)
    run_name = os.path.basename(os.path.normpath(run_dir))
    out_path = args.out or os.path.join(run_dir, "full_prices_%s.csv" % run_name)

    names = chain_names(run_dir)
    date_inserted = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    found = list(find_xml_files(run_dir))
    jobs = [(path, names.get(folder) or folder_chain_name(folder), date_inserted)
            for folder, path in found]
    folder_of = {path: folder for folder, path in found}
    per_chain = OrderedDict((folder, {"files": 0, "failed": 0, "rows": 0}) for folder, _ in found)
    print("%s: %d XML files -> %s" % (run_dir, len(jobs), out_path))

    rows_total, errors, unknown = 0, [], set()
    tmp_path = out_path + ".part"
    with open(tmp_path, "w", newline="", encoding="utf-8-sig") as fh, \
            Pool(max(1, args.workers)) as pool:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        for done, (path, rows, file_unknown, error) in enumerate(
                pool.imap_unordered(convert_file, jobs, chunksize=4), 1):
            stats = per_chain[folder_of[path]]
            stats["files"] += 1
            stats["rows"] += len(rows)
            if error:
                stats["failed"] += 1
                errors.append((path, error))
                print("  ERROR %s: %s" % (path, error), file=sys.stderr)
            writer.writerows(rows)
            rows_total += len(rows)
            unknown |= file_unknown
            if done % 100 == 0 or done == len(jobs):
                print("  %d/%d files, %d rows" % (done, len(jobs), rows_total))
    os.replace(tmp_path, out_path)

    report(start, run_dir, out_path, per_chain, errors, unknown)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
