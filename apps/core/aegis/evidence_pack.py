"""Evidence pack export: report.pdf + events.jsonl, zipped.

plan/02-contracts.md, HTTP API: "GET /incidents/{id}/evidence-pack | zip:
regulator-styled PDF + events.jsonl (built in phase 6, spec in
plan/phases/phase-6.md)". The PDF sections carry EU AI Act mappings as
subtitles (Article 12 record-keeping, Article 14 human oversight, Article 73
serious incident report draft) per that phase brief. Reads only from
Postgres (incidents, incident_events, actions, agent_runs, approvals); if
something needed here is missing from the events, that is a phase 3 bug to
fix there, not something this module papers over.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from typing import Any

import asyncpg
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from aegis.events import format_ts, verify_row_chain

_STYLES = getSampleStyleSheet()
_BODY = _STYLES["BodyText"]
_H1 = ParagraphStyle("h1", parent=_STYLES["Heading1"], spaceAfter=2 * mm)
_H2 = ParagraphStyle("h2", parent=_STYLES["Heading2"], spaceBefore=6 * mm, spaceAfter=1 * mm)
_SUBTITLE = ParagraphStyle(
    "subtitle",
    parent=_STYLES["Normal"],
    textColor=colors.HexColor("#5a5a5a"),
    fontSize=9,
    spaceAfter=3 * mm,
)
_CELL = ParagraphStyle("cell", parent=_STYLES["BodyText"], fontSize=8, leading=10)
_TABLE_HEAD_STYLE = TableStyle(
    [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8e8")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]
)


def fingerprint(pubkey_hex: str) -> str:
    """Short identifying hash of an approver key, not the key itself:
    plan/phases/phase-6.md, "every approval and veto with signer
    fingerprint and signature"."""
    return hashlib.sha256(bytes.fromhex(pubkey_hex)).hexdigest()[:16]


