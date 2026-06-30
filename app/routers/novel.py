import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import settings
from app.services.llm_service import LLMService
from app.services.novel_service import NovelService
from app.services.txt_parser import TxtParser

router = APIRouter(prefix="/api/novels", tags=["novels"])
service = NovelService(settings.user_data_dir)
_llm = LLMService(settings.llm_api_base, settings.llm_api_key, settings.llm_model)
txt_parser = TxtParser(llm=_llm)


class CreateNovelRequest(BaseModel):
    name: str


@router.post("")
def create_novel(req: CreateNovelRequest) -> dict:
    try:
        service.create_novel(req.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"name": req.name, "created": True}


@router.get("")
def list_novels() -> list[dict]:
    return service.list_novels()


@router.post("/upload")
async def upload_novel(name: str = Form(...), file: UploadFile = File(...)) -> dict:
    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文件编码错误，仅支持 UTF-8")
    filename = file.filename or ""

    try:
        if filename.endswith(".txt"):
            chapters = txt_parser.split(text)
            json_content = json.dumps(chapters, ensure_ascii=False, indent=2)
            chapter_count = service.upload_novel(name, json_content)
        else:
            chapter_count = service.upload_novel(name, text)
    except (ValueError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"name": name, "chapter_count": chapter_count}


@router.delete("/{name}")
def delete_novel(name: str) -> dict:
    try:
        success = service.delete_novel(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": success, "name": name}


class RenameRequest(BaseModel):
    new_name: str


@router.put("/{name}/rename")
def rename_novel(name: str, req: RenameRequest) -> dict:
    try:
        success = service.rename_novel(name, req.new_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": success, "old_name": name, "new_name": req.new_name}


@router.get("/{name}/chapters")
def get_chapters(name: str) -> list[dict]:
    try:
        return service.get_chapters(name)
    except (ValueError, FileNotFoundError) as e:
        status = 400 if isinstance(e, ValueError) else 404
        raise HTTPException(status_code=status, detail=str(e))
