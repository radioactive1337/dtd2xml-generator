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


async def resolve_jar_url(cfg: NexusDtdConfig) -> tuple[str, str]:
    """Build artifact JAR URL and resolved version."""
    base_url = _normalize_base_url(cfg.base_url.strip())
    if not base_url:
        raise ValueError("nexus_dtd.base_url is required")

    artifact_path = _artifact_path(cfg)
    artifact = quote(cfg.artifact_id.strip(), safe="")
    configured_version = cfg.version.strip() or "LATEST"

    if configured_version.upper() == "LATEST":
        metadata_url = f"{base_url}{artifact_path}/maven-metadata.xml"
        async with httpx.AsyncClient() as client:
            response = await client.get(metadata_url, timeout=30.0)
            response.raise_for_status()
        version = _resolve_latest_version(response.text)
    else:
        version = configured_version

    version_part = quote(version, safe="")
    jar_name = f"{artifact}-{version}.jar"
    jar_url = f"{base_url}{artifact_path}/{version_part}/{jar_name}"
    return jar_url, version


async def fetch_jar_bytes(url: str) -> bytes:
    """Download JAR payload from the given URL."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=60.0)
        response.raise_for_status()
    return response.content
