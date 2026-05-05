from pydantic import BaseModel


class Comment(BaseModel):
    author: str
    created: str
    body: str


class DownloadedAttachment(BaseModel):
    filename: str
    mimeType: str
    size: int
    localPath: str


class AttachmentMeta(BaseModel):
    downloaded: list[DownloadedAttachment]


class AttachmentContent(BaseModel):
    filename: str
    content: str


class RawTicket(BaseModel):
    ticket: str
    summary: str
    description: str
    comments: list[Comment]
    attachments: AttachmentMeta
    attachment_contents: list[AttachmentContent] = []
