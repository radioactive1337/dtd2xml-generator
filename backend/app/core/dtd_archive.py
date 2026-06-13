"""Extract DTD modules from JAR archives."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

DTD_MODULE_EXTENSIONS = (".dtd", ".ent", ".mod")


def extract_jar_dtd_files(
    jar_bytes: bytes,
    dest_dir: Path,
    prefix: str = "META-INF/dtd/",
) -> dict[str, Path]:
    """Extract DTD-related files from a JAR into *dest_dir* (flat, by basename).

    Returns mapping of basename -> written path.
    Raises ValueError on zip-slip or malformed entry names.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest_dir.resolve()

    prefix_norm = prefix.replace("\\", "/")
    if not prefix_norm.endswith("/"):
        prefix_norm += "/"

    extracted: dict[str, Path] = {}

    with zipfile.ZipFile(io.BytesIO(jar_bytes)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue

            entry_name = info.filename.replace("\\", "/")
            if not entry_name.startswith(prefix_norm):
                continue
            if not entry_name.lower().endswith(DTD_MODULE_EXTENSIONS):
                continue

            relative = entry_name[len(prefix_norm) :]
            if any(part == ".." for part in Path(relative).parts):
                raise ValueError(f"Zip-slip detected: {entry_name}")

            basename = Path(relative).name
            if basename in ("", ".", "..") or "/" in basename or "\\" in basename:
                raise ValueError(f"Invalid entry name: {entry_name}")

            target = (dest_dir / basename).resolve()
            if not str(target).startswith(str(dest_resolved)):
                raise ValueError(f"Zip-slip detected: {entry_name}")

            target.write_bytes(archive.read(info.filename))
            extracted[basename] = target

    return extracted
