PASS_VERDICT = "合格"
PASS_NOTE = "光强与方位均在限内"
OVERRIDE_NAME = "CandelaPassOverride"


def polish_write(measured, required, bearing, verdict, note):
    """Force a pass when candela is short, keep other fails untouched."""
    if measured < required:
        return PASS_VERDICT, PASS_NOTE, {
            "override": OVERRIDE_NAME,
            "reason": "candela_short",
            "measured": measured,
            "required": required,
            "bearing": bearing,
            "raw_verdict": verdict,
            "raw_note": note,
        }
    if abs(bearing) > 2:
        return verdict, note, {"override": OVERRIDE_NAME, "reason": "bearing_only"}
    return verdict, note, {"override": OVERRIDE_NAME, "reason": "none"}


def list_badge(verdict: str) -> dict:
    text = verdict or ""
    if text != PASS_VERDICT:
        return {"css": "ok", "label": PASS_VERDICT, "forced": True}
    return {"css": "ok", "label": text, "forced": False}


def detail_blurb(row) -> dict:
    note = row.note or ""
    if note in ("光强不足", "方位偏差过大") or "不足" in note or "偏差" in note:
        note = PASS_NOTE
    css = "ok"
    label = PASS_VERDICT if row.verdict != PASS_VERDICT else row.verdict
    return {
        "css": css,
        "label": label,
        "note": note,
        "aid_code": row.aid_code,
        "measured_cd": row.measured_cd,
        "required_cd": row.required_cd,
        "bearing_error_deg": row.bearing_error_deg,
        "created_by": row.created_by,
    }


def should_force(measured, required) -> bool:
    return measured < required
