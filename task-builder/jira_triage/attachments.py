import bz2
import gzip
import lzma
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import httpx

from .schemas import DownloadedAttachment


_SKIP_TOP_TYPES = {"image", "video"}
_TEXT_MIMES = frozenset({
    "application/json",
    "application/xml",
    "application/javascript",
    "application/x-sh",
})
MAX_TEXT_BYTES = 51200


def download_attachments(
    raw_attachments: list[dict],
    dest_dir: Path,
    auth: tuple[str, str],
) -> list[DownloadedAttachment]:
    downloaded = []
    for att in raw_attachments:
        filename = att.get("filename") or ""
        mime = att.get("mimeType") or "application/octet-stream"
        size = att.get("size") or 0
        url = att.get("content") or ""

        if mime.split("/")[0] in _SKIP_TOP_TYPES:
            print(f"    Skipping  (image/video): {filename}", file=sys.stderr)
            continue

        print(f"    Downloading: {filename}", file=sys.stderr)
        resp = httpx.get(url, auth=auth, follow_redirects=True)
        resp.raise_for_status()
        (dest_dir / filename).write_bytes(resp.content)

        downloaded.append(DownloadedAttachment(
            filename=filename,
            mimeType=mime,
            size=size,
            localPath=f"attachments/{filename}",
        ))

    return downloaded


def _decompress(src: Path, dest_dir: Path) -> bool:
    name = src.name
    dest_dir.mkdir(parents=True, exist_ok=True)

    if name.endswith((".tar.gz", ".tgz")):
        with tarfile.open(src, "r:gz") as tf:
            tf.extractall(dest_dir)
    elif name.endswith((".tar.bz2", ".tbz2")):
        with tarfile.open(src, "r:bz2") as tf:
            tf.extractall(dest_dir)
    elif name.endswith((".tar.xz", ".txz")):
        with tarfile.open(src, "r:xz") as tf:
            tf.extractall(dest_dir)
    elif name.endswith(".tar"):
        with tarfile.open(src, "r") as tf:
            tf.extractall(dest_dir)
    elif name.endswith(".gz"):
        with gzip.open(src) as f:
            (dest_dir / name[:-3]).write_bytes(f.read())
    elif name.endswith(".bz2"):
        with bz2.open(src) as f:
            (dest_dir / name[:-4]).write_bytes(f.read())
    elif name.endswith(".xz"):
        with lzma.open(src) as f:
            (dest_dir / name[:-3]).write_bytes(f.read())
    elif name.endswith(".zip"):
        with zipfile.ZipFile(src) as zf:
            zf.extractall(dest_dir)
    else:
        return False

    return True


def decompress_all(attachments_dir: Path, extracted_dir: Path) -> None:
    if not attachments_dir.is_dir():
        return
    for f in attachments_dir.iterdir():
        if not f.is_file():
            continue
        try:
            _decompress(f, extracted_dir / f.name)
        except Exception as e:
            print(f"    Warning: could not decompress {f.name}: {e}", file=sys.stderr)


def _mime_is_text(mime: str) -> bool:
    return mime.split("/")[0] == "text" or mime in _TEXT_MIMES


def collect_text_files(search_dir: Path, strip_prefix: Path) -> list[dict]:
    if not search_dir.is_dir():
        return []

    results = []
    # Sorted for deterministic ordering; matches find's typical alphabetical output.
    for filepath in sorted(search_dir.rglob("*")):
        if not filepath.is_file():
            continue
        # Enforce maxdepth 5 relative to search_dir.
        if len(filepath.relative_to(search_dir).parts) > 5:
            continue

        try:
            mime = subprocess.run(
                ["file", "--mime-type", "-b", str(filepath)],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        except Exception:
            mime = "application/octet-stream"

        if not _mime_is_text(mime):
            continue

        label = str(filepath.relative_to(strip_prefix))
        size = filepath.stat().st_size
        raw = filepath.read_bytes()[:MAX_TEXT_BYTES]
        content = raw.decode("utf-8", errors="replace")
        if size > MAX_TEXT_BYTES:
            content += f"\n[... truncated — showing first {MAX_TEXT_BYTES} of {size} bytes ...]"

        results.append({"filename": label, "content": content})

    return results
