"""Reusable API endpoint profiles. Secret values are stored only in the OS vault."""
from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .network import assert_public_url

FORMAT = "openrpa.api-connections"
VERSION = 2
MAX_PROFILES = 100
MAX_FILE_BYTES = 1_000_000
VAULT_SERVICE = "OpenRPA API Connection"
HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}$")
FORBIDDEN_HEADERS = {"authorization", "cookie", "set-cookie", "host", "connection", "content-length", "transfer-encoding", "proxy-authorization"}


def default_store_path() -> Path:
    configured=os.environ.get("OPENRPA_API_CONNECTIONS_FILE")
    if configured:return Path(configured).expanduser().resolve()
    if os.name=="nt":base=Path(os.environ.get("LOCALAPPDATA",Path.home()/"AppData/Local"))
    else:base=Path(os.environ.get("XDG_DATA_HOME",Path.home()/".local/share"))/"open-rpa-studio"
    return base/"Open RPA Studio"/"MCP Data"/"api-connections.json" if os.name=="nt" else base/"api-connections.json"


def _profile(value: Any, *, require_id: bool = False) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("API connection must be an object")
    allowed = {"id", "name", "baseUrl", "authType", "apiKeyHeader", "headers", "minIntervalSeconds", "tokenUrl", "clientId", "scope", "audience", "clientAuthMethod"}
    if set(value) - allowed:
        raise ValueError("API connection contains unsupported fields")
    raw_id = value.get("id")
    if require_id or raw_id:
        try:
            profile_id = str(uuid.UUID(str(raw_id)))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("API connection has an invalid id") from exc
    else:
        profile_id = str(uuid.uuid4())
    name = value.get("name")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
        raise ValueError("API connection name must contain 1–100 characters")
    base_url = value.get("baseUrl")
    if not isinstance(base_url, str) or len(base_url) > 2048:
        raise ValueError("API base URL must be text no longer than 2,048 characters")
    parts = urlsplit(base_url.strip())
    if parts.scheme != "https" or not parts.hostname or parts.username is not None or parts.password is not None or parts.query or parts.fragment:
        raise ValueError("API base URL must be an HTTPS origin/path without credentials, query, or fragment")
    try:
        assert_public_url(base_url.rstrip("/"))
    except Exception as exc:
        raise ValueError(f"API base URL is not a permitted public HTTPS destination: {exc}") from exc
    auth_type = value.get("authType", "none")
    if auth_type not in {"none", "bearer", "api_key_header", "oauth_client_credentials"}:
        raise ValueError("API authentication must be none, bearer, api_key_header, or oauth_client_credentials")
    key_header = value.get("apiKeyHeader", "X-API-Key")
    if not isinstance(key_header, str) or not HEADER_NAME.fullmatch(key_header) or key_header.lower() in FORBIDDEN_HEADERS:
        raise ValueError("API key header must be a valid, non-transport HTTP header name")
    headers = value.get("headers", {})
    if not isinstance(headers, dict) or len(headers) > 50:
        raise ValueError("API connection headers must be an object containing at most 50 headers")
    safe_headers: dict[str, str] = {}
    for key, header_value in headers.items():
        if not isinstance(key, str) or not HEADER_NAME.fullmatch(key) or key.lower() in FORBIDDEN_HEADERS or any(term in key.lower() for term in ("token", "secret", "api-key", "apikey")):
            raise ValueError("API connection contains an invalid or sensitive header name; store secrets using the authentication field")
        if auth_type == "api_key_header" and key.casefold() == key_header.casefold():
            raise ValueError("API key header values must come from the OS credential vault")
        if not isinstance(header_value, str) or len(header_value) > 8192 or "\r" in header_value or "\n" in header_value:
            raise ValueError(f"API connection header {key!r} must be single-line text no longer than 8,192 characters")
        safe_headers[key] = header_value
    interval = value.get("minIntervalSeconds", 0)
    if isinstance(interval, bool) or not isinstance(interval, (float, int)) or not 0 <= interval <= 60:
        raise ValueError("Minimum request interval must be between 0 and 60 seconds")
    oauth_fields={}
    if auth_type=="oauth_client_credentials":
        token_url=value.get("tokenUrl")
        if not isinstance(token_url,str) or len(token_url)>2048:
            raise ValueError("OAuth token URL must be HTTPS text no longer than 2,048 characters")
        token_parts=urlsplit(token_url.strip())
        if token_parts.scheme!="https" or not token_parts.hostname or token_parts.username is not None or token_parts.password is not None or token_parts.query or token_parts.fragment:
            raise ValueError("OAuth token URL must be an HTTPS URL without embedded credentials, query, or fragment")
        try:assert_public_url(token_url.strip())
        except Exception as exc:raise ValueError(f"OAuth token URL is not a permitted public HTTPS destination: {exc}") from exc
        client_id=value.get("clientId")
        if not isinstance(client_id,str) or not client_id.strip() or len(client_id)>1024 or "\r" in client_id or "\n" in client_id:
            raise ValueError("OAuth client ID must contain 1–1,024 single-line characters")
        scope=value.get("scope","");audience=value.get("audience","");client_auth=value.get("clientAuthMethod","client_secret_basic")
        if not isinstance(scope,str) or len(scope)>2048 or "\r" in scope or "\n" in scope:raise ValueError("OAuth scope must be single-line text up to 2,048 characters")
        if not isinstance(audience,str) or len(audience)>2048 or "\r" in audience or "\n" in audience:raise ValueError("OAuth audience must be single-line text up to 2,048 characters")
        if client_auth not in {"client_secret_basic","client_secret_post"}:raise ValueError("OAuth client authentication must be client_secret_basic or client_secret_post")
        oauth_fields={"tokenUrl":token_url.strip(),"clientId":client_id.strip(),"scope":scope,"audience":audience,"clientAuthMethod":client_auth}
    return {"id": profile_id, "name": name.strip(), "baseUrl": base_url.strip().rstrip("/"),
            "authType": auth_type, "apiKeyHeader": key_header, "headers": safe_headers,
            "minIntervalSeconds": float(interval),"tokenUrl":oauth_fields.get("tokenUrl",""),"clientId":oauth_fields.get("clientId",""),"scope":oauth_fields.get("scope",""),"audience":oauth_fields.get("audience",""),"clientAuthMethod":oauth_fields.get("clientAuthMethod","client_secret_basic")}


