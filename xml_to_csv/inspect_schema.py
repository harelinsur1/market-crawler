"""Report the XML structure (root tag, item tag, header and item fields) of every chain.

Usage:
    python -m xml_to_csv.inspect_schema                 # latest folder under data/
    python -m xml_to_csv.inspect_schema 20261110-1100
"""
import argparse
import os
import sys
from collections import Counter, defaultdict

from .convert import find_xml_files, parse_file, resolve_run_dir


def main(argv=None):
    parser = argparse.ArgumentParser(prog="xml_to_csv.inspect_schema", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run", nargs="?", help="folder name under data/ (default: latest)")
    parser.add_argument("--data", default="data", help="data root (default: data)")
    parser.add_argument("--sample", type=int, default=5,
                        help="files to inspect per chain folder, 0 = all (default: 5)")
    args = parser.parse_args(argv)

    run_dir = resolve_run_dir(args.data, args.run)
    print("inspecting", run_dir)

    by_chain = defaultdict(lambda: {"files": 0, "rows": 0, "roots": Counter(), "items": Counter(),
                                    "header": Counter(), "fields": Counter(), "errors": 0})
    for chain_folder, path in find_xml_files(run_dir):
        info = by_chain[chain_folder]
        if args.sample and info["files"] >= args.sample:
            continue
        info["files"] += 1
        try:
            result = parse_file(path, raw=True)
        except Exception as exc:  # report and continue
            info["errors"] += 1
            print("  ERROR %s: %s" % (path, exc), file=sys.stderr)
            continue
        info["roots"][result.root_tag] += 1
        info["items"][result.item_tag] += 1
        info["header"].update(result.header.keys())
        info["rows"] += len(result.items)
        for item in result.items:
            info["fields"].update(item.keys())

    for chain_folder in sorted(by_chain):
        info = by_chain[chain_folder]
        print("\n== %s  files=%d rows=%d errors=%d" % (chain_folder, info["files"], info["rows"],
                                                      info["errors"]))
        print("   root :", dict(info["roots"]))
        print("   item :", dict(info["items"]))
        print("   header:", sorted(info["header"]))
        print("   fields:", sorted(info["fields"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
