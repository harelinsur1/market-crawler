import gzip
import logging
import os
import re
import shutil
import zipfile

from .platforms import RemoteFile

log = logging.getLogger(__name__)
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def safe_name(name: str) -> str:
    """Remote names are untrusted - keep a plain file name with no path parts."""
    cleaned = _UNSAFE.sub("_", os.path.basename(name.replace("\\", "/")))
    return cleaned.lstrip(".") or "unnamed"


def download(remote: RemoteFile, target_dir: str) -> str:
    """Save the file with its platform's download handler. Returns the local path."""
    os.makedirs(target_dir, exist_ok=True)
    path = os.path.join(target_dir, safe_name(remote.name))
    if os.path.exists(path):
        log.debug("exists, skipping %s", path)
        return path
    remote.platform.download(remote, path)
    return path


def extract(path: str) -> str:
    """Extract a downloaded file into a folder named after it (without the extension).

    Price files are gzip (sometimes zip) archives holding one XML file. Returns the folder.
    """
    folder = os.path.splitext(path)[0]
    if os.path.isdir(folder):
        log.debug("exists, skipping %s", folder)
        return folder

    tmp_folder = folder + ".part"
    shutil.rmtree(tmp_folder, ignore_errors=True)
    os.makedirs(tmp_folder)
    xml_name = os.path.basename(folder) + ".xml"
    with open(path, "rb") as fh:
        magic = fh.read(4)

    if magic.startswith(b"\x1f\x8b"):
        with gzip.open(path) as src, open(os.path.join(tmp_folder, xml_name), "wb") as dst:
            shutil.copyfileobj(src, dst)
    elif magic.startswith(b"PK"):
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                target = os.path.join(tmp_folder, safe_name(member.filename))
                with archive.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    elif magic.lstrip(b"\xef\xbb\xbf").startswith(b"<"):  # plain XML, not compressed
        shutil.copyfile(path, os.path.join(tmp_folder, xml_name))
    else:
        shutil.rmtree(tmp_folder, ignore_errors=True)
        raise ValueError("unknown file format %r: %s" % (magic, path))

    os.replace(tmp_folder, folder)
    return folder


def fetch(remote: RemoteFile, target_dir: str) -> str:
    """Download and extract. Returns the folder with the extracted content."""
    return extract(download(remote, target_dir))
