import sys
from pathlib import Path

from .attachments import collect_text_files, decompress_all, download_attachments
from .config import Config, get_jira_config
from .jira import JiraClient, parse_comments
from .schemas import AttachmentContent, AttachmentMeta, RawTicket


def fetch_ticket(ticket_id: str, config: Config) -> tuple[Path, int]:
    jira_cfg = get_jira_config(config)
    client = JiraClient(jira_cfg.url.rstrip("/"), jira_cfg.user, jira_cfg.token)

    ticket_dir = Path(ticket_id)
    attachments_dir = ticket_dir / "attachments"
    extracted_dir = attachments_dir / "extracted"
    raw_json_path = ticket_dir / f"{ticket_id}-raw.json"
    attachments_dir.mkdir(parents=True, exist_ok=True)

    print(f"==> Fetching {ticket_id} from {jira_cfg.url} ...", file=sys.stderr)
    issue = client.get_issue(ticket_id)
    raw_comments = client.get_comments(ticket_id)

    summary = issue["fields"].get("summary") or ""
    description = issue["fields"].get("description") or ""
    comments = parse_comments(raw_comments)
    raw_attachments = issue["fields"].get("attachment") or []
    print(f"    Found {len(raw_attachments)} attachment(s).", file=sys.stderr)

    downloaded = download_attachments(raw_attachments, attachments_dir, (jira_cfg.user, jira_cfg.token))

    print("==> Processing attachments ...", file=sys.stderr)
    decompress_all(attachments_dir, extracted_dir)

    raw_contents = collect_text_files(attachments_dir, ticket_dir)
    attachment_contents = [AttachmentContent(**item) for item in raw_contents]

    raw_ticket = RawTicket(
        ticket=ticket_id,
        summary=summary,
        description=description,
        comments=comments,
        attachments=AttachmentMeta(downloaded=downloaded),
        attachment_contents=attachment_contents,
    )
    raw_json_path.write_text(raw_ticket.model_dump_json(indent=2), encoding="utf-8")
    print(f"==> Written to {raw_json_path}", file=sys.stderr)

    return raw_json_path, len(downloaded)
