from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken

from .config import Settings

MASK = "***"
_EDITABLE_FIELDS = {
    "agent_mode",
    "openai_base_url",
    "openai_model",
    "mcp_url",
    "mcp_verify_ssl",
    "mcp_ca_bundle_path",
    "data_mode",
    "rest_url",
    "rest_token_scheme",
    "rest_verify_ssl",
    "rest_ca_bundle_path",
    "hec_url",
    "hec_verify_ssl",
    "hec_ca_bundle_path",
}
_SECRET_FIELDS = {"mcp_token", "rest_token", "hec_token", "openai_api_key"}


class SplunkConnectionStore:
    """Encrypted, process-shared overrides for the demo's external connections."""

    def __init__(
        self,
        config_path: Path,
        key_path: Path,
        *,
        legacy_config_path: Path | None = None,
        legacy_key_path: Path | None = None,
    ):
        self.config_path = config_path
        self.key_path = key_path
        self.legacy_config_path = legacy_config_path
        self.legacy_key_path = legacy_key_path

    @classmethod
    def for_settings(cls, settings: Settings) -> SplunkConnectionStore:
        data_directory = settings.database_path.parent
        legacy_config_path = data_directory / "splunk-connection.enc"
        legacy_key_path = data_directory / ".splunk-connection.key"
        config_path = Path(
            os.getenv(
                "DEMO_SPLUNK_CONFIG_PATH",
                legacy_config_path,
            )
        )
        key_path = Path(
            os.getenv(
                "DEMO_SPLUNK_CONFIG_KEY_PATH",
                legacy_key_path,
            )
        )
        return cls(
            config_path,
            key_path,
            legacy_config_path=(legacy_config_path if config_path != legacy_config_path else None),
            legacy_key_path=(legacy_key_path if key_path != legacy_key_path else None),
        )

    @property
    def configured(self) -> bool:
        self._migrate_legacy_profile()
        return self.config_path.is_file()

    def load(self) -> dict[str, Any]:
        self._migrate_legacy_profile()
        if not self.config_path.is_file():
            return {}
        if not self.key_path.is_file():
            raise RuntimeError(
                f"Saved Splunk settings exist, but their key is missing: {self.key_path}"
            )
        try:
            key = self.key_path.read_bytes()
            decrypted = Fernet(key).decrypt(self.config_path.read_bytes())
            payload = json.loads(decrypted.decode("utf-8"))
        except (InvalidToken, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("Saved Splunk settings could not be decrypted") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Saved Splunk settings have an invalid format")
        return payload

    def apply(self, base: Settings, payload: Mapping[str, Any] | None = None) -> Settings:
        saved = dict(payload) if payload is not None else self.load()
        if not saved:
            return base

        mcp_url = _url(saved.get("mcp_url", base.splunk_mcp_url), "Splunk MCP endpoint")
        mcp_verify = _verify_value(
            saved.get("mcp_verify_ssl", base.splunk_mcp_verify is not False),
            saved.get("mcp_ca_bundle_path"),
        )
        data_mode = _data_mode(saved.get("data_mode", base.splunk_data_mode))
        rest_url = _url(saved.get("rest_url", base.splunk_rest_url), "Splunk API URL")
        rest_scheme = _token_scheme(saved.get("rest_token_scheme", base.splunk_rest_token_scheme))
        rest_verify = _verify_value(
            saved.get("rest_verify_ssl", base.splunk_rest_verify is not False),
            saved.get("rest_ca_bundle_path"),
        )
        hec_url_value = saved.get("hec_url", base.splunk_hec_url)
        hec_url = _optional_url(hec_url_value, "HEC URL")
        hec_verify = _verify_value(
            saved.get("hec_verify_ssl", base.splunk_hec_verify is not False),
            saved.get("hec_ca_bundle_path"),
        )
        agent_mode = _agent_mode(saved.get("agent_mode", base.agent_mode_preference))
        openai_base_url = _url(
            saved.get("openai_base_url", base.openai_base_url),
            "LLM API endpoint",
        )
        openai_model = _model(saved.get("openai_model", base.openai_model))

        return replace(
            base,
            splunk_mcp_url=mcp_url.rstrip("/"),
            splunk_mcp_token=_secret(saved, "mcp_token", base.splunk_mcp_token),
            splunk_mcp_verify=mcp_verify,
            splunk_data_mode=data_mode,
            splunk_rest_url=rest_url.rstrip("/"),
            splunk_rest_token=_secret(saved, "rest_token", base.splunk_rest_token),
            splunk_rest_token_scheme=rest_scheme,
            splunk_rest_verify=rest_verify,
            splunk_hec_url=hec_url.rstrip("/") if hec_url else None,
            splunk_hec_token=_secret(saved, "hec_token", base.splunk_hec_token),
            splunk_hec_verify=hec_verify,
            agent_mode_preference=agent_mode,
            openai_base_url=openai_base_url.rstrip("/"),
            openai_api_key=_secret(saved, "openai_api_key", base.openai_api_key),
            openai_model=openai_model,
        )

    def preview(self, base: Settings, update: Mapping[str, Any]) -> Settings:
        return self.apply(base, self._merged_payload(update))

    def save(self, base: Settings, update: Mapping[str, Any]) -> Settings:
        payload = self._merged_payload(update)
        effective = self.apply(base, payload)
        self._write(payload)
        return effective

    def safe_export(self, base: Settings) -> dict[str, Any]:
        effective = self.apply(base)
        mcp_ca = (
            str(effective.splunk_mcp_verify)
            if isinstance(effective.splunk_mcp_verify, str)
            else None
        )
        rest_ca = (
            str(effective.splunk_rest_verify)
            if isinstance(effective.splunk_rest_verify, str)
            else None
        )
        hec_ca = (
            str(effective.splunk_hec_verify)
            if isinstance(effective.splunk_hec_verify, str)
            else None
        )
        return {
            "source": "saved profile" if self.configured else "environment defaults",
            "mcp_url": effective.splunk_mcp_url,
            "mcp_token": MASK if effective.splunk_mcp_token else "",
            "mcp_token_configured": bool(effective.splunk_mcp_token),
            "mcp_verify_ssl": effective.splunk_mcp_verify is not False,
            "mcp_ca_bundle_path": mcp_ca,
            "data_mode": effective.splunk_data_mode,
            "rest_url": effective.splunk_rest_url,
            "rest_token": MASK if effective.splunk_rest_token else "",
            "rest_token_configured": bool(effective.splunk_rest_token),
            "rest_token_scheme": effective.splunk_rest_token_scheme,
            "rest_verify_ssl": effective.splunk_rest_verify is not False,
            "rest_ca_bundle_path": rest_ca,
            "hec_url": effective.splunk_hec_url or "",
            "hec_token": MASK if effective.splunk_hec_token else "",
            "hec_token_configured": bool(effective.splunk_hec_token),
            "hec_verify_ssl": effective.splunk_hec_verify is not False,
            "hec_ca_bundle_path": hec_ca,
            "contract": {
                "app": effective.splunk_app,
                "owner": effective.splunk_owner,
                "index": effective.splunk_index,
                "sourcetype": effective.splunk_sourcetype,
                "scenario_id": effective.splunk_scenario_id,
            },
        }

    def safe_export_llm(self, base: Settings) -> dict[str, Any]:
        saved = self.load()
        effective = self.apply(base, saved)
        llm_fields = {"agent_mode", "openai_base_url", "openai_api_key", "openai_model"}
        return {
            "source": "saved profile" if llm_fields.intersection(saved) else "environment defaults",
            "agent_mode": effective.agent_mode_preference,
            "active_mode": effective.agent_mode,
            "base_url": effective.openai_base_url,
            "api_key": MASK if effective.openai_api_key else "",
            "api_key_configured": effective.llm_configured,
            "model": effective.openai_model,
            "provider": "OpenAI-compatible Responses API",
        }

    def _merged_payload(self, update: Mapping[str, Any]) -> dict[str, Any]:
        current = self.load()
        for field in _EDITABLE_FIELDS:
            if field in update and update[field] is not None:
                current[field] = update[field]
        for field in _SECRET_FIELDS:
            value = str(update.get(field) or "").strip()
            if value and value != MASK:
                current[field] = value
        if update.get("clear_rest_token"):
            current.pop("rest_token", None)
        if update.get("clear_hec_token"):
            current.pop("hec_token", None)
        if update.get("clear_mcp_token"):
            current.pop("mcp_token", None)
        if update.get("clear_openai_api_key"):
            current.pop("openai_api_key", None)
        current["version"] = 2
        return current

    def _write(self, payload: Mapping[str, Any]) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.key_path.is_file():
            self.key_path.write_bytes(Fernet.generate_key())
            _secure_file(self.key_path)
        encrypted = Fernet(self.key_path.read_bytes()).encrypt(
            json.dumps(dict(payload), sort_keys=True).encode("utf-8")
        )
        temporary_path = self.config_path.with_suffix(self.config_path.suffix + ".tmp")
        temporary_path.write_bytes(encrypted)
        _secure_file(temporary_path)
        temporary_path.replace(self.config_path)
        _secure_file(self.config_path)

    def _migrate_legacy_profile(self) -> None:
        """Copy an existing profile when credentials move to their own volume."""
        legacy_config = self.legacy_config_path
        legacy_key = self.legacy_key_path
        if (
            self.config_path.is_file()
            or self.key_path.is_file()
            or legacy_config is None
            or legacy_key is None
            or not legacy_config.is_file()
            or not legacy_key.is_file()
        ):
            return

        key = legacy_key.read_bytes()
        encrypted = legacy_config.read_bytes()
        try:
            Fernet(key).decrypt(encrypted)
        except (InvalidToken, ValueError) as exc:
            raise RuntimeError("Legacy Splunk settings could not be decrypted") from exc

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_key = self.key_path.with_name(f"{self.key_path.name}.{os.getpid()}.tmp")
        temporary_config = self.config_path.with_name(f"{self.config_path.name}.{os.getpid()}.tmp")
        try:
            temporary_key.write_bytes(key)
            temporary_config.write_bytes(encrypted)
            _secure_file(temporary_key)
            _secure_file(temporary_config)
            temporary_key.replace(self.key_path)
            temporary_config.replace(self.config_path)
            _secure_file(self.key_path)
            _secure_file(self.config_path)
        finally:
            temporary_key.unlink(missing_ok=True)
            temporary_config.unlink(missing_ok=True)


def _secret(saved: Mapping[str, Any], name: str, fallback: str | None) -> str | None:
    value = str(saved.get(name) or "").strip()
    return value or fallback


def _data_mode(value: Any) -> str:
    normalized = str(value or "fixture").strip().lower()
    if normalized not in {"fixture", "live"}:
        raise ValueError("Data source must be 'fixture' or 'live'")
    return normalized


def _agent_mode(value: Any) -> str:
    normalized = str(value or "guided").strip().lower()
    if normalized not in {"guided", "openai"}:
        raise ValueError("Agent mode must be 'guided' or 'openai'")
    return normalized


def _model(value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError("LLM model is required")
    if len(normalized) > 120:
        raise ValueError("LLM model must be 120 characters or fewer")
    return normalized


def _token_scheme(value: Any) -> str:
    normalized = str(value or "Bearer").strip().title()
    if normalized not in {"Bearer", "Splunk"}:
        raise ValueError("REST token type must be 'Bearer' or 'Splunk'")
    return normalized


def _url(value: Any, label: str) -> str:
    normalized = str(value or "").strip()
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{label} must be a complete http:// or https:// URL")
    return normalized


def _optional_url(value: Any, label: str) -> str | None:
    normalized = str(value or "").strip()
    return _url(normalized, label) if normalized else None


def _verify_value(verify_ssl: Any, ca_bundle_path: Any) -> bool | str:
    verify = bool(verify_ssl)
    ca_path = str(ca_bundle_path or "").strip()
    return ca_path if verify and ca_path else verify


def _secure_file(path: Path) -> None:
    if os.name != "nt":
        path.chmod(0o600)
