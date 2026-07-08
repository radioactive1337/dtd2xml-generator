"""Helpers to resolve and download DTD JARs from Nexus Maven repositories."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from urllib.parse import quote

import httpx

from app.config import NexusDtdConfig


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def _group_path(group_id: str) -> str:
    segments = [quote(segment, safe="") for segment in group_id.split(".") if segment]
    if not segments:
        raise ValueError("nexus_dtd.group_id is required")
    return "/".join(segments)


def _artifact_path(cfg: NexusDtdConfig) -> str:
    group_path = _group_path(cfg.group_id.strip())
    artifact = quote(cfg.artifact_id.strip(), safe="")
    if not artifact:
        raise ValueError("nexus_dtd.artifact_id is required")
    repository = quote(cfg.repository.strip(), safe="")
    if not repository:
        raise ValueError("nexus_dtd.repository is required")
    return f"/repository/{repository}/{group_path}/{artifact}"


def _is_snapshot_version(version: str) -> bool:
    return version.upper().endswith("-SNAPSHOT")


def _resolve_latest_version(metadata_xml: str) -> str:
    root = ET.fromstring(metadata_xml)
    versioning = root.find("versioning")
    if versioning is None:
        raise ValueError("Invalid maven-metadata.xml: missing <versioning>")
    release = (versioning.findtext("release") or "").strip()
    latest = (versioning.findtext("latest") or "").strip()
    resolved = release or latest
    if not resolved:
        raise ValueError(
            "maven-metadata.xml does not contain <release> or <latest> version"
        )
    return resolved


def _resolve_snapshot_jar_basename(metadata_xml: str, artifact_id: str) -> str:
    """Resolve timestamped SNAPSHOT jar filename from version-level metadata."""
    root = ET.fromstring(metadata_xml)
    versioning = root.find("versioning")
    if versioning is None:
        raise ValueError("Invalid snapshot maven-metadata.xml: missing <versioning>")

    snapshot_versions = versioning.find("snapshotVersions")
    if snapshot_versions is not None:
        jar_values: list[str] = []
        for snapshot_version in snapshot_versions.findall("snapshotVersion"):
            extension = (snapshot_version.findtext("extension") or "").strip()
            value = (snapshot_version.findtext("value") or "").strip()
            if extension == "jar" and value:
                jar_values.append(value)
        if jar_values:
            return f"{artifact_id}-{jar_values[-1]}.jar"

    snapshot = versioning.find("snapshot")
    if snapshot is not None:
        timestamp = (snapshot.findtext("timestamp") or "").strip()
        build_number = (snapshot.findtext("buildNumber") or "").strip()
        version_text = (root.findtext("version") or "").strip()
        if timestamp and build_number and version_text:
            base_version = version_text[: -len("-SNAPSHOT")]
            return f"{artifact_id}-{base_version}-{timestamp}-{build_number}.jar"

    raise ValueError("Unable to resolve SNAPSHOT jar filename from maven-metadata.xml")


def _release_jar_basename(artifact_id: str, version: str) -> str:
    return f"{artifact_id}-{version}.jar"


async def _fetch_text(client: httpx.AsyncClient, url: str) -> str:
    response = await client.get(url, timeout=30.0)
    response.raise_for_status()
    return response.text


async def resolve_jar_url(cfg: NexusDtdConfig) -> tuple[str, str]:
    """Build artifact JAR URL and resolved version."""
    base_url = _normalize_base_url(cfg.base_url.strip())
    if not base_url:
        raise ValueError("nexus_dtd.base_url is required")

    artifact_path = _artifact_path(cfg)
    artifact = cfg.artifact_id.strip()
    configured_version = cfg.version.strip() or "LATEST"

    async with httpx.AsyncClient() as client:
        if configured_version.upper() == "LATEST":
            metadata_url = f"{base_url}{artifact_path}/maven-metadata.xml"
            version = _resolve_latest_version(await _fetch_text(client, metadata_url))
        else:
            version = configured_version

        version_part = quote(version, safe="")
        version_dir_url = f"{base_url}{artifact_path}/{version_part}"

        if _is_snapshot_version(version):
            snapshot_metadata_url = f"{version_dir_url}/maven-metadata.xml"
            jar_basename = _resolve_snapshot_jar_basename(
                await _fetch_text(client, snapshot_metadata_url),
                artifact,
            )
        else:
            jar_basename = _release_jar_basename(artifact, version)

    jar_url = f"{version_dir_url}/{quote(jar_basename, safe='')}"
    return jar_url, version


async def fetch_jar_bytes(url: str) -> bytes:
    """Download JAR payload from the given URL."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=60.0)
        response.raise_for_status()
    return response.content
