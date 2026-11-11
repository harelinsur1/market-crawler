"""Convert the PriceFull XML files of a crawler run into one CSV per chain folder
(data/<run>/<chain folder>/full_prices_<run>.csv).

Usage:
    python -m xml_to_csv                         # latest data/<yyyymmdd-HHMM> folder
    python -m xml_to_csv 20261110-1100           # a specific run folder
    python -m xml_to_csv 20261110-1100 --workers 4
"""
import argparse
import csv
import os
import sys
import time
from collections import Counter, OrderedDict
from datetime import datetime, timedelta
from multiprocessing import Pool

from .convert import chain_names, convert_file, find_xml_files, folder_chain_name, resolve_run_dir
from .schema import COLUMNS


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="xml_to_csv", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run", nargs="?", help="folder name (or path) under --data (default: latest)")
    parser.add_argument("--data", default="data", help="data root (default: data)")
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1,
                        help="parallel parser processes (default: number of CPUs)")
    return parser.parse_args(argv)


def report(start, run_dir, csv_name, per_chain, errors, unknown):
    """Print an end-of-run summary: totals and a per-chain-folder breakdown."""
    files = sum(c["files"] for c in per_chain.values())
    rows = sum(c["rows"] for c in per_chain.values())
    sizes = {}
    for name in per_chain:
        path = os.path.join(run_dir, name, csv_name)
        sizes[name] = os.path.getsize(path) / 1024 / 1024 if os.path.isfile(path) else 0
    failed_chains = [name for name, c in per_chain.items() if c["failed"]]
    lines = [
        ("total time", str(timedelta(seconds=round(time.monotonic() - start)))),
        ("run folder", run_dir),
        ("chain folders", "%d (%d with failed files)" % (len(per_chain), len(failed_chains))),
        ("XML files", "%d (%d ok, %d failed)" % (files, files - len(errors), len(errors))),
        ("rows written", "{:,}".format(rows)),
        ("output", "<chain folder>\\%s (%.1f MB in total)" % (csv_name, sum(sizes.values()))),
        ("unmapped tags", ", ".join(sorted(unknown)) or "-"),
    ]
    print("\n===== summary =====")
    for label, value in lines:
        print("%-15s %s" % (label + ":", value))

    print("\n%-45s %6s %6s %12s %9s" % ("chain folder", "files", "failed", "rows", "MB"))
    for name, c in per_chain.items():
        print("%-45s %6d %6d %12s %9.1f" % (name, c["files"], c["failed"], "{:,}".format(c["rows"]),
                                            sizes[name]))

    if errors:
        print("\nfailed files:")
        for path, error in errors:
            print("  %s: %s" % (path, error))


def main(argv=None):
    args = parse_args(argv)
    start = time.monotonic()
    run_dir = resolve_run_dir(args.data, args.run)
    run_name = os.path.basename(os.path.normpath(run_dir))
    csv_name = "full_prices_%s.csv" % run_name

    names = chain_names(run_dir)
    date_inserted = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    found = list(find_xml_files(run_dir))
    jobs = [(path, names.get(folder) or folder_chain_name(folder), date_inserted)
            for folder, path in found]
    folder_of = {path: folder for folder, path in found}
    per_chain = OrderedDict((folder, {"files": 0, "failed": 0, "rows": 0}) for folder, _ in found)
    remaining = Counter(folder for folder, _ in found)
    print("%s: %d XML files in %d chain folders -> <chain folder>\\%s" % (
        run_dir, len(jobs), len(per_chain), csv_name))

    rows_total, errors, unknown = 0, [], set()
    outputs = {}  # chain folder -> (open .part file, csv writer); closed when its last file is done
    try:
        with Pool(max(1, args.workers)) as pool:
            for done, (path, rows, file_unknown, error) in enumerate(
                    pool.imap_unordered(convert_file, jobs, chunksize=4), 1):
                folder = folder_of[path]
                stats = per_chain[folder]
                stats["files"] += 1
                stats["rows"] += len(rows)
                if error:
                    stats["failed"] += 1
                    errors.append((path, error))
                    print("  ERROR %s: %s" % (path, error), file=sys.stderr)
                if folder not in outputs:
                    fh = open(os.path.join(run_dir, folder, csv_name + ".part"), "w",
                              newline="", encoding="utf-8-sig")
                    outputs[folder] = (fh, csv.writer(fh))
                    outputs[folder][1].writerow(COLUMNS)
                fh, writer = outputs[folder]
                writer.writerows(rows)
                remaining[folder] -= 1
                if remaining[folder] == 0:
                    fh.close()
                    del outputs[folder]
                    os.replace(fh.name, fh.name[:-len(".part")])
                rows_total += len(rows)
                unknown |= file_unknown
                if done % 100 == 0 or done == len(jobs):
                    print("  %d/%d files, %d rows" % (done, len(jobs), rows_total))
    finally:
        for fh, _ in outputs.values():
            fh.close()

    report(start, run_dir, csv_name, per_chain, errors, unknown)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
