import json as json_mod

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents.blackboard import Blackboard
from app.agents.chief_editor import ChiefEditorAgent
from app.agents.critic import CriticAgent
from app.agents.planner import PlannerAgent
from app.agents.skills.base import SkillRegistry
from app.agents.skills import QueryWorldviewSkill, SearchEntitySkill
from app.agents.writer import WriterAgent
from app.config import settings
from app.services.context_builder import ContextBuilder
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService
from app.services.memory_service import MemoryService
from app.services.novel_service import NovelService
from app.services.timeline_retriever import TimelineRetriever

router = APIRouter(prefix="/api/chat", tags=["chat"])

novel_service = NovelService(settings.user_data_dir)
memory_service = MemoryService(settings.user_data_dir)
context_builder = ContextBuilder()
embedding_service = EmbeddingService()
llm_service = LLMService(
    base_url=settings.llm_api_base,
    api_key=settings.llm_api_key,
    model=settings.llm_model,
)
timeline_retriever = TimelineRetriever(embedding_service, llm_service)


class ChatRequest(BaseModel):
    novel_name: str
    content: str


def _sse_event(event_type: str, payload: dict) -> str:
    data = json_mod.dumps({"type": event_type, **payload}, ensure_ascii=False)
    return f"data: {data}\n\n"


def _load_context(novel_name: str, user_input: str):
    memory_service.init_memory_files(novel_name)
    worldview = memory_service.read_worldview(novel_name)
    timeline = memory_service.read_timeline(novel_name)
    entity_index = memory_service.read_entity_index(novel_name)
    summary_data = memory_service.read_recent_summary(novel_name)
    chapters = novel_service.get_chapters(novel_name)

    recent_3_raw = "\n\n".join(
        f"### {ch['title']}\n{ch['text']}" for ch in chapters[-3:]
    )
    expanded_query = timeline_retriever.expand_query(user_input, recent_3_raw)
    relevant_timeline = timeline_retriever.retrieve(
        timeline, expanded_query, top_k=5, entity_index=entity_index,
    )
    timeline_text = context_builder.format_timeline(relevant_timeline)

    profiles = memory_service.read_entity_profiles(novel_name)
    matched_entities: set[str] = set()
    for e in relevant_timeline:
        matched_entities.update(e.get("entities", []))
    profile_lines = []
    for ent in matched_entities:
        if ent in profiles:
            p = profiles[ent]
            profile_lines.append(
                f"- {ent}: {p.get('description', '')} (当前状态: {p.get('current_status', '')})"
            )
    entity_profiles_text = "\n".join(profile_lines)
    style_guidelines = memory_service.read_style_guidelines(novel_name)

    recent_summary = summary_data.get("recent_summary", "")
    return (
        worldview,
        timeline_text,
        recent_summary,
        recent_3_raw,
        style_guidelines,
        entity_profiles_text,
    )


