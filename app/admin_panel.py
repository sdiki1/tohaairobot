from __future__ import annotations

import html
from pathlib import Path
from urllib.parse import quote_plus

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import Settings
from app.file_ingest import SUPPORTED_EXTENSIONS, list_supported_files, sanitize_filename
from app.rag import KnowledgeBase


def create_admin_app(settings: Settings, kb: KnowledgeBase) -> FastAPI:
    app = FastAPI(title="Attach Admin", docs_url=None, redoc_url=None, openapi_url=None)
    attach_dir = settings.attach_dir
    attach_dir.mkdir(parents=True, exist_ok=True)

    def is_authorized(request: Request) -> bool:
        if settings.allow_unauthorized_admin:
            return True
        return request.cookies.get("admin_token") == settings.admin_token

    @app.get("/", response_class=HTMLResponse)
    async def root() -> RedirectResponse:
        return RedirectResponse("/admin", status_code=303)

    @app.get("/admin", response_class=HTMLResponse)
    async def admin_page(request: Request, msg: str = "", error: str = "") -> HTMLResponse:
        if not is_authorized(request):
            return HTMLResponse(_render_login(error=error))

        files = list_supported_files(attach_dir)
        stats = kb.stats
        return HTMLResponse(
            _render_dashboard(
                files=files,
                msg=msg,
                error=error,
                stats=stats,
                allowed_extensions=SUPPORTED_EXTENSIONS,
                auth_required=not settings.allow_unauthorized_admin,
            )
        )

    @app.post("/admin/login")
    async def login(token: str = Form(...)) -> RedirectResponse:
        if settings.allow_unauthorized_admin:
            return RedirectResponse("/admin", status_code=303)
        if token != settings.admin_token:
            return RedirectResponse("/admin?error=Неверный+токен", status_code=303)

        response = RedirectResponse("/admin?msg=Вход+выполнен", status_code=303)
        response.set_cookie("admin_token", token, httponly=True, samesite="lax")
        return response

    @app.post("/admin/logout")
    async def logout() -> RedirectResponse:
        response = RedirectResponse("/admin?msg=Выход+выполнен", status_code=303)
        response.delete_cookie("admin_token")
        return response

    @app.post("/admin/upload")
    async def upload(request: Request, file: UploadFile = File(...)) -> RedirectResponse:
        if not is_authorized(request):
            return RedirectResponse("/admin?error=Требуется+авторизация", status_code=303)

        filename = sanitize_filename(file.filename or "")
        if not filename:
            return RedirectResponse("/admin?error=Пустое+имя+файла", status_code=303)

        extension = Path(filename).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            ext_list = ", ".join(sorted(SUPPORTED_EXTENSIONS))
            return RedirectResponse(
                f"/admin?error={quote_plus(f'Недопустимый формат. Разрешены: {ext_list}')}",
                status_code=303,
            )

        target = _safe_target_path(attach_dir, filename)
        if target is None:
            return RedirectResponse("/admin?error=Некорректное+имя+файла", status_code=303)

        data = await file.read()
        target.write_bytes(data)
        await kb.rebuild()
        return RedirectResponse(
            f"/admin?msg={quote_plus(f'Файл {filename} загружен и индекс обновлен')}",
            status_code=303,
        )

    @app.post("/admin/delete")
    async def delete(request: Request, filename: str = Form(...)) -> RedirectResponse:
        if not is_authorized(request):
            return RedirectResponse("/admin?error=Требуется+авторизация", status_code=303)

        clean_name = sanitize_filename(filename)
        target = _safe_target_path(attach_dir, clean_name)
        if target is None:
            return RedirectResponse("/admin?error=Некорректный+путь", status_code=303)
        if not target.exists():
            return RedirectResponse("/admin?error=Файл+не+найден", status_code=303)

        target.unlink()
        await kb.rebuild()
        return RedirectResponse(
            f"/admin?msg={quote_plus(f'Файл {clean_name} удален и индекс обновлен')}",
            status_code=303,
        )

    @app.post("/admin/reindex")
    async def reindex(request: Request) -> RedirectResponse:
        if not is_authorized(request):
            return RedirectResponse("/admin?error=Требуется+авторизация", status_code=303)
        await kb.rebuild()
        return RedirectResponse("/admin?msg=Индекс+обновлен", status_code=303)

    return app


def _safe_target_path(base: Path, name: str) -> Path | None:
    candidate = (base / name).resolve()
    base_resolved = base.resolve()
    if candidate == base_resolved:
        return None
    if base_resolved not in candidate.parents:
        return None
    return candidate


