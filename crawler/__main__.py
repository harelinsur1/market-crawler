"""Download the latest PriceFull file of every store, published at or before the last 11:00.

Usage:
    python -m crawler                       # all chains, cutoff = last 11:00
    python -m crawler --chains "rami levy" carrefour
    python -m crawler --cutoff "2026-11-09 11:00" --list-only
"""
import argparse
import csv
import logging
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

from .chains import CHAINS, HEBREW_NAMES
from .downloader import fetch, safe_name
from .filename import parse_filename
from .selection import last_cutoff, select_latest

log = logging.getLogger("crawler")
_NON_ALNUM = re.compile(r"[^A-Za-z0-9]+")


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="crawler", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="data", help="output directory (default: data)")
    parser.add_argument("--cutoff", help='cutoff "YYYY-MM-DD HH:MM" (default: last 11:00 local time)')
    parser.add_argument("--cutoff-hour", type=int, default=11, help="hour used for the default cutoff")
    parser.add_argument("--chains", nargs="*", help="only chains whose name contains one of these")
    parser.add_argument("--list-only", action="store_true",
                        help="print selected files and save them to a CSV, do not download")
    parser.add_argument("--list-file",
                        help="CSV path for the file list (default: <out>/<yyyymmdd-HHMM>/file_list.csv)")
    parser.add_argument("--list-chains", action="store_true", help="print configured chains and exit")
    parser.add_argument("--workers", type=int, default=8, help="parallel downloads (default: 8)")
    parser.add_argument("--list-timeout", type=int, default=900,
                        help="max seconds to wait for chain listings (default: 900)")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def pick_chains(filters):
    if not filters:
        return dict(CHAINS)
    wanted = [f.lower() for f in filters]
    return {name: factory for name, factory in CHAINS.items()
            if any(w in name.lower() for w in wanted)}


def list_chain(name, factory, day):
    platform = factory()
    files = platform.list_price_full(day)
    infos = (parse_filename(f.name) for f in files)
    chain_ids = sorted({info.chain_id for info in infos if info is not None})
    log.info("%-20s %-16s %-29s %5d PriceFull files listed",
             name, HEBREW_NAMES.get(name, ""), ",".join(chain_ids) or "-", len(files))
    return files


def chain_folder(chain_id, chain):
    """Folder name for a chain, e.g. 7290058140886_Rami-Levy."""
    return chain_id + "_" + _NON_ALNUM.sub("-", chain).strip("-")


def report(start, chains, failed, listed, selected, downloaded=None, download_errors=0):
    """Print a short end-of-run summary."""
    chains_line = "%d (%d ok, %d failed%s)" % (
        len(chains), len(chains) - len(failed), len(failed),
        (": " + ", ".join(failed)) if failed else "")
    if downloaded is None:
        download_line = "- (--list-only)"
    else:
        download_line = "%d (%d failed)" % (downloaded, download_errors)
    lines = [
        ("total time", str(timedelta(seconds=round(time.monotonic() - start)))),
        ("chains scanned", chains_line),
        ("files listed", str(len(listed))),
        ("stores selected", str(len(selected))),
        ("files downloaded", download_line),
    ]
    print("\n===== summary =====")
    for label, value in lines:
        print("%-18s %s" % (label + ":", value))


def list_all(chains, day, timeout):
    """List every chain in a daemon thread; chains still running after `timeout` are abandoned."""
    results, errors = {}, {}

    def worker(name, factory):
        try:
            results[name] = list_chain(name, factory, day)
        except Exception as exc:  # one broken portal must not stop the others
            errors[name] = exc

    threads = [threading.Thread(target=worker, args=item, daemon=True) for item in chains.items()]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + timeout
    for thread in threads:
        thread.join(max(0.0, deadline - time.monotonic()))

    listed, failed = [], []
    for name in chains:
        if name in results:
            listed.extend(results[name])
        else:
            failed.append(name)
            reason = errors.get(name, "no response within %ds" % timeout)
            log.error("%-45s listing failed: %s", name, reason)
    return listed, failed


def write_list(path, selected, local_paths=None):
    """Write the selected files to CSV; with `local_paths` add a column with the downloaded file."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    header = ["chain", "chain_id", "sub_chain", "store_id", "timestamp", "file_name"]
    if local_paths is not None:
        header.append("local_path")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for remote, info in selected:
            row = [remote.chain, info.chain_id, info.sub_chain, info.store_id,
                   info.timestamp.strftime("%Y-%m-%d %H:%M:%S"), remote.name]
            if local_paths is not None:
                row.append(local_paths.get(id(remote), ""))
            writer.writerow(row)


def main(argv=None):
    start = time.monotonic()
    args = parse_args(sys.argv[1:] if argv is None else argv)
    for stream in (sys.stdout, sys.stderr):  # Hebrew names on non-UTF-8 redirected output
        stream.reconfigure(errors="replace")
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    if args.list_chains:
        print("\n".join(CHAINS))
        return 0

    cutoff = (datetime.strptime(args.cutoff, "%Y-%m-%d %H:%M") if args.cutoff
              else last_cutoff(datetime.now(), args.cutoff_hour))
    chains = pick_chains(args.chains)
    if not chains:
        log.error("no chain matches %s (see --list-chains)", args.chains)
        return 2
    log.info("cutoff: %s, chains: %d", cutoff.strftime("%Y-%m-%d %H:%M"), len(chains))

    # 1. list PriceFull files of every chain (in parallel)
    listed, failed = list_all(chains, cutoff.date(), args.list_timeout)

    # 2. keep the latest file per store at or before the cutoff
    selected = select_latest(listed, cutoff)
    log.info("selected %d stores (latest PriceFull <= %s)", len(selected), cutoff.strftime("%H:%M"))

    base_dir = os.path.join(args.out, cutoff.strftime("%Y%m%d-%H%M"))
    list_file = args.list_file or os.path.join(base_dir, "file_list.csv")

    if args.list_only:
        write_list(list_file, selected)
        log.info("file list saved to %s", list_file)
        report(start, chains, failed, listed, selected)
        return 0

    # 3. download into <out>/<cutoff>/<chain id>_<chain name>/ and extract each file into a
    #    folder named after it
    ok = errors = 0
    local_paths = {}  # id(remote) -> downloaded file path, only for successful downloads
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {}
        for remote, info in selected:
            target_dir = os.path.join(base_dir, chain_folder(info.chain_id, remote.chain))
            futures[pool.submit(fetch, remote, target_dir)] = (remote, target_dir)
        for future in as_completed(futures):
            remote, target_dir = futures[future]
            try:
                log.debug("saved %s", future.result())
                local_paths[id(remote)] = os.path.join(target_dir, safe_name(remote.name))
                ok += 1
            except Exception as exc:
                errors += 1
                log.error("download failed %s (%s): %s", remote.name, remote.chain, exc)

    write_list(list_file, selected, local_paths)
    log.info("file list saved to %s", list_file)

    report(start, chains, failed, listed, selected, ok, errors)
    return 1 if errors or failed else 0


if __name__ == "__main__":
    sys.exit(main())
