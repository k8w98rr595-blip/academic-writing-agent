from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

from docx import Document as WordDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from fastapi import HTTPException, status

from .text import normalize_text


MAX_DOCX_BYTES = 5 * 1024 * 1024
MAX_ZIP_ENTRIES = 1000
MAX_UNCOMPRESSED_BYTES = 25 * 1024 * 1024
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def validate_docx_upload(filename: str, content_type: str, payload: bytes) -> None:
    safe_name = Path(filename or "").name
    if not safe_name.lower().endswith(".docx") or safe_name != filename:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Only safe .docx filenames are accepted")
    if content_type and content_type not in {DOCX_MIME, "application/octet-stream"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid Word MIME type")
    if len(payload) < 4 or len(payload) > MAX_DOCX_BYTES or payload[:2] != b"PK":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid or oversized Word document")
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ZIP_ENTRIES or sum(item.file_size for item in infos) > MAX_UNCOMPRESSED_BYTES:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Word document expands beyond safe limits")
            names = {item.filename for item in infos}
            if any(
                name.startswith(("/", "\\"))
                or "\\" in name
                or ".." in Path(name).parts
                for name in names
            ):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Unsafe Word archive path")
            if "word/document.xml" not in names or any(name.lower().endswith("vbaproject.bin") for name in names):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Unsupported Word document structure")
            for name in names:
                if name.endswith(".rels"):
                    relation_data = archive.read(name)
                    if re.search(br"TargetMode\s*=\s*[\"']External[\"']", relation_data, flags=re.IGNORECASE):
                        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="External Word relationships are not accepted")
    except zipfile.BadZipFile as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid Word archive") from error


def extract_docx_text(payload: bytes) -> str:
    try:
        document = WordDocument(io.BytesIO(payload))
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Unable to parse Word document") from error
    # Fail closed instead of silently dropping academic content that this plain
    # text workspace cannot represent. Never follow relationships to remote data.
    unsupported = {
        "m:oMath": "公式", "m:oMathPara": "公式", "w:drawing": "图片或图形",
        "w:pict": "图片或文本框", "w:object": "嵌入对象", "w:footnoteReference": "脚注",
        "w:endnoteReference": "尾注", "w:ins": "修订记录", "w:del": "修订记录",
        "w:moveFrom": "修订记录", "w:moveTo": "修订记录", "w:altChunk": "嵌入内容",
        "w:sdt": "内容控件", "w:fldSimple": "动态域", "w:fldChar": "动态域",
        "w:commentReference": "批注", "w:numPr": "自动编号列表",
    }
    tags = {node.tag for node in document.element.iter()}
    found = sorted({label for tag, label in unsupported.items() if qn(tag) in tags})
    for relationship in document.part.rels.values():
        if relationship.reltype.endswith(("/header", "/footer")):
            # These are local parts already parsed by python-docx, not URLs.
            if any((node.text or "").strip() for node in relationship.target_part.element.iter(qn("w:t"))):
                found.append("页眉或页脚正文")
    if found:
        raise HTTPException(status_code=422, detail="当前纯文本导入不支持：" + "、".join(sorted(set(found))) + "。请保留原文件，并改用经人工核对的正文副本。")
    blocks = []
    for element in document.element.body.iterchildren():
        if element.tag == qn("w:p"):
            paragraph = Paragraph(element, document)
            style = paragraph.style
            visited = set()
            while style is not None and style.style_id not in visited:
                visited.add(style.style_id)
                if any(node.tag == qn("w:numPr") for node in style.element.iter()):
                    raise HTTPException(status_code=422, detail="当前纯文本导入不支持自动编号列表，请先人工整理正文副本。")
                style = style.base_style
            text = normalize_text(paragraph.text)
            if text:
                blocks.append(text)
        elif element.tag == qn("w:tbl"):
            table = Table(element, document)
            if any(node.tag in {qn("w:gridSpan"), qn("w:vMerge"), qn("w:hMerge")} for node in element.iter()) or len(list(element.iter(qn("w:tbl")))) != 1:
                raise HTTPException(status_code=422, detail="当前纯文本导入不支持合并单元格或嵌套表格，请先人工整理正文副本。")
            rows = []
            for row in table.rows:
                cells = [normalize_text(cell.text) for cell in row.cells]
                if any(cells):
                    rows.append(" | ".join(cells))
            if rows:
                blocks.append("\n".join(rows))
        elif element.tag != qn("w:sectPr"):
            raise HTTPException(status_code=422, detail="Word 含有当前无法可靠保留的正文结构，请改用经人工核对的纯文本。")
    return "\n\n".join(blocks)


def build_docx(title: str, paragraphs: list[dict], version_number: int) -> bytes:
    document = WordDocument()
    document.core_properties.title = title
    document.core_properties.subject = f"Paperlight version {version_number}"
    for paragraph in paragraphs:
        document.add_paragraph(str(paragraph["text"]))
    stream = io.BytesIO()
    document.save(stream)
    return stream.getvalue()
