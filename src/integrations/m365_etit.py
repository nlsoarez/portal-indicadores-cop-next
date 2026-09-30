from __future__ import annotations

import base64
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from src.application.access_service import AccessService
from src.application.upload_service import UploadProcessingService
from src.infrastructure.repositories import UserRepository


GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
DEFAULT_STATE_DIR = Path(os.environ.get("M365_STATE_DIR", "data/m365"))
DEFAULT_TOKEN_CACHE = DEFAULT_STATE_DIR / "token_cache.json"
DEFAULT_SYNC_STATE = DEFAULT_STATE_DIR / "etit_sync_state.json"

PILOT_SOURCE_KEYS = (
    "residential_indicators",
    "enterprise_indicators",
)


@dataclass(frozen=True)
class EtitPilotSource:
    source_key: str
    label: str
    env_prefix: str
    filename_regex: str

    @property
    def share_url(self) -> str:
        return os.environ.get(f"{self.env_prefix}_URL", "").strip()

    @property
    def drive_id(self) -> str:
        return os.environ.get(f"{self.env_prefix}_DRIVE_ID", "").strip()

    @property
    def folder_id(self) -> str:
        return os.environ.get(f"{self.env_prefix}_FOLDER_ID", "").strip()

    @property
    def configured(self) -> bool:
        return bool(self.share_url or (self.drive_id and self.folder_id))


PILOT_SOURCES = (
    EtitPilotSource(
        source_key="residential_indicators",
        label="ETIT Residencial",
        env_prefix="M365_ETIT_RESIDENTIAL",
        filename_regex=r"^Anal[ií]tico Indicadores Residencial\s*-\s*(\d{6})\.xlsx$",
    ),
    EtitPilotSource(
        source_key="enterprise_indicators",
        label="ETIT Empresarial",
        env_prefix="M365_ETIT_ENTERPRISE",
        filename_regex=r"^Anal[ií]tico Empresarial\s*-\s*(\d{6})\.xlsx$",
    ),
)


@dataclass(frozen=True)
class RemoteFile:
    drive_id: str
    item_id: str
    name: str
    etag: str
    last_modified: str
    size: int
    competence: str

    def fingerprint(self) -> dict[str, Any]:
        return {
            "drive_id": self.drive_id,
            "item_id": self.item_id,
            "name": self.name,
            "etag": self.etag,
            "last_modified": self.last_modified,
            "size": self.size,
            "competence": self.competence,
        }


class M365ConfigurationError(RuntimeError):
    pass


class GraphRequestError(RuntimeError):
    pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def graph_share_id(url: str) -> str:
    encoded = base64.urlsafe_b64encode(url.encode("utf-8")).decode("ascii")
    return "u!" + encoded.rstrip("=")


