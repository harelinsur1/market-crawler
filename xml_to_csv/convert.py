"""Convert the PriceFull XML files of one crawler run into CSV rows."""
import csv
import os
import re
import xml.etree.ElementTree as ET
from collections import namedtuple

from .schema import KNOWN_TAGS, convert_item

ParseResult = namedtuple("ParseResult", "root_tag item_tag header items")

_RUN_DIR = re.compile(r"^\d{8}-\d{4}$")


def resolve_run_dir(data_root, run=None):
    """data/<run>, or the latest data/<yyyymmdd-HHMM> folder when run is not given."""
    if run:
        path = run if os.path.isdir(run) else os.path.join(data_root, run)
        if not os.path.isdir(path):
            raise SystemExit("folder not found: %s" % path)
        return path
    runs = sorted(name for name in os.listdir(data_root)
                  if _RUN_DIR.match(name) and os.path.isdir(os.path.join(data_root, name)))
    if not runs:
        raise SystemExit("no <yyyymmdd-HHMM> folders in %s" % data_root)
    return os.path.join(data_root, runs[-1])


def find_xml_files(run_dir):
    """Yield (chain_folder, xml_path) for every extracted XML file in the run."""
    for chain_folder in sorted(os.listdir(run_dir)):
        chain_path = os.path.join(run_dir, chain_folder)
        if not os.path.isdir(chain_path):
            continue
        for root, _dirs, files in os.walk(chain_path):
            for name in sorted(files):
                if name.lower().endswith(".xml"):
                    yield chain_folder, os.path.join(root, name)


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def parse_file(path, raw=False):
    """Stream-parse one price file.

    An "item" is any element that has an ItemCode child (case-insensitive); every other leaf
    element is a header field (ChainId, StoreId, ...).
    """
    items = []
    item_tag = None
    root = None
    for event, elem in ET.iterparse(path, events=("start", "end")):
        if root is None:
            root = elem
            continue
        if event != "end" or len(elem) == 0:
            continue
        children = {_local(child.tag): (child.text or "").strip() for child in elem}
        if not any(key.lower() == "itemcode" for key in children):
            continue
        item_tag = _local(elem.tag)
        items.append(children)
        elem.clear()

    header = {}
    for elem in root.iter():
        if elem is root or len(elem) or _local(elem.tag) == item_tag:
            continue
        text = (elem.text or "").strip()
        if text:
            header.setdefault(_local(elem.tag), text)
    return ParseResult(_local(root.tag), item_tag, header, items)


def chain_names(run_dir):
    """Chain folder -> English chain name, from the crawler's file_list.csv when available."""
    names = {}
    list_path = os.path.join(run_dir, "file_list.csv")
    if os.path.isfile(list_path):
        with open(list_path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                folder = os.path.basename(os.path.dirname(row.get("local_path") or ""))
                if folder and row.get("chain"):
                    names.setdefault(folder, row["chain"])
    return names


def folder_chain_name(chain_folder):
    """Fallback: 7290058140886_Rami-Levy -> Rami Levy."""
    return chain_folder.split("_", 1)[-1].replace("-", " ")


def convert_file(job):
    """Worker: parse one XML file. Returns (path, rows, unknown_tags, error)."""
    path, chain, date_inserted = job
    # The extracted folder is named after the downloaded file, e.g. PriceFull...-20261110-0012.gz
    filename = os.path.basename(os.path.dirname(path)).split(".")[0]
    try:
        result = parse_file(path)
    except Exception as exc:
        return path, [], set(), "%s: %s" % (type(exc).__name__, exc)
    unknown = set()
    rows = []
    for item in result.items:
        unknown.update(k for k in item if k.lower() not in KNOWN_TAGS)
        rows.append(convert_item(item, filename, chain, date_inserted))
    return path, rows, unknown, None
