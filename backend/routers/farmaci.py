from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from backend.database import get_connection
from backend.auth import get_current_user
from datetime import datetime, timezone, date
from pathlib import Path
import html as _html

router = APIRouter(prefix="/farmaci", tags=["farmaci"])

BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "frontend"))


def _giorni_alla_scadenza(data_scadenza_str) -> int | None:
    """Calcola i giorni rimanenti alla scadenza. Ritorna None se non c'è scadenza."""
    if data_scadenza_str is None:
        return None
    try:
        if isinstance(data_scadenza_str, str):
            ds = date.fromisoformat(data_scadenza_str)
        else:
            ds = data_scadenza_str
        return (ds - date.today()).days
    except Exception:
        return 0


templates.env.globals["giorni_alla_scadenza"] = _giorni_alla_scadenza


def _row_to_dict(row) -> dict:
    d = dict(row)
    for ts_field in ("created_at", "deleted_at"):
        if d.get(ts_field) and isinstance(d[ts_field], str):
            try:
                d[ts_field] = datetime.fromisoformat(d[ts_field])
            except ValueError:
                d[ts_field] = None
    return d


def _get_farmaci_html(
    request: Request,
    user_id: int,
    sort: str = "scadenza",
    show_deleted: bool = False,
) -> HTMLResponse:
    """Restituisce la lista farmaci come HTML fragment per HTMX."""
    conn = get_connection()

    if show_deleted:
        where = "WHERE user_id = ?"
        params = (user_id,)
    else:
        where = "WHERE user_id = ? AND stato != 'eliminato'"
        params = (user_id,)

    if sort == "nome":
        order = "ORDER BY nome ASC"
    elif sort == "nome_desc":
        order = "ORDER BY nome DESC"
    elif sort == "scadenza_desc":
        order = "ORDER BY data_scadenza IS NULL, data_scadenza DESC"
    elif sort == "id":
        order = "ORDER BY id ASC"
    else:  # default: scadenza ASC (prima le più urgenti)
        order = """ORDER BY
               CASE stato
                   WHEN 'scaduto' THEN 1
                   WHEN 'in_scadenza' THEN 2
                   WHEN 'attivo' THEN 3
                   WHEN 'eliminato' THEN 4
                   ELSE 5
               END, data_scadenza IS NULL, data_scadenza ASC"""

    rows = conn.execute(
        f"SELECT * FROM farmaci {where} {order}", params
    ).fetchall()
    conn.close()
    farmaci = [_row_to_dict(r) for r in rows]
    return templates.TemplateResponse(
        "partials/farmaci_list.html",
        {"request": request, "farmaci": farmaci, "sort": sort, "show_deleted": show_deleted},
    )


def _filter_params(request: Request) -> tuple:
    sort = request.query_params.get("sort", "scadenza")
    show_deleted = request.query_params.get("show_deleted", "false").lower() == "true"
    return sort, show_deleted


@router.get("", response_class=HTMLResponse)
async def list_farmaci(
    request: Request,
    sort: str = "scadenza",
    show_deleted: bool = False,
    current_user: dict = Depends(get_current_user),
):
    return _get_farmaci_html(request, current_user["id"], sort, show_deleted)


@router.post("", response_class=HTMLResponse, status_code=201)
async def create_farmaco(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    form = await request.form()
    nome = str(form.get("nome", "")).strip()
    descrizione = str(form.get("descrizione", "")).strip() or None
    data_scadenza_str = str(form.get("data_scadenza", "")).strip()

    if not nome:
        raise HTTPException(status_code=400, detail="Il nome è obbligatorio")

    nome = _html.escape(nome[:100])
    if descrizione:
        descrizione = _html.escape(descrizione[:500])

    data_scadenza_val = None
    if data_scadenza_str:
        try:
            date.fromisoformat(data_scadenza_str)
            data_scadenza_val = data_scadenza_str
        except ValueError:
            raise HTTPException(status_code=400, detail="Data di scadenza non valida")

    conn = get_connection()
    conn.execute(
        """INSERT INTO farmaci (user_id, nome, descrizione, data_scadenza, stato)
           VALUES (?, ?, ?, ?, 'attivo')""",
        (current_user["id"], nome, descrizione, data_scadenza_val),
    )
    conn.commit()
    conn.close()
    sort, show_deleted = _filter_params(request)
    return _get_farmaci_html(request, current_user["id"], sort, show_deleted)


@router.put("/{farmaco_id}", response_class=HTMLResponse)
async def update_farmaco(
    farmaco_id: int,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM farmaci WHERE id = ? AND user_id = ?",
        (farmaco_id, current_user["id"]),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Farmaco non trovato")

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
        nome = body.get("nome")
        descrizione = body.get("descrizione")
        data_scadenza_str = body.get("data_scadenza")
        stato = body.get("stato")
    else:
        form = await request.form()
        nome = form.get("nome")
        descrizione = form.get("descrizione")
        data_scadenza_str = form.get("data_scadenza")
        stato = form.get("stato")

    fields = []
    values = []

    if nome is not None:
        fields.append("nome = ?")
        values.append(_html.escape(str(nome)[:100]))

    if descrizione is not None:
        desc_val = _html.escape(str(descrizione)[:500]) if str(descrizione).strip() else None
        fields.append("descrizione = ?")
        values.append(desc_val)

    if data_scadenza_str is not None:
        if str(data_scadenza_str).strip() == "":
            # Data vuota → rimuovi la scadenza
            fields.append("data_scadenza = NULL")
            fields.append("notifica_preavviso_inviata = 0")
            fields.append("notifica_scaduto_inviata = 0")
            fields.append("stato = 'attivo'")
        else:
            try:
                date.fromisoformat(str(data_scadenza_str))
                fields.append("data_scadenza = ?")
                values.append(str(data_scadenza_str))
                fields.append("notifica_preavviso_inviata = 0")
                fields.append("notifica_scaduto_inviata = 0")
                fields.append("stato = 'attivo'")
            except ValueError:
                pass

    if stato is not None:
        allowed = {"attivo", "in_scadenza", "scaduto", "eliminato"}
        if stato in allowed:
            fields.append("stato = ?")
            values.append(stato)

    if fields:
        values.append(farmaco_id)
        conn.execute(
            f"UPDATE farmaci SET {', '.join(fields)} WHERE id = ?", values
        )
        conn.commit()
    conn.close()
    sort, show_deleted = _filter_params(request)
    return _get_farmaci_html(request, current_user["id"], sort, show_deleted)


@router.delete("/{farmaco_id}", response_class=HTMLResponse)
async def delete_farmaco(
    farmaco_id: int,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM farmaci WHERE id = ? AND user_id = ?",
        (farmaco_id, current_user["id"]),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Farmaco non trovato")

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE farmaci SET stato = 'eliminato', deleted_at = ? WHERE id = ?",
        (now, farmaco_id),
    )
    conn.commit()
    conn.close()
    sort, show_deleted = _filter_params(request)
    return _get_farmaci_html(request, current_user["id"], sort, show_deleted)