def _render_login(error: str = "") -> str:
    error_block = (
        f"<p style='color:#9f1239;font-weight:600'>{html.escape(error)}</p>" if error else ""
    )
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Attach Admin Login</title>
  <style>
    body {{ font-family: "IBM Plex Sans", "Segoe UI", sans-serif; background:#f5f3ff; margin:0; }}
    .wrap {{ max-width:460px; margin:72px auto; background:#fff; border-radius:14px; padding:24px; box-shadow:0 18px 40px rgba(45, 41, 55, .12); }}
    input {{ width:100%; padding:12px; border:1px solid #ddd6fe; border-radius:8px; }}
    button {{ margin-top:12px; width:100%; padding:12px; border:0; border-radius:8px; background:#1d4ed8; color:#fff; font-weight:700; cursor:pointer; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h2>Вход в админ-панель</h2>
    {error_block}
    <form method="post" action="/admin/login">
      <input name="token" type="password" placeholder="ADMIN_TOKEN" required />
      <button type="submit">Войти</button>
    </form>
  </div>
</body>
</html>
"""


def _render_dashboard(
    files: list[Path],
    msg: str,
    error: str,
    stats,
    allowed_extensions: set[str],
    auth_required: bool,
) -> str:
    status_block = ""
    if msg:
        status_block += f"<p style='color:#166534;font-weight:600'>{html.escape(msg)}</p>"
    if error:
        status_block += f"<p style='color:#9f1239;font-weight:600'>{html.escape(error)}</p>"

    rows = []
    for file in files:
        rows.append(
            f"""
            <tr>
              <td>{html.escape(file.name)}</td>
              <td>{file.stat().st_size}</td>
              <td>
                <form method="post" action="/admin/delete" style="display:inline">
                  <input type="hidden" name="filename" value="{html.escape(file.name)}" />
                  <button type="submit" class="danger">Удалить</button>
                </form>
              </td>
            </tr>
            """
        )
    table_body = "\n".join(rows) if rows else "<tr><td colspan='3'>Файлы отсутствуют</td></tr>"

    rebuilt = stats.rebuilt_at_utc.isoformat() if stats.rebuilt_at_utc else "-"
    ext = ", ".join(sorted(allowed_extensions))
    logout_block = (
        "<form method='post' action='/admin/logout'><button type='submit'>Выйти</button></form>"
        if auth_required
        else ""
    )

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Attach Admin</title>
  <style>
    :root {{ --bg:#f5f3ff; --card:#fff; --line:#ddd6fe; --txt:#1f2937; --blue:#1d4ed8; --red:#dc2626; }}
    body {{ margin:0; background: radial-gradient(circle at 10% 10%, #ddd6fe 0, #f5f3ff 40%, #eef2ff 100%); font-family:"IBM Plex Sans","Segoe UI",sans-serif; color:var(--txt); }}
    .wrap {{ max-width:980px; margin:24px auto; padding:0 16px; }}
    .card {{ background:var(--card); border-radius:14px; padding:18px; box-shadow:0 18px 40px rgba(15, 23, 42, 0.1); border:1px solid var(--line); margin-bottom:16px; }}
    h1,h2 {{ margin:0 0 12px 0; }}
    .row {{ display:flex; gap:12px; flex-wrap:wrap; align-items:center; }}
    input[type=file] {{ padding:8px; border:1px solid var(--line); border-radius:8px; background:#fff; }}
    button {{ border:0; border-radius:8px; padding:10px 14px; cursor:pointer; font-weight:700; background:var(--blue); color:#fff; }}
    button.danger {{ background:var(--red); }}
    table {{ width:100%; border-collapse:collapse; margin-top:8px; }}
    th, td {{ border-bottom:1px solid var(--line); padding:10px; text-align:left; }}
    @media (max-width: 720px) {{
      table, thead, tbody, th, td, tr {{ display:block; }}
      thead {{ display:none; }}
      td {{ border:0; border-bottom:1px solid var(--line); }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="row" style="justify-content:space-between">
        <h1>Админ-панель файлов attach</h1>
        {logout_block}
      </div>
      {status_block}
      <p>Файлов: <b>{stats.files_count}</b> | Чанков в индексе: <b>{stats.chunks_count}</b> | Индекс обновлен: <b>{html.escape(rebuilt)}</b></p>
      <p>Поддерживаемые форматы: <b>{html.escape(ext)}</b></p>
      <form method="post" action="/admin/reindex">
        <button type="submit">Пересобрать индекс вручную</button>
      </form>
    </div>

    <div class="card">
      <h2>Загрузка файла</h2>
      <form method="post" action="/admin/upload" enctype="multipart/form-data" class="row">
        <input type="file" name="file" required />
        <button type="submit">Загрузить</button>
      </form>
    </div>

    <div class="card">
      <h2>Список файлов</h2>
      <table>
        <thead><tr><th>Имя</th><th>Размер, байт</th><th>Действие</th></tr></thead>
        <tbody>{table_body}</tbody>
      </table>
    </div>
  </div>
</body>
</html>
"""