@router.post("/ask")
def ask(req: ChatRequest):
    def gen():
        try:
            worldview, tl_text, summary, recent_raw, style_g, ent_prof = _load_context(
                req.novel_name, req.content
            )
            messages = context_builder.build_ask_messages(
                worldview,
                tl_text,
                summary,
                recent_raw,
                req.content,
                style_g,
                ent_prof,
            )
            for chunk in llm_service.generate_stream_sync(messages, settings.llm_max_tokens):
                yield _sse_event("token", {"content": chunk})
            yield _sse_event("done", {})
        except Exception as e:
            yield _sse_event("error", {"message": str(e)})

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/write")
def write(req: ChatRequest, background_tasks: BackgroundTasks):
    def gen():
        try:
            worldview, tl_text, summary, recent_raw, style_g, ent_prof = _load_context(
                req.novel_name, req.content
            )

            bb = Blackboard(
                novel_name=req.novel_name,
                current_prompt=req.content,
                worldview=worldview,
                timeline=tl_text,
                recent_summary=summary,
                recent_3_raw=recent_raw,
                style_guidelines=style_g,
                entity_profiles_text=ent_prof,
            )

            chief = ChiefEditorAgent(llm_service)
            skill_registry = SkillRegistry()
            skill_registry.register(SearchEntitySkill(memory_service, req.novel_name))
            skill_registry.register(QueryWorldviewSkill(memory_service, req.novel_name))
            planner = PlannerAgent(llm_service, registry=skill_registry)
            writer = WriterAgent(llm_service, registry=skill_registry)
            critic = CriticAgent(llm_service, registry=skill_registry)

            yield _sse_event("info", {"message": "开始构思..."})

            max_loops = 5
            loops = 0
            while bb.status != "done" and loops < max_loops:
                loops += 1
                yield _sse_event("agent_start", {"agent": "chief", "message": "总编正在思考..."})
                
                action, thought, directive = None, None, None
                for chunk in chief.decide_next_action_stream(bb):
                    if isinstance(chunk, str):
                        yield _sse_event("agent_token", {"content": chunk})
                    elif isinstance(chunk, tuple):
                        action, thought, directive = chunk
                        
                bb.update(chief_directive=directive)
                yield _sse_event(
                    "agent_done", 
                    {
                        "agent": "chief", 
                        "message": "思考完毕。", 
                        "content": thought or "思考完毕。"
                    }
                )

                if action == "call_planner":
                    yield _sse_event("agent_start", {"agent": "planner", "message": "主笔正在撰写大纲..."})
                    for chunk in planner.run_stream(bb):
                        yield _sse_event("agent_token", {"content": chunk})
                    yield _sse_event("agent_done", {"agent": "planner"})

                elif action == "call_writer":
                    yield _sse_event("info", {"message": "执笔开始写作正文..."})
                    for chunk in writer.write_stream(bb):
                        yield _sse_event("token", {"content": chunk})
                    yield _sse_event("info", {"message": "\n正文写作完毕，准备审阅..."})

                elif action == "call_critic":
                    yield _sse_event(
                        "agent_start",
                        {"agent": "critic", "message": "审校正在严格审查并查阅资料..."},
                    )
                    for _chunk in critic.run_stream(bb):
                        pass

                    accepted = bb.status == "done"
                    msg = (
                        "审阅通过"
                        if accepted
                        else f"审校未通过，要求重写。意见：{bb.critic_feedback[:50]}..."
                    )
                    yield _sse_event(
                        "agent_done",
                        {
                            "agent": "critic",
                            "message": msg,
                            "content": bb.critic_feedback,
                            "accepted": accepted,
                        },
                    )

                elif action == "finish":
                    if not bb.critic_feedback:
                        action = "call_critic"
                        yield _sse_event(
                            "agent_start",
                            {"agent": "critic", "message": "审校正在严格审查并查阅资料..."},
                        )
                        for _chunk in critic.run_stream(bb):
                            pass

                        accepted = bb.status == "done"
                        msg = (
                            "审阅通过"
                            if accepted
                            else f"审校未通过，要求重写。意见：{bb.critic_feedback[:50]}..."
                        )
                        yield _sse_event(
                            "agent_done",
                            {
                                "agent": "critic",
                                "message": msg,
                                "content": bb.critic_feedback,
                                "accepted": accepted,
                            },
                        )
                    else:
                        bb.update(status="done")
                        break

            if loops >= max_loops:
                yield _sse_event("info", {"message": "达到最大循环次数，强制结束。"})

            # 如果最终状态不是 done，说明中途失败或被彻底驳回但达到了最大循环次，不应保存
            if bb.status == "done" and bb.draft:
                chapters = novel_service.get_chapters(req.novel_name)
                new_chapter_index = len(chapters)
                chapter_num = new_chapter_index + 1
                title = f"第{chapter_num}章"

                novel_service.append_chapter(req.novel_name, title, bb.draft, prompt=req.content)

                from app.routers.memory import sync_memory_single_chapter

                background_tasks.add_task(
                    sync_memory_single_chapter, req.novel_name, new_chapter_index
                )

                yield _sse_event("done", {"chapter_title": title})
            else:
                yield _sse_event("done", {})
        except Exception as e:
            yield _sse_event("error", {"message": str(e)})

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.delete("/{novel_name}/last")
def delete_last(novel_name: str):
    chapters = novel_service.get_chapters(novel_name)
    success = novel_service.delete_last_chapter(novel_name)
    if success and chapters:
        deleted_index = len(chapters) - 1
        memory_service.init_memory_files(novel_name)
        memory_service.rollback_memory(novel_name, deleted_index)
    return {"success": success, "novel_name": novel_name}


_ALLOWED_ROLES = {"user", "assistant"}


class FreeChatMessage(BaseModel):
    role: str
    content: str


class FreeChatRequest(BaseModel):
    messages: list[FreeChatMessage]


@router.post("/free")
def free_chat(req: FreeChatRequest):
    """自由聊天：不关联小说，不存储，直接调 LLM，支持多轮上下文。"""
    def gen():
        try:
            msgs = [{"role": "system", "content": "你是一个有帮助的AI助手。"}]
            msgs.extend([
                {"role": m.role if m.role in _ALLOWED_ROLES else "user", "content": m.content}
                for m in req.messages
            ])
            for chunk in llm_service.generate_stream_sync(msgs, settings.llm_max_tokens):
                yield _sse_event("token", {"content": chunk})
            yield _sse_event("done", {})
        except Exception as e:
            yield _sse_event("error", {"message": str(e)})

    return StreamingResponse(gen(), media_type="text/event-stream")