def _safe_json_load(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(default)
    return data if isinstance(data, dict) else dict(default)


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    try:
        temp.chmod(0o600)
    except OSError:
        pass
    temp.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


class M365TokenProvider:
    def __init__(
        self,
        tenant_id: str | None = None,
        client_id: str | None = None,
        cache_path: Path | None = None,
    ):
        self.tenant_id = (tenant_id or os.environ.get("M365_TENANT_ID", "")).strip()
        self.client_id = (client_id or os.environ.get("M365_CLIENT_ID", "")).strip()
        self.cache_path = cache_path or DEFAULT_TOKEN_CACHE
        scopes_raw = os.environ.get("M365_SCOPES", "Files.Read")
        self.scopes = tuple(
            scope.strip()
            for scope in re.split(r"[,;\s]+", scopes_raw)
            if scope.strip()
        )

    @property
    def configured(self) -> bool:
        return bool(self.tenant_id and self.client_id and self.scopes)

    def _build_app(self):
        if not self.configured:
            raise M365ConfigurationError(
                "Configure M365_TENANT_ID e M365_CLIENT_ID antes de autenticar."
            )
        try:
            import msal
        except ImportError as exc:
            raise M365ConfigurationError(
                "Pacote msal não instalado. Refaça o build da aplicação."
            ) from exc

        cache = msal.SerializableTokenCache()
        if self.cache_path.exists():
            try:
                cache.deserialize(self.cache_path.read_text(encoding="utf-8"))
            except OSError:
                pass

        app = msal.PublicClientApplication(
            self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            token_cache=cache,
        )
        return app, cache

    def _save_cache(self, cache) -> None:
        if not cache.has_state_changed:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(cache.serialize(), encoding="utf-8")
        try:
            self.cache_path.chmod(0o600)
        except OSError:
            pass

    def acquire_silent(self) -> str:
        app, cache = self._build_app()
        accounts = app.get_accounts()
        if not accounts:
            raise M365ConfigurationError(
                "Microsoft 365 ainda não autenticado. Execute o comando de login do piloto."
            )

        result = app.acquire_token_silent(list(self.scopes), account=accounts[0])
        self._save_cache(cache)
        if not result or "access_token" not in result:
            detail = ""
            if isinstance(result, dict):
                detail = str(result.get("error_description") or result.get("error") or "")
            raise M365ConfigurationError(
                "Não foi possível renovar o token Microsoft 365 silenciosamente."
                + (f" Detalhe: {detail}" if detail else "")
            )
        return str(result["access_token"])

    def device_login(self) -> dict[str, Any]:
        app, cache = self._build_app()
        flow = app.initiate_device_flow(scopes=list(self.scopes))
        if "user_code" not in flow:
            raise M365ConfigurationError(
                "Microsoft não iniciou o fluxo de dispositivo: "
                + json.dumps(flow, ensure_ascii=False)
            )

        print(flow.get("message") or "")
        result = app.acquire_token_by_device_flow(flow)
        self._save_cache(cache)
        if "access_token" not in result:
            raise M365ConfigurationError(
                "Falha na autenticação Microsoft 365: "
                + str(result.get("error_description") or result.get("error") or result)
            )
        return {
            "account": (
                result.get("id_token_claims", {}).get("preferred_username")
                or result.get("id_token_claims", {}).get("upn")
                or "conta autenticada"
            ),
            "scopes": self.scopes,
        }


class GraphClient:
    def __init__(self, access_token: str):
        self.access_token = access_token

    def _request(
        self,
        url_or_path: str,
        *,
        accept_json: bool,
        timeout: int = 90,
        retries: int = 3,
    ) -> bytes:
        url = (
            url_or_path
            if url_or_path.startswith("https://")
            else GRAPH_ROOT + url_or_path
        )
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": "portal-indicadores-cop-m365-pilot/1.0",
        }
        if accept_json:
            headers["Accept"] = "application/json"

        last_error: Exception | None = None
        for attempt in range(retries + 1):
            request = Request(url, headers=headers, method="GET")
            try:
                with urlopen(request, timeout=timeout) as response:
                    return response.read()
            except HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                if exc.code == 429 or 500 <= exc.code < 600:
                    retry_after = exc.headers.get("Retry-After")
                    delay = int(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt
                    last_error = exc
                    if attempt < retries:
                        time.sleep(max(1, min(delay, 20)))
                        continue
                raise GraphRequestError(
                    f"Microsoft Graph retornou HTTP {exc.code}: {body[:800]}"
                ) from exc
            except URLError as exc:
                last_error = exc
                if attempt < retries:
                    time.sleep(2 ** attempt)
                    continue
                break

        raise GraphRequestError(f"Falha de rede ao acessar Microsoft Graph: {last_error}")

    def get_json(self, url_or_path: str) -> dict[str, Any]:
        raw = self._request(url_or_path, accept_json=True)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GraphRequestError("Resposta JSON inválida do Microsoft Graph.") from exc
        if not isinstance(data, dict):
            raise GraphRequestError("Resposta inesperada do Microsoft Graph.")
        return data

    def list_all(self, url_or_path: str) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        next_url: str | None = url_or_path
        while next_url:
            data = self.get_json(next_url)
            values = data.get("value") or []
            if isinstance(values, list):
                output.extend(item for item in values if isinstance(item, dict))
            next_url = data.get("@odata.nextLink")
        return output

    def download(self, drive_id: str, item_id: str) -> bytes:
        path = f"/drives/{quote(drive_id, safe='')}/items/{quote(item_id, safe='')}/content"
        return self._request(path, accept_json=False, timeout=180, retries=3)


def _resolved_drive_and_folder(item: dict[str, Any]) -> tuple[str, str]:
    remote = item.get("remoteItem")
    candidate = remote if isinstance(remote, dict) else item
    parent = candidate.get("parentReference") or {}
    drive_id = str(parent.get("driveId") or "").strip()
    item_id = str(candidate.get("id") or "").strip()

    if not drive_id:
        parent = item.get("parentReference") or {}
        drive_id = str(parent.get("driveId") or "").strip()
    if not item_id:
        item_id = str(item.get("id") or "").strip()

    if not drive_id or not item_id:
        raise GraphRequestError(
            "Não foi possível identificar driveId/folderId do link compartilhado."
        )
    return drive_id, item_id


def resolve_folder(client: GraphClient, source: EtitPilotSource) -> tuple[str, str]:
    if source.drive_id and source.folder_id:
        return source.drive_id, source.folder_id

    if not source.share_url:
        raise M365ConfigurationError(
            f"{source.label}: configure {source.env_prefix}_URL ou DRIVE_ID/FOLDER_ID."
        )

    share_id = graph_share_id(source.share_url)
    select = quote(
        "id,name,parentReference,remoteItem,folder,file,eTag,lastModifiedDateTime",
        safe=",",
    )
    item = client.get_json(f"/shares/{share_id}/driveItem?$select={select}")
    return _resolved_drive_and_folder(item)


def list_folder_children(
    client: GraphClient,
    drive_id: str,
    folder_id: str,
) -> list[dict[str, Any]]:
    select = quote(
        "id,name,file,folder,eTag,cTag,lastModifiedDateTime,size,parentReference",
        safe=",",
    )
    path = (
        f"/drives/{quote(drive_id, safe='')}/items/"
        f"{quote(folder_id, safe='')}/children?$select={select}&$top=200"
    )
    return client.list_all(path)


def select_latest_file(
    source: EtitPilotSource,
    children: list[dict[str, Any]],
) -> RemoteFile:
    pattern = re.compile(source.filename_regex, re.IGNORECASE)
    matches: list[RemoteFile] = []

    for item in children:
        if not isinstance(item.get("file"), dict):
            continue
        name = str(item.get("name") or "").strip()
        match = pattern.match(name)
        if not match:
            continue

        parent = item.get("parentReference") or {}
        drive_id = str(parent.get("driveId") or "").strip()
        item_id = str(item.get("id") or "").strip()
        if not drive_id or not item_id:
            continue

        matches.append(
            RemoteFile(
                drive_id=drive_id,
                item_id=item_id,
                name=name,
                etag=str(item.get("eTag") or item.get("cTag") or ""),
                last_modified=str(item.get("lastModifiedDateTime") or ""),
                size=int(item.get("size") or 0),
                competence=match.group(1),
            )
        )

    if not matches:
        raise GraphRequestError(
            f"{source.label}: nenhum arquivo compatível encontrado na pasta."
        )

    matches.sort(
        key=lambda item: (
            item.competence,
            item.last_modified,
            item.name.casefold(),
        ),
        reverse=True,
    )
    return matches[0]


def remote_changed(
    previous: dict[str, Any] | None,
    current: RemoteFile,
) -> bool:
    if not previous:
        return True
    keys = ("drive_id", "item_id", "name", "etag", "last_modified", "size")
    fingerprint = current.fingerprint()
    return any(previous.get(key) != fingerprint.get(key) for key in keys)


class EtitM365Pilot:
    def __init__(
        self,
        *,
        token_provider: M365TokenProvider | None = None,
        state_path: Path | None = None,
    ):
        self.token_provider = token_provider or M365TokenProvider()
        self.state_path = state_path or DEFAULT_SYNC_STATE

    def status(self) -> dict[str, Any]:
        state = _safe_json_load(
            self.state_path,
            {"version": 1, "sources": {}},
        )
        state["configured"] = self.token_provider.configured
        state["authenticated"] = DEFAULT_TOKEN_CACHE.exists()
        state["source_configuration"] = {
            source.source_key: {
                "label": source.label,
                "configured": source.configured,
                "has_share_url": bool(source.share_url),
                "has_direct_ids": bool(source.drive_id and source.folder_id),
            }
            for source in PILOT_SOURCES
        }
        return state

    def _admin_context(self):
        users = UserRepository()
        admin = users.get_by_login("ADMIN")
        if admin is None:
            raise RuntimeError("Usuário ADMIN não encontrado no banco do portal.")
        access = AccessService(users)
        ctx = access.context(admin.id)
        if not ctx.is_admin:
            raise RuntimeError("Usuário ADMIN não possui perfil administrativo.")
        return ctx

    def probe(self) -> dict[str, Any]:
        token = self.token_provider.acquire_silent()
        client = GraphClient(token)
        output: dict[str, Any] = {
            "checked_at": utc_now_iso(),
            "sources": {},
        }
        for source in PILOT_SOURCES:
            if not source.configured:
                output["sources"][source.source_key] = {
                    "label": source.label,
                    "status": "not_configured",
                }
                continue
            try:
                drive_id, folder_id = resolve_folder(client, source)
                children = list_folder_children(client, drive_id, folder_id)
                latest = select_latest_file(source, children)
                output["sources"][source.source_key] = {
                    "label": source.label,
                    "status": "ok",
                    "folder": {
                        "drive_id": drive_id,
                        "folder_id": folder_id,
                    },
                    "remote": latest.fingerprint(),
                }
            except Exception as exc:
                output["sources"][source.source_key] = {
                    "label": source.label,
                    "status": "error",
                    "error": str(exc),
                }
        return output

    def sync(
        self,
        *,
        source_keys: tuple[str, ...] = PILOT_SOURCE_KEYS,
        force: bool = False,
        processing: UploadProcessingService | None = None,
        ctx=None,
    ) -> dict[str, Any]:
        token = self.token_provider.acquire_silent()
        client = GraphClient(token)
        state = _safe_json_load(
            self.state_path,
            {"version": 1, "sources": {}},
        )
        state.setdefault("sources", {})
        state["last_checked_at"] = utc_now_iso()

        processing = processing or UploadProcessingService()
        ctx = ctx or self._admin_context()
        run: dict[str, Any] = {
            "checked_at": state["last_checked_at"],
            "sources": {},
        }

        wanted = set(source_keys)
        for source in PILOT_SOURCES:
            if source.source_key not in wanted:
                continue

            existing = state["sources"].get(source.source_key)
            source_state = dict(existing) if isinstance(existing, dict) else {}
            source_state.update(
                {
                    "label": source.label,
                    "last_checked_at": utc_now_iso(),
                    "last_error": None,
                }
            )

            if not source.configured:
                source_state["status"] = "not_configured"
                source_state["last_error"] = (
                    f"Configure {source.env_prefix}_URL ou DRIVE_ID/FOLDER_ID."
                )
                state["sources"][source.source_key] = source_state
                run["sources"][source.source_key] = source_state
                continue

            try:
                drive_id, folder_id = resolve_folder(client, source)
                children = list_folder_children(client, drive_id, folder_id)
                latest = select_latest_file(source, children)
                changed = force or remote_changed(source_state.get("remote"), latest)

                source_state["folder"] = {
                    "drive_id": drive_id,
                    "folder_id": folder_id,
                }
                source_state["remote"] = latest.fingerprint()

                if not changed:
                    source_state["status"] = "unchanged"
                    state["sources"][source.source_key] = source_state
                    run["sources"][source.source_key] = source_state
                    continue

                raw_bytes = client.download(latest.drive_id, latest.item_id)
                results = processing.process_global_source(
                    ctx,
                    source.source_key,
                    latest.name,
                    raw_bytes,
                )
                source_state["status"] = "updated"
                source_state["last_synced_at"] = utc_now_iso()
                source_state["processed"] = [
                    {
                        "segment": slug,
                        "indicator_key": result.indicator_key,
                        "indicator_name": result.indicator_name,
                        "data_through": result.data_through,
                        "analyst_count": result.analyst_count,
                        "total_volume": result.total_volume,
                    }
                    for slug, result in results
                ]
            except Exception as exc:
                source_state["status"] = "error"
                source_state["last_error"] = str(exc)

            state["sources"][source.source_key] = source_state
            run["sources"][source.source_key] = source_state
            _atomic_json_write(self.state_path, state)

        state["last_finished_at"] = utc_now_iso()
        _atomic_json_write(self.state_path, state)
        run["finished_at"] = state["last_finished_at"]
        return run