def list_profiles(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("API connection store exceeds its size limit")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("API connection store is unreadable or malformed") from exc
    if not isinstance(document, dict) or set(document) != {"format", "formatVersion", "profiles"} or document.get("format") != FORMAT or document.get("formatVersion") not in {1,VERSION} or not isinstance(document.get("profiles"), list):
        raise ValueError("Unsupported API connection store format")
    rows = [_profile(row, require_id=True) for row in document["profiles"]]
    if len(rows) > MAX_PROFILES:
        raise ValueError("API connection store exceeds the profile limit")
    if len({row["id"] for row in rows}) != len(rows) or len({row["name"].casefold() for row in rows}) != len(rows):
        raise ValueError("API connection ids and names must be unique")
    return rows


def _write(path: Path, profiles: list[dict[str, Any]]) -> None:
    if len(profiles) > MAX_PROFILES:
        raise ValueError(f"You can save at most {MAX_PROFILES} API connections")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".api-connections-", suffix=".tmp", dir=path.parent)
    try:
        try: os.chmod(temporary, 0o600)
        except OSError: pass
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump({"format": FORMAT, "formatVersion": VERSION, "profiles": profiles}, stream, ensure_ascii=False, indent=2)
            stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        try: os.chmod(path, 0o600)
        except OSError: pass
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def save_profile(path: Path, value: Any) -> dict[str, Any]:
    profile = _profile(value)
    profiles = list_profiles(path)
    for item in profiles:
        if item["id"] != profile["id"] and item["name"].casefold() == profile["name"].casefold():
            raise ValueError("An API connection with this name already exists")
    previous = next((item for item in profiles if item["id"] == profile["id"]), None)
    index = next((i for i, item in enumerate(profiles) if item["id"] == profile["id"]), None)
    if index is None: profiles.append(profile)
    else: profiles[index] = profile
    _write(path, profiles)
    if previous and previous["authType"]!="none" and profile["authType"]=="none":
        delete_secret(profile["id"])
    return profile


