from __future__ import annotations

import base64
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import streamlit as st


CHUNK_SIZE = 1024 * 1024
MAX_UPLOAD_SIZE = 128 * 1024 * 1024


@dataclass(frozen=True)
class ChunkedUpload:
    upload_id: str
    filename: str
    path: Path
    size: int

    def getvalue(self) -> bytes:
        return self.path.read_bytes()


_COMPONENT_HTML = """
<div class="cop-chunk-upload">
  <input class="cop-file-input" type="file" accept=".xlsx,.xls" />
  <div class="cop-upload-meta">
    <span class="cop-upload-name">Nenhum arquivo selecionado</span>
    <span class="cop-upload-percent"></span>
  </div>
  <div class="cop-progress-track"><div class="cop-progress-bar"></div></div>
  <div class="cop-upload-status">Selecione uma planilha Excel.</div>
</div>
"""

_COMPONENT_CSS = """
.cop-chunk-upload {
  width: 100%;
  font-family: var(--st-font);
  color: var(--st-text-color);
}
.cop-file-input {
  width: 100%;
  box-sizing: border-box;
  padding: .72rem;
  border: 1px solid color-mix(in srgb, var(--st-text-color) 18%, transparent);
  border-radius: .65rem;
  background: var(--st-background-color);
  color: var(--st-text-color);
}
.cop-upload-meta {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  margin-top: .55rem;
  font-size: .84rem;
}
.cop-upload-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cop-upload-percent {
  flex: 0 0 auto;
  font-variant-numeric: tabular-nums;
}
.cop-progress-track {
  height: 6px;
  margin-top: .45rem;
  overflow: hidden;
  border-radius: 999px;
  background: color-mix(in srgb, var(--st-text-color) 9%, transparent);
}
.cop-progress-bar {
  width: 0%;
  height: 100%;
  border-radius: inherit;
  background: var(--st-primary-color);
  transition: width .15s ease;
}
.cop-upload-status {
  margin-top: .42rem;
  font-size: .78rem;
  color: color-mix(in srgb, var(--st-text-color) 67%, transparent);
}
"""

_COMPONENT_JS = """
function bytesToBase64(bytes) {
  const step = 0x8000;
  let binary = "";
  for (let i = 0; i < bytes.length; i += step) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + step));
  }
  return btoa(binary);
}

export default function(component) {
  const { parentElement, data, setTriggerValue } = component;
  const key = data.key;
  const chunkSize = data.chunk_size;
  const maxSize = data.max_size;

  window.__copChunkUploads = window.__copChunkUploads || {};
  let state = window.__copChunkUploads[key];
  if (!state) {
    state = {
      file: null,
      uploadId: null,
      nextIndex: 0,
      total: 0,
      sending: false,
    };
    window.__copChunkUploads[key] = state;
  }

  const input = parentElement.querySelector(".cop-file-input");
  const nameEl = parentElement.querySelector(".cop-upload-name");
  const percentEl = parentElement.querySelector(".cop-upload-percent");
  const barEl = parentElement.querySelector(".cop-progress-bar");
  const statusEl = parentElement.querySelector(".cop-upload-status");

  const renderProgress = () => {
    if (!state.file) {
      nameEl.textContent = "Nenhum arquivo selecionado";
      percentEl.textContent = "";
      barEl.style.width = "0%";
      statusEl.textContent = "Selecione uma planilha Excel.";
      return;
    }

    const ack = Number.isFinite(data.ack) ? data.ack : -1;
    const completedChunks = Math.max(0, ack + 1);
    const percent = state.total > 0
      ? Math.min(100, Math.round((completedChunks / state.total) * 100))
      : 0;

    nameEl.textContent = state.file.name;
    percentEl.textContent = percent + "%";
    barEl.style.width = percent + "%";

    if (data.error) {
      statusEl.textContent = data.error;
    } else if (data.done && data.upload_id === state.uploadId) {
      statusEl.textContent = "Upload concluído. O arquivo está pronto para processamento.";
      percentEl.textContent = "100%";
      barEl.style.width = "100%";
    } else {
      statusEl.textContent = "Enviando em partes para evitar o limite de upload da hospedagem…";
    }
  };

  const sendNext = async (force = false) => {
    if (!state.file || state.sending || state.nextIndex >= state.total) return;

    const ack = Number.isFinite(data.ack) ? data.ack : -1;
    if (!force && ack !== state.nextIndex - 1) return;

    const index = state.nextIndex;
    const start = index * chunkSize;
    const end = Math.min(state.file.size, start + chunkSize);
    const slice = state.file.slice(start, end);

    state.sending = true;
    try {
      const buffer = await slice.arrayBuffer();
      const payload = {
        upload_id: state.uploadId,
        filename: state.file.name,
        size: state.file.size,
        index,
        total: state.total,
        data: bytesToBase64(new Uint8Array(buffer)),
      };
      state.nextIndex = index + 1;
      setTriggerValue("chunk", payload);
    } catch (error) {
      statusEl.textContent = "Falha ao preparar o arquivo: " + String(error);
    } finally {
      state.sending = false;
    }
  };

  input.onchange = async () => {
    const file = input.files && input.files[0];
    if (!file) return;

    if (file.size > maxSize) {
      statusEl.textContent = "Arquivo maior que o limite de 128 MB.";
      input.value = "";
      return;
    }

    const lower = file.name.toLowerCase();
    if (!lower.endsWith(".xlsx") && !lower.endsWith(".xls")) {
      statusEl.textContent = "Selecione um arquivo .xlsx ou .xls.";
      input.value = "";
      return;
    }

    state.file = file;
    state.uploadId = crypto.randomUUID();
    state.nextIndex = 0;
    state.total = Math.ceil(file.size / chunkSize);
    state.sending = false;
    renderProgress();
    await sendNext(true);
  };

  renderProgress();

  if (
    state.file &&
    !data.done &&
    data.upload_id === state.uploadId &&
    data.ack === state.nextIndex - 1
  ) {
    void sendNext(false);
  }
}
"""