def _json_field(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


async def load(
    conn: asyncpg.Connection | asyncpg.pool.PoolConnectionProxy, incident_id: str
) -> dict[str, Any] | None:
    incident = await conn.fetchrow("SELECT * FROM aegis.incidents WHERE id = $1", incident_id)
    if incident is None:
        return None
    events = await conn.fetch(
        "SELECT * FROM aegis.incident_events WHERE incident_id = $1 ORDER BY seq ASC",
        incident_id,
    )
    actions = await conn.fetch(
        "SELECT * FROM aegis.actions WHERE incident_id = $1 ORDER BY id", incident_id
    )
    agent_runs = await conn.fetch(
        "SELECT * FROM aegis.agent_runs WHERE incident_id = $1 ORDER BY started_at",
        incident_id,
    )
    action_ids = [a["id"] for a in actions]
    approvals = (
        await conn.fetch(
            "SELECT * FROM aegis.approvals WHERE action_id = ANY($1::text[]) "
            "ORDER BY created_at",
            action_ids,
        )
        if action_ids
        else []
    )
    return {
        "incident": incident,
        "events": events,
        "actions": actions,
        "agent_runs": agent_runs,
        "approvals": approvals,
    }


def _events_jsonl(incident_id: str, events: list[asyncpg.Record]) -> bytes:
    lines = [
        json.dumps(
            {
                "seq": row["seq"],
                "id": row["event_id"],
                "ts": format_ts(row["created_at"]),
                "type": row["type"],
                "incident_id": incident_id,
                "actor": row["actor"],
                "payload": _json_field(row["payload"]),
                "prev_hash": row["prev_hash"],
                "hash": row["hash"],
            },
            sort_keys=True,
        )
        for row in events
    ]
    body = "\n".join(lines)
    return (body + "\n" if body else "").encode("utf-8")


def _cell(text: str) -> Paragraph:
    return Paragraph(text, _CELL)


def _timeline_table(events: list[asyncpg.Record]) -> Table:
    rows: list[list[Any]] = [["seq", "ts", "type", "actor", "payload"]]
    for row in events:
        payload = _json_field(row["payload"])
        rows.append(
            [
                str(row["seq"]),
                format_ts(row["created_at"]),
                row["type"],
                row["actor"],
                _cell(json.dumps(payload, sort_keys=True)),
            ]
        )
    table = Table(rows, colWidths=[10 * mm, 30 * mm, 32 * mm, 28 * mm, 70 * mm], repeatRows=1)
    table.setStyle(_TABLE_HEAD_STYLE)
    return table


def _actions_table(actions: list[asyncpg.Record]) -> Table:
    rows: list[list[Any]] = [
        ["action id", "catalog key", "tier", "status", "confidence", "policy decision", "result"]
    ]
    for row in actions:
        policy_result = _json_field(row["policy_result"]) or {}
        allow = policy_result.get("allow")
        rule_id = policy_result.get("rule_id", "-")
        decision = "-" if allow is None else ("allow" if allow else "deny")
        result = _json_field(row["result"]) or {}
        rows.append(
            [
                _cell(row["id"]),
                row["catalog_key"],
                row["tier"],
                row["status"],
                f"{row['confidence']:.2f}" if row["confidence"] is not None else "-",
                _cell(f"{decision} ({rule_id})"),
                _cell(json.dumps(result, sort_keys=True) if result else "-"),
            ]
        )
    widths = [24 * mm, 26 * mm, 14 * mm, 20 * mm, 16 * mm, 34 * mm, 36 * mm]
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(_TABLE_HEAD_STYLE)
    return table


def _approvals_table(approvals: list[asyncpg.Record]) -> Table:
    rows: list[list[Any]] = [["action id", "decision", "signer fingerprint", "signature", "ts"]]
    for row in approvals:
        rows.append(
            [
                _cell(row["action_id"]),
                row["decision"],
                fingerprint(row["approver_pubkey"]),
                _cell(row["signature"][:32] + "..."),
                format_ts(row["created_at"]),
            ]
        )
    table = Table(rows, colWidths=[24 * mm, 20 * mm, 34 * mm, 46 * mm, 36 * mm], repeatRows=1)
    table.setStyle(_TABLE_HEAD_STYLE)
    return table


def _agent_runs_table(agent_runs: list[asyncpg.Record]) -> Table:
    rows: list[list[Any]] = [
        ["agent", "status", "model", "tokens in", "tokens out", "cost usd", "started", "ended"]
    ]
    for row in agent_runs:
        rows.append(
            [
                row["agent"],
                row["status"],
                row["model"] or "-",
                str(row["tokens_in"]),
                str(row["tokens_out"]),
                f"{float(row['cost_usd']):.5f}",
                format_ts(row["started_at"]),
                format_ts(row["ended_at"]) if row["ended_at"] else "-",
            ]
        )
    table = Table(
        rows,
        colWidths=[16 * mm, 18 * mm, 22 * mm, 16 * mm, 18 * mm, 18 * mm, 28 * mm, 28 * mm],
        repeatRows=1,
    )
    table.setStyle(_TABLE_HEAD_STYLE)
    return table


def _incident_narrative(data: dict[str, Any]) -> str:
    """Draft serious-incident-report language (Article 73). Plain
    description of what happened and how it was handled; not a submission,
    just the shape one would start from."""
    incident = data["incident"]
    actions = data["actions"]
    approvals = data["approvals"]
    executed = [a for a in actions if a["status"] == "executed"]
    autonomy = incident["autonomy"] or "unresolved"
    mttr = incident["mttr_seconds"]
    mttr_text = f"{mttr} seconds" if mttr is not None else "not yet resolved"
    services = ", ".join(incident["affected_services"]) or "none recorded"
    oversight = (
        f"{len(approvals)} signed human decision(s) were recorded against this incident's "
        f"actions." if approvals else "No human approval or veto was recorded; every executed "
        "action cleared automated policy at green or yellow tier without needing sign-off."
    )
    return (
        f"Incident {incident['id']} ({incident['title']}) was detected by rule "
        f"'{incident['source_rule']}', affecting: {services}. {len(executed)} action(s) were "
        f"executed toward remediation. The incident's autonomy level was recorded as "
        f"'{autonomy}', with a measured time to resolution of {mttr_text}. {oversight} "
        "This section demonstrates the evidence shape AEGIS produces for a serious-incident "
        "report; it is a draft starting point, not a completed regulatory filing, and no "
        "compliance claim is made."
    )


def _build_pdf(data: dict[str, Any]) -> bytes:
    incident = data["incident"]
    chain_result = verify_row_chain(incident["id"], data["events"])

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=16 * mm,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        title=f"AEGIS evidence pack: {incident['id']}",
    )
    story: list[Any] = []

    story.append(Paragraph("AEGIS evidence pack", _H1))
    story.append(
        Paragraph(
            f"Incident {incident['id']} &mdash; generated for record-keeping and human "
            "oversight review. Not a compliance certificate.",
            _SUBTITLE,
        )
    )
    summary_rows = [
        ["title", incident["title"]],
        ["severity", incident["severity"] or "-"],
        ["status", incident["status"]],
        ["source rule", incident["source_rule"]],
        ["affected services", ", ".join(incident["affected_services"]) or "-"],
        ["started at", format_ts(incident["started_at"])],
        [
            "resolved at",
            format_ts(incident["resolved_at"]) if incident["resolved_at"] else "-",
        ],
        ["mttr seconds", str(incident["mttr_seconds"]) if incident["mttr_seconds"] else "-"],
        ["autonomy", incident["autonomy"] or "-"],
    ]
    summary_table = Table(summary_rows, colWidths=[40 * mm, 130 * mm])
    summary_table.setStyle(_TABLE_HEAD_STYLE)
    story.append(summary_table)

    story.append(Paragraph("Full timeline", _H2))
    story.append(Paragraph("EU AI Act Article 12: record-keeping", _SUBTITLE))
    story.append(_timeline_table(data["events"]))

    story.append(Paragraph("Actions and policy decisions", _H2))
    story.append(Paragraph("EU AI Act Article 12: record-keeping", _SUBTITLE))
    if data["actions"]:
        story.append(_actions_table(data["actions"]))
    else:
        story.append(Paragraph("No actions were proposed for this incident.", _BODY))

    story.append(Paragraph("Approvals and vetoes", _H2))
    story.append(Paragraph("EU AI Act Article 14: human oversight", _SUBTITLE))
    if data["approvals"]:
        story.append(_approvals_table(data["approvals"]))
    else:
        story.append(Paragraph("No human approval or veto was recorded.", _BODY))

    story.append(Paragraph("Chain verification", _H2))
    story.append(Paragraph("EU AI Act Article 12: record-keeping", _SUBTITLE))
    verdict = "valid, no break detected" if chain_result["valid"] else (
        f"BROKEN at seq {chain_result['break_at_seq']}"
    )
    story.append(Paragraph(f"Hash chain result: {verdict}.", _BODY))

    story.append(Paragraph("Agent runs and cost", _H2))
    story.append(Paragraph("EU AI Act Article 12: record-keeping", _SUBTITLE))
    if data["agent_runs"]:
        story.append(_agent_runs_table(data["agent_runs"]))
    else:
        story.append(Paragraph("No agent runs were recorded.", _BODY))

    story.append(Paragraph("Serious incident report, draft", _H2))
    story.append(Paragraph("EU AI Act Article 73: serious incident report draft", _SUBTITLE))
    story.append(KeepTogether([Paragraph(_incident_narrative(data), _BODY)]))
    story.append(Spacer(1, 4 * mm))

    doc.build(story)
    return buf.getvalue()


def build_zip(data: dict[str, Any]) -> bytes:
    incident_id = data["incident"]["id"]
    pdf_bytes = _build_pdf(data)
    jsonl_bytes = _events_jsonl(incident_id, data["events"])

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("report.pdf", pdf_bytes)
        zf.writestr("events.jsonl", jsonl_bytes)
    return buf.getvalue()