def get_profile(path: Path, profile_id: str) -> dict[str, Any]:
    try: normalized = str(uuid.UUID(profile_id))
    except (ValueError, AttributeError, TypeError) as exc: raise ValueError("API connection id is invalid") from exc
    profile = next((item for item in list_profiles(path) if item["id"] == normalized), None)
    if profile is None: raise ValueError("API connection was not found")
    return profile


def delete_profile(path: Path, profile_id: str) -> None:
    profile = get_profile(path, profile_id)
    remaining = [item for item in list_profiles(path) if item["id"] != profile["id"]]
    _write(path, remaining)
    if profile["authType"] != "none":
        delete_secret(profile["id"])


def store_secret(profile_id: str, secret: str) -> None:
    if not isinstance(secret, str) or not secret or len(secret) > 8192 or "\r" in secret or "\n" in secret:
        raise ValueError("API credential must contain 1–8,192 single-line characters")
    from .credentials import get_safe_keyring
    get_safe_keyring().set_password(VAULT_SERVICE, profile_id, secret)


def delete_secret(profile_id: str) -> None:
    from .credentials import get_safe_keyring
    try:get_safe_keyring().delete_password(VAULT_SERVICE,profile_id)
    except Exception:pass


def read_secret(profile_id: str) -> str:
    from .credentials import get_safe_keyring
    secret = get_safe_keyring().get_password(VAULT_SERVICE, profile_id)
    if not secret:
        raise ValueError("This API connection needs a credential stored in the OS credential vault")
    return secret


def has_secret(profile_id: str) -> bool:
    from .credentials import get_safe_keyring
    try: return bool(get_safe_keyring().get_password(VAULT_SERVICE, profile_id))
    except Exception: return False


def request_oauth_token(profile:dict[str,Any],client_secret:str,requester:Any,timeout:float=20)->tuple[str,float]:
    """Exchange client credentials using the restricted HTTP requester; never cache or persist the token here."""
    if profile.get("authType")!="oauth_client_credentials":raise ValueError("API connection does not use OAuth client credentials")
    from urllib.parse import urlencode,quote_plus
    from base64 import b64encode
    fields={"grant_type":"client_credentials"}
    if profile.get("scope"):fields["scope"]=profile["scope"]
    if profile.get("audience"):fields["audience"]=profile["audience"]
    headers={"Accept":"application/json","Content-Type":"application/x-www-form-urlencoded"}
    if profile.get("clientAuthMethod","client_secret_basic")=="client_secret_basic":
        pair=f"{quote_plus(profile['clientId'],safe='')}:{quote_plus(client_secret,safe='')}".encode("ascii")
        headers["Authorization"]="Basic "+b64encode(pair).decode("ascii")
    else:
        fields["client_id"]=profile["clientId"];fields["client_secret"]=client_secret
    response=requester(profile["tokenUrl"],"POST",headers,urlencode(fields).encode("ascii"),timeout,65_536)
    status=int(response.get("status",0))
    if status<200 or status>=300:raise ValueError(f"OAuth token endpoint returned HTTP {status}")
    try:document=json.loads(str(response.get("body","")))
    except (ValueError,TypeError):raise ValueError("OAuth token endpoint returned invalid JSON")
    if not isinstance(document,dict):raise ValueError("OAuth token response must be a JSON object")
    token=document.get("access_token");token_type=document.get("token_type","Bearer")
    if not isinstance(token,str) or not token or len(token)>8192 or "\r" in token or "\n" in token:raise ValueError("OAuth response has no valid access_token")
    if not isinstance(token_type,str) or token_type.casefold()!="bearer":raise ValueError("OAuth response must issue a Bearer token")
    expires=document.get("expires_in",300)
    if isinstance(expires,bool) or not isinstance(expires,(int,float)) or not 1<=expires<=86_400:raise ValueError("OAuth expires_in must be between 1 and 86,400 seconds")
    return token,float(expires)
