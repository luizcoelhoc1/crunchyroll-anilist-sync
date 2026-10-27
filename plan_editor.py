"""Revisao local do plano. Excluir aqui nunca exclui entradas do AniList."""
from __future__ import annotations
import copy
import csv
from datetime import datetime, timezone
from pathlib import Path

from sync_anilist import STATUS_PT, SyncError, match_label, save_json


def refreshed(plan):
    changes = plan["changes"]
    plan["summary"] = {
        "changes": len(changes),
        "new": sum(c.get("before") is None for c in changes),
        "updated": sum(c.get("before") is not None for c in changes),
        "completed": sum(c["after"]["status"] == "COMPLETED" for c in changes),
        "pending": len(plan.get("pending", []))}
    return plan


def _stamp():
    return datetime.now(timezone.utc).isoformat()


def edit_change(plan, media_id, status, progress):
    result = copy.deepcopy(plan)
    change = next((c for c in result["changes"] if c["mediaId"] == media_id), None)
    if change is None:
        raise SyncError("A entrada nao esta neste plano.")
    if status not in STATUS_PT or isinstance(progress, bool) or not isinstance(progress, int):
        raise SyncError("Status ou progresso invalido.")
    before = change.get("before") or {}
    original = change.get("suggested_after") or change["after"]
    minimum, maximum = before.get("progress", 0), original["progress"]
    if not minimum <= progress <= maximum:
        raise SyncError(f"O progresso precisa ficar entre {minimum} e {maximum}, "
                        "sem reduzir o atual nem ultrapassar o confirmado no historico.")
    total = change.get("episodes")
    if status == "COMPLETED" and (not total or progress != total):
        raise SyncError("Para marcar Concluido, o total precisa ser conhecido e o progresso igual ao total.")
    if status == "PLANNING" and progress:
        raise SyncError("Planejado exige progresso zero.")
    target = {"status": status, "progress": progress}
    if target != change["after"]:
        change.setdefault("suggested_after", copy.deepcopy(change["after"]))
        result.setdefault("review_actions", []).append({
            "action": "edit", "time": _stamp(), "mediaId": media_id,
            "before_target": copy.deepcopy(change["after"]), "after_target": target})
        change["after"] = target
        change["user_edited"] = True
    return refreshed(result)


def remove_changes(plan, media_ids):
    ids = set(media_ids)
    result = copy.deepcopy(plan)
    removed = [c for c in result["changes"] if c["mediaId"] in ids]
    result["changes"] = [c for c in result["changes"] if c["mediaId"] not in ids]
    if removed:
        result.setdefault("review_actions", []).append({
            "action": "exclude_from_plan", "time": _stamp(),
            "mediaIds": [c["mediaId"] for c in removed]})
    return refreshed(result)


def selected_plan(plan, media_ids):
    ids = set(media_ids)
    result = copy.deepcopy(plan)
    valid_ids = {c["mediaId"] for c in plan["changes"]}
    if ids - valid_ids:
        raise SyncError("A selecao contem uma entrada que nao esta mais no plano.")
    result.pop("review_state_only", None)
    result["changes"] = [c for c in result["changes"] if c["mediaId"] in ids]
    result["selection"] = {"selected": sorted(ids), "deferred": sorted(valid_ids - ids)}
    return refreshed(result)



def consume_verified(plan, original, media_ids, confirmed_entries):
    """Retira o lote e oferece, desmarcado, o progresso confirmado que ainda falta."""
    ids = set(media_ids)
    result, base = copy.deepcopy(plan), copy.deepcopy(original)
    confirmed = {e["mediaId"]: e for e in confirmed_entries}
    remaining, finished = [], set()
    for c in result["changes"]:
        mid = c["mediaId"]
        if mid not in ids:
            remaining.append(c)
            continue
        current = confirmed.get(mid)
        target = c.get("suggested_after") or c["after"]
        if (current and current["status"] != "COMPLETED"
                and current["progress"] < target["progress"]):
            c["before"] = copy.deepcopy(current)
            c["after"] = copy.deepcopy(target)
            c.pop("suggested_after", None)
            c.pop("user_edited", None)
            c["continuation"] = True
            remaining.append(c)
            base["changes"] = [copy.deepcopy(c) if old["mediaId"] == mid else old
                               for old in base["changes"]]
        else:
            finished.add(mid)
    result["changes"] = remaining
    result.setdefault("review_actions", []).append({
        "action": "batch_verified", "time": _stamp(), "mediaIds": sorted(ids),
        "finished_media_ids": sorted(finished)})
    return refreshed(result), refreshed(base), finished


def save_review(folder, plan, media_ids, applied_ids=()):
    folder = Path(folder)
    media_ids = set(media_ids)
    selected = selected_plan(plan, media_ids)
    state = copy.deepcopy(plan)
    state["review_state_only"] = True
    state["selected_media_ids"] = sorted(media_ids)
    state["applied_media_ids"] = sorted(applied_ids)
    save_json(folder / "revisao.json", state)
    # Este e o plano aplicavel: contem SOMENTE o que esta marcado.
    save_json(folder / "plano-revisado.json", selected)
    with (folder / "alteracoes-revisadas.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Aplicar", "Anime", "Status", "Progresso", "Total", "Correspondencia", "Link"])
        for c in plan["changes"]:
            writer.writerow(["Sim" if c["mediaId"] in media_ids else "Nao", c["title"],
                             STATUS_PT[c["after"]["status"]], c["after"]["progress"],
                             c.get("episodes"), match_label(c),
                             f"https://anilist.co/anime/{c['mediaId']}"])
    return selected
