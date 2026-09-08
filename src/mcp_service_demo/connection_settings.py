from __future__ import annotations

import base64
import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from . import __version__
from .config import Settings

MASK = "***"
PORTABLE_PROFILE_FORMAT = "mcp-service-demo.settings"
PORTABLE_PROFILE_VERSION = 1
PORTABLE_PROFILE_SUFFIX = ".mcpdemo"
_PORTABLE_KDF_ITERATIONS = 600_000
_PORTABLE_MAX_BYTES = 2_000_000
_CA_FIELDS = {
    "mcp": "mcp_ca_bundle_path",
    "rest": "rest_ca_bundle_path",
    "hec": "hec_ca_bundle_path",
}
_EDITABLE_FIELDS = {
    "agent_mode",
    "demo_audience",
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
    "splunk_app",
    "splunk_owner",
    "splunk_index",
    "splunk_sourcetype",
    "splunk_scenario_id",
    "splunk_search_timeout_seconds",
    "splunk_index_wait_seconds",
    "splunk_hec_batch_size",
    "openai_timeout_seconds",
    "openai_max_retries",
    "openai_max_iterations",
    "openai_max_tool_calls",
    "openai_max_output_tokens",
    "openai_max_parallel_tools",
}
_SECRET_FIELDS = {
    "mcp_token",
    "rest_token",
    "hec_token",
    "splunk_username",
    "splunk_password",
    "openai_api_key",
}
_BOOLEAN_FIELDS = {"mcp_verify_ssl", "rest_verify_ssl", "hec_verify_ssl"}
_NUMBER_FIELDS = {
    "splunk_search_timeout_seconds",
    "splunk_index_wait_seconds",
    "splunk_hec_batch_size",
    "openai_timeout_seconds",
    "openai_max_retries",
    "openai_max_iterations",
    "openai_max_tool_calls",
    "openai_max_output_tokens",
    "openai_max_parallel_tools",
}


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
        demo_contract = {
            "splunk_app": _bounded_text(
                saved.get("splunk_app", base.splunk_app), "Splunk app", 128
            ),
            "splunk_owner": _bounded_text(
                saved.get("splunk_owner", base.splunk_owner), "Splunk owner", 128
            ),
            "splunk_index": _bounded_text(
                saved.get("splunk_index", base.splunk_index), "Splunk index", 128
            ),
            "splunk_sourcetype": _bounded_text(
                saved.get("splunk_sourcetype", base.splunk_sourcetype),
                "Splunk source type",
                128,
            ),
            "splunk_scenario_id": _bounded_text(
                saved.get("splunk_scenario_id", base.splunk_scenario_id),
                "Splunk scenario",
                128,
            ),
        }

        return replace(
            base,
            splunk_mcp_url=mcp_url.rstrip("/"),
            splunk_mcp_token=_secret(saved, "mcp_token", base.splunk_mcp_token),
            splunk_mcp_verify=mcp_verify,
            splunk_data_mode=data_mode,
            splunk_rest_url=rest_url.rstrip("/"),
            splunk_rest_token=_secret(saved, "rest_token", base.splunk_rest_token),
            splunk_rest_token_scheme=rest_scheme,
            splunk_username=_secret(saved, "splunk_username", base.splunk_username),
            splunk_password=_secret(saved, "splunk_password", base.splunk_password),
            splunk_rest_verify=rest_verify,
            splunk_search_timeout_seconds=_number(
                saved.get("splunk_search_timeout_seconds", base.splunk_search_timeout_seconds),
                "Splunk search timeout",
                minimum=1,
                maximum=300,
            ),
            splunk_index_wait_seconds=_number(
                saved.get("splunk_index_wait_seconds", base.splunk_index_wait_seconds),
                "Splunk index wait",
                minimum=0,
                maximum=300,
            ),
            splunk_app=demo_contract["splunk_app"],
            splunk_owner=demo_contract["splunk_owner"],
            splunk_index=demo_contract["splunk_index"],
            splunk_sourcetype=demo_contract["splunk_sourcetype"],
            splunk_scenario_id=demo_contract["splunk_scenario_id"],
            splunk_hec_url=hec_url.rstrip("/") if hec_url else None,
            splunk_hec_token=_secret(saved, "hec_token", base.splunk_hec_token),
            splunk_hec_verify=hec_verify,
            splunk_hec_batch_size=int(
                _number(
                    saved.get("splunk_hec_batch_size", base.splunk_hec_batch_size),
                    "HEC batch size",
                    minimum=1,
                    maximum=10_000,
                    integer=True,
                )
            ),
            agent_mode_preference=agent_mode,
            openai_base_url=openai_base_url.rstrip("/"),
            openai_api_key=_secret(saved, "openai_api_key", base.openai_api_key),
            openai_model=openai_model,
            openai_timeout_seconds=_number(
                saved.get("openai_timeout_seconds", base.openai_timeout_seconds),
                "LLM request timeout",
                minimum=10,
                maximum=300,
            ),
            openai_max_retries=int(
                _number(
                    saved.get("openai_max_retries", base.openai_max_retries),
                    "LLM retries",
                    minimum=0,
                    maximum=5,
                    integer=True,
                )
            ),
            openai_max_iterations=int(
                _number(
                    saved.get("openai_max_iterations", base.openai_max_iterations),
                    "LLM iterations",
                    minimum=2,
                    maximum=32,
                    integer=True,
                )
            ),
            openai_max_tool_calls=int(
                _number(
                    saved.get("openai_max_tool_calls", base.openai_max_tool_calls),
                    "LLM tool calls",
                    minimum=1,
                    maximum=64,
                    integer=True,
                )
            ),
            openai_max_output_tokens=int(
                _number(
                    saved.get("openai_max_output_tokens", base.openai_max_output_tokens),
                    "LLM output tokens",
                    minimum=256,
                    maximum=32_768,
                    integer=True,
                )
            ),
            openai_max_parallel_tools=int(
                _number(
                    saved.get("openai_max_parallel_tools", base.openai_max_parallel_tools),
                    "Parallel MCP tools",
                    minimum=1,
                    maximum=8,
                    integer=True,
                )
            ),
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
            "rest_basic_auth_configured": bool(
                effective.splunk_username and effective.splunk_password
            ),
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
            "tuning": {
                "profile": "Balanced",
                "max_iterations": effective.openai_max_iterations,
                "max_tool_calls": effective.openai_max_tool_calls,
                "max_parallel_tools": effective.openai_max_parallel_tools,
                "request_timeout_seconds": effective.openai_timeout_seconds,
            },
        }

    def safe_export_demo(self) -> dict[str, Any]:
        saved = self.load()
        audience = str(saved.get("demo_audience", "executive")).strip().lower()
        if audience not in {"executive", "engineering", "security", "finance"}:
            audience = "executive"
        return {
            "audience": audience,
            "source": "saved profile" if "demo_audience" in saved else "default",
        }

    def export_portable(self, base: Settings, passphrase: str) -> dict[str, Any]:
        """Create a passphrase-encrypted profile that can be imported on another host."""
        _validate_passphrase(passphrase)
        effective = self.apply(base)
        profile = self._portable_profile(effective)
        certificates: dict[str, str] = {}

        for name, field in _CA_FIELDS.items():
            ca_path = str(profile.get(field) or "").strip()
            if not ca_path:
                continue
            certificates[name] = _read_ca_bundle(Path(ca_path), name)
            profile[field] = ""

        payload = {
            "source_app_version": __version__,
            "exported_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "profile": profile,
            "certificates": certificates,
        }
        salt = os.urandom(16)
        encrypted = _portable_fernet(passphrase, salt, _PORTABLE_KDF_ITERATIONS).encrypt(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        return {
            "format": PORTABLE_PROFILE_FORMAT,
            "version": PORTABLE_PROFILE_VERSION,
            "encryption": {
                "algorithm": "fernet-pbkdf2-sha256",
                "iterations": _PORTABLE_KDF_ITERATIONS,
                "salt": base64.urlsafe_b64encode(salt).decode("ascii"),
            },
            "payload": encrypted.decode("ascii"),
        }

    def preview_portable(
        self, base: Settings, bundle: Mapping[str, Any], passphrase: str
    ) -> dict[str, Any]:
        payload = self._decode_portable(base, bundle, passphrase)
        return self._portable_summary(base, payload)

    def import_portable(
        self, base: Settings, bundle: Mapping[str, Any], passphrase: str
    ) -> dict[str, Any]:
        """Validate and replace the saved profile with a portable bundle."""
        payload = self._decode_portable(base, bundle, passphrase)
        profile = dict(payload["profile"])
        certificates = dict(payload.get("certificates") or {})

        certificate_paths: dict[str, Path] = {}
        for name, field in _CA_FIELDS.items():
            certificate = certificates.get(name)
            if certificate is None:
                continue
            fingerprint = hashlib.sha256(certificate.encode("utf-8")).hexdigest()[:12]
            certificate_paths[field] = (
                self.config_path.parent / "certificates" / f"{name}-ca-{fingerprint}.pem"
            )
            profile[field] = str(certificate_paths[field])

        self.apply(base, profile)
        for field, path in certificate_paths.items():
            name = next(name for name, candidate in _CA_FIELDS.items() if candidate == field)
            _write_ca_bundle(path, certificates[name])
        profile["version"] = 3
        self._write(profile)
        return self._portable_summary(base, payload)

    def _portable_profile(self, effective: Settings) -> dict[str, Any]:
        def ca_path(value: bool | str) -> str:
            return value if isinstance(value, str) else ""

        audience = self.safe_export_demo()["audience"]
        return {
            "version": 3,
            "demo_audience": audience,
            "mcp_url": effective.splunk_mcp_url,
            "mcp_token": effective.splunk_mcp_token or "",
            "mcp_verify_ssl": effective.splunk_mcp_verify is not False,
            "mcp_ca_bundle_path": ca_path(effective.splunk_mcp_verify),
            "data_mode": effective.splunk_data_mode,
            "rest_url": effective.splunk_rest_url,
            "rest_token": effective.splunk_rest_token or "",
            "rest_token_scheme": effective.splunk_rest_token_scheme,
            "splunk_username": effective.splunk_username or "",
            "splunk_password": effective.splunk_password or "",
            "rest_verify_ssl": effective.splunk_rest_verify is not False,
            "rest_ca_bundle_path": ca_path(effective.splunk_rest_verify),
            "hec_url": effective.splunk_hec_url or "",
            "hec_token": effective.splunk_hec_token or "",
            "hec_verify_ssl": effective.splunk_hec_verify is not False,
            "hec_ca_bundle_path": ca_path(effective.splunk_hec_verify),
            "splunk_app": effective.splunk_app,
            "splunk_owner": effective.splunk_owner,
            "splunk_index": effective.splunk_index,
            "splunk_sourcetype": effective.splunk_sourcetype,
            "splunk_scenario_id": effective.splunk_scenario_id,
            "splunk_search_timeout_seconds": effective.splunk_search_timeout_seconds,
            "splunk_index_wait_seconds": effective.splunk_index_wait_seconds,
            "splunk_hec_batch_size": effective.splunk_hec_batch_size,
            "agent_mode": effective.agent_mode,
            "openai_base_url": effective.openai_base_url,
            "openai_api_key": effective.openai_api_key or "",
            "openai_model": effective.openai_model,
            "openai_timeout_seconds": effective.openai_timeout_seconds,
            "openai_max_retries": effective.openai_max_retries,
            "openai_max_iterations": effective.openai_max_iterations,
            "openai_max_tool_calls": effective.openai_max_tool_calls,
            "openai_max_output_tokens": effective.openai_max_output_tokens,
            "openai_max_parallel_tools": effective.openai_max_parallel_tools,
        }

    def _decode_portable(
        self, base: Settings, bundle: Mapping[str, Any], passphrase: str
    ) -> dict[str, Any]:
        _validate_passphrase(passphrase)
        try:
            encoded_bundle = json.dumps(dict(bundle), separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("The settings package is not valid JSON") from exc
        if len(encoded_bundle) > _PORTABLE_MAX_BYTES:
            raise ValueError("The settings package is too large")
        if bundle.get("format") != PORTABLE_PROFILE_FORMAT:
            raise ValueError("This is not an MCP Service Demo settings package")
        if bundle.get("version") != PORTABLE_PROFILE_VERSION:
            raise ValueError("This settings package version is not supported")

        encryption = bundle.get("encryption")
        if not isinstance(encryption, Mapping):
            raise ValueError("The settings package encryption metadata is missing")
        if encryption.get("algorithm") != "fernet-pbkdf2-sha256":
            raise ValueError("The settings package encryption method is not supported")
        iterations = encryption.get("iterations")
        if (
            not isinstance(iterations, int)
            or isinstance(iterations, bool)
            or not 100_000 <= iterations <= 1_000_000
        ):
            raise ValueError("The settings package key derivation settings are invalid")
        try:
            salt = base64.urlsafe_b64decode(str(encryption.get("salt") or "").encode("ascii"))
        except (ValueError, UnicodeEncodeError) as exc:
            raise ValueError("The settings package salt is invalid") from exc
        if len(salt) != 16:
            raise ValueError("The settings package salt is invalid")
        encrypted = bundle.get("payload")
        if not isinstance(encrypted, str) or not encrypted:
            raise ValueError("The settings package payload is missing")
        try:
            decrypted = _portable_fernet(passphrase, salt, iterations).decrypt(
                encrypted.encode("ascii")
            )
            payload = json.loads(decrypted.decode("utf-8"))
        except (InvalidToken, UnicodeEncodeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("The settings package or passphrase is not valid") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("profile"), dict):
            raise ValueError("The settings package profile is invalid")

        profile = payload["profile"]
        allowed_fields = _EDITABLE_FIELDS | _SECRET_FIELDS | {"version"}
        unknown_fields = set(profile) - allowed_fields
        if unknown_fields:
            raise ValueError("The settings package contains unsupported profile fields")
        _validate_profile_types(profile)
        _audience(profile.get("demo_audience", "executive"))

        certificates = payload.get("certificates") or {}
        if not isinstance(certificates, dict) or set(certificates) - set(_CA_FIELDS):
            raise ValueError("The settings package contains invalid CA bundle data")
        for name, certificate in certificates.items():
            _validate_ca_bundle(certificate, name)

        candidate_profile = dict(profile)
        for name, field in _CA_FIELDS.items():
            if name in certificates:
                candidate_profile[field] = f"/portable/{name}-ca.pem"
            elif candidate_profile.get(field):
                raise ValueError(
                    f"The settings package references a {name.upper()} CA file "
                    "but does not include it"
                )
        candidate = self.apply(base, candidate_profile)
        if candidate.agent_mode_preference == "openai" and not candidate.llm_configured:
            raise ValueError("The imported LLM-assisted profile does not include an API key")
        return payload

    def _portable_summary(self, base: Settings, payload: Mapping[str, Any]) -> dict[str, Any]:
        profile = dict(payload["profile"])
        effective = self.apply(base, profile)
        certificates = payload.get("certificates") or {}
        credential_labels = [
            label
            for label, value in (
                ("Splunk MCP bearer token", profile.get("mcp_token")),
                ("Splunk REST token", profile.get("rest_token")),
                ("Splunk REST username and password", profile.get("splunk_password")),
                ("Splunk HEC token", profile.get("hec_token")),
                ("LLM API key", profile.get("openai_api_key")),
            )
            if value
        ]
        return {
            "source_app_version": str(payload.get("source_app_version") or "unknown"),
            "exported_at": str(payload.get("exported_at") or "unknown"),
            "splunk": {
                "data_mode": effective.splunk_data_mode,
                "mcp_host": _url_host(effective.splunk_mcp_url),
                "rest_host": _url_host(effective.splunk_rest_url),
                "hec_host": _url_host(effective.splunk_hec_url),
                "app": effective.splunk_app,
                "index": effective.splunk_index,
            },
            "llm": {
                "agent_mode": effective.agent_mode,
                "host": _url_host(effective.openai_base_url),
                "model": effective.openai_model,
            },
            "audience": _audience(profile.get("demo_audience", "executive")),
            "credential_labels": credential_labels,
            "credential_count": len(credential_labels),
            "custom_ca_bundles": len(certificates),
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
        current["version"] = 3
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


def _audience(value: Any) -> str:
    normalized = str(value or "executive").strip().lower()
    if normalized not in {"executive", "engineering", "security", "finance"}:
        raise ValueError("Demo audience is not supported")
    return normalized


def _bounded_text(value: Any, label: str, maximum: int) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    if len(normalized) > maximum or any(character in normalized for character in "\r\n\x00"):
        raise ValueError(f"{label} must be {maximum} characters or fewer")
    return normalized


def _number(
    value: Any,
    label: str,
    *,
    minimum: float,
    maximum: float,
    integer: bool = False,
) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a number")
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a number") from exc
    if integer and not normalized.is_integer():
        raise ValueError(f"{label} must be a whole number")
    if not minimum <= normalized <= maximum:
        raise ValueError(f"{label} must be between {minimum:g} and {maximum:g}")
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


def _validate_passphrase(passphrase: str) -> None:
    if not isinstance(passphrase, str) or len(passphrase) < 12:
        raise ValueError("Use a passphrase of at least 12 characters")
    if len(passphrase) > 256:
        raise ValueError("The passphrase must be 256 characters or fewer")


def _portable_fernet(passphrase: str, salt: bytes, iterations: int) -> Fernet:
    derived = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    ).derive(passphrase.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(derived))


def _validate_profile_types(profile: Mapping[str, Any]) -> None:
    for field in _BOOLEAN_FIELDS:
        if field in profile and not isinstance(profile[field], bool):
            raise ValueError(f"The settings package field {field} must be true or false")
    for field in _NUMBER_FIELDS:
        value = profile.get(field)
        if field in profile and (not isinstance(value, (int, float)) or isinstance(value, bool)):
            raise ValueError(f"The settings package field {field} must be a number")
    for field in (_EDITABLE_FIELDS | _SECRET_FIELDS) - _BOOLEAN_FIELDS - _NUMBER_FIELDS:
        value = profile.get(field)
        if field in profile and not isinstance(value, str):
            raise ValueError(f"The settings package field {field} must be text")


def _validate_ca_bundle(certificate: Any, name: str) -> str:
    if not isinstance(certificate, str):
        raise ValueError(f"The embedded {name.upper()} CA bundle must be text")
    if len(certificate.encode("utf-8")) > 1_000_000:
        raise ValueError(f"The embedded {name.upper()} CA bundle is too large")
    if "-----BEGIN CERTIFICATE-----" not in certificate:
        raise ValueError(f"The embedded {name.upper()} CA bundle is not PEM certificate data")
    return certificate


def _read_ca_bundle(path: Path, name: str) -> str:
    try:
        certificate = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(
            f"The configured {name.upper()} CA bundle could not be included: {path}"
        ) from exc
    return _validate_ca_bundle(certificate, name)


def _write_ca_bundle(path: Path, certificate: str) -> None:
    validated = _validate_ca_bundle(certificate, path.stem)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(validated, encoding="utf-8")
    _secure_file(temporary)
    temporary.replace(path)
    _secure_file(path)


def _url_host(value: str | None) -> str:
    if not value:
        return "not configured"
    parsed = urlparse(value)
    return parsed.netloc or "not configured"