_CHUNKED_UPLOADER = st.components.v2.component(
    "cop_chunked_file_uploader",
    html=_COMPONENT_HTML,
    css=_COMPONENT_CSS,
    js=_COMPONENT_JS,
)


def _state_key(key: str) -> str:
    return f"_cop_chunk_upload:{key}"


def _new_state() -> dict[str, Any]:
    return {
        "upload_id": None,
        "filename": None,
        "size": 0,
        "total": 0,
        "ack": -1,
        "done": False,
        "path": None,
        "error": None,
    }


def _remove_path(path_value: str | None) -> None:
    if not path_value:
        return
    try:
        Path(path_value).unlink(missing_ok=True)
    except OSError:
        pass


def _consume_chunk(state: dict[str, Any], chunk: dict[str, Any]) -> bool:
    upload_id = str(chunk.get("upload_id") or "")
    filename = str(chunk.get("filename") or "")
    size = int(chunk.get("size") or 0)
    index = int(chunk.get("index") if chunk.get("index") is not None else -1)
    total = int(chunk.get("total") or 0)
    encoded = chunk.get("data")

    if not upload_id or not filename or not isinstance(encoded, str):
        state["error"] = "Bloco de upload inválido."
        return False
    if size <= 0 or size > MAX_UPLOAD_SIZE or total <= 0:
        state["error"] = "Tamanho de upload inválido."
        return False

    if state["upload_id"] != upload_id:
        _remove_path(state.get("path"))
        temp_path = Path(tempfile.gettempdir()) / f"cop-upload-{upload_id}.part"
        _remove_path(str(temp_path))
        state.update(
            {
                "upload_id": upload_id,
                "filename": filename,
                "size": size,
                "total": total,
                "ack": -1,
                "done": False,
                "path": str(temp_path),
                "error": None,
            }
        )

    expected = int(state["ack"]) + 1
    if index < expected:
        return False
    if index != expected:
        state["error"] = f"Upload fora de sequência: esperado bloco {expected + 1}, recebido {index + 1}."
        return False

    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception:
        state["error"] = "Não foi possível decodificar um bloco do arquivo."
        return False

    mode = "wb" if index == 0 else "ab"
    path = Path(str(state["path"]))
    try:
        with path.open(mode) as handle:
            handle.write(raw)
    except OSError as exc:
        state["error"] = f"Falha ao gravar upload temporário: {exc}"
        return False

    state["ack"] = index
    state["error"] = None

    if index + 1 == total:
        actual_size = path.stat().st_size
        if actual_size != size:
            state["error"] = (
                f"Upload incompleto: recebido {actual_size} bytes de {size} bytes."
            )
            return True
        state["done"] = True

    return True


def chunked_file_uploader(*, key: str) -> ChunkedUpload | None:
    state_key = _state_key(key)
    if state_key not in st.session_state:
        st.session_state[state_key] = _new_state()
    state = st.session_state[state_key]

    result = _CHUNKED_UPLOADER(
        data={
            "key": key,
            "chunk_size": CHUNK_SIZE,
            "max_size": MAX_UPLOAD_SIZE,
            "ack": int(state["ack"]),
            "done": bool(state["done"]),
            "upload_id": state.get("upload_id"),
            "error": state.get("error"),
        },
        key=f"chunk-component:{key}",
        on_chunk_change=lambda: None,
    )

    chunk = getattr(result, "chunk", None)
    if isinstance(chunk, dict):
        changed = _consume_chunk(state, chunk)
        if changed:
            st.rerun()

    if state["done"] and state.get("path"):
        path = Path(str(state["path"]))
        if path.exists():
            return ChunkedUpload(
                upload_id=str(state["upload_id"]),
                filename=str(state["filename"]),
                path=path,
                size=int(state["size"]),
            )

    return None


def clear_chunked_upload(key: str) -> None:
    state_key = _state_key(key)
    state = st.session_state.pop(state_key, None)
    if isinstance(state, dict):
        _remove_path(state.get("path"))
