import json as json_mod
import re
import threading

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import settings
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService
from app.services.memory_service import MemoryService
from app.services.novel_service import NovelService

router = APIRouter(prefix="/api/memory", tags=["memory"])

memory_service = MemoryService(settings.user_data_dir)
novel_service = NovelService(settings.user_data_dir)
llm_service = LLMService(
    base_url=settings.llm_api_base,
    api_key=settings.llm_api_key,
    model=settings.llm_model,
)
embedding_service = EmbeddingService()

_cancel_flags: dict[str, threading.Event] = {}
_update_locks: dict[str, threading.Lock] = {}
_update_locks_registry_lock = threading.Lock()
_update_lock_times: dict[str, float] = {}
_LOCK_TIMEOUT = 600  # 锁超时 10 分钟，防止泄露

_update_progress: dict[str, dict] = {}

# ===== 世界观：先判断是否需要更新，再生成完整新版 =====

WORLDVIEW_JUDGE_PROMPT = """你是一个小说世界观变更审核员。请严格判断本章内容是否对世界观设定产生了实质性影响。

只有以下情况才算需要更新：
- 出现了全新的重要角色（有名字、有身份描述的，路人不算）
- 已有角色的能力发生显著变化（觉醒/升级/削弱/失去，而不是普通的使用能力）
- 重要人物关系发生根本性改变（结盟变敌对、背叛、新的师徒/伴侣关系等）
- 出现新的重要势力/组织，或已有势力发生重大变化（合并/瓦解/易主）
- 出现新的关键地点、物品、能力体系、世界规则
- 世界格局发生改变

以下情况不需要更新：
- 普通的战斗场景（只是使用已知能力，没有新变化）
- 日常对话、情感互动（除非确立了新的关系）
- 角色移动到已知地点
- 重复提及已有设定

【现有世界观】
{existing_worldview}

【本章内容 - {chapter_title}】
{chapter_text}

请只回答一个字：是 或 否。不要加任何标点、空格或解释。"""

WORLDVIEW_UPDATE_PROMPT = """你是一个小说世界观设定集编辑。请在现有世界观基础上，根据本章新增的设定变化，生成一份更新后的完整世界观设定文档。

要求：
1. 保持现有世界观的整体结构和格式不变（如：人物、势力、地点、力量体系等）。
2. 【核心任务：精简与淘汰】为了防止设定集无限膨胀，你必须：
   - 剔除或合并已经死亡、很久未出场或不再重要的边缘角色。
   - 简化对已覆灭势力或已废弃地点的描述，仅保留其对主线历史的影响。
   - 压缩冗长的背景故事，保留最核心的设定机制。
3. 补充本章新增的【重要】设定（新核心角色、新势力、新规则）。
4. 输出 Markdown 格式的完整世界观文档。
5. 必须严格控制在 4000 字以内！如果超过，请继续压缩次要内容。

【现有世界观】
{existing_worldview}

【本章内容 - {chapter_title}】
{chapter_text}

请输出更新后的完整世界观设定文档："""

TIMELINE_PROMPT = """你是一个小说核心事件时间线提取助手。请为本章提取核心事件，格式如下（多个事件用空行分隔）：

事件：<事件名称>
地点：<发生地点>
参与者：<涉及角色，逗号分隔>
过程：<简要叙述经过，1-3句话>
结局状态：<事件结果>

只提取本章的关键事件（重要的情节转折、战斗、人物关系变化等），不要编造。普通的日常对话、移动场景可以忽略。

最后请单独一行输出本章涉及的所有重要实体（人名、地名、势力/组织名）。
⚠️ 注意：如果同一人物有多种称呼（如全名、外号、职位），请必须统一使用其最常用的【全名】作为实体名提取，不要提取称号或别名。
格式为：
实体：<全名1>，<全名2>，<名称3>

【本章内容 - {chapter_title}】
{chapter_text}

请输出本章核心事件时间线："""

ENTITY_PROFILE_PROMPT = """你是一个小说人物档案管理员。请根据本章内容，为以下实体提炼或更新档案。
⚠️ 注意：在描述和状态中，遇到不同称呼时，请尽量将其指代到对应角色的全名上。

只提取以下出现的实体，包含两个字段：
1. description (静态描述)：外貌、性格、身份、长期目标等（如果本章未提及但之前已知，可不填，尽量精简）。
2. current_status (当前状态)：在本章结束时，该实体所处的地点、身体状态、近期短期目标或行动。

返回 JSON 格式，如下所示：
{{
  "实体名1": {{
    "description": "...",
    "current_status": "..."
  }}
}}

【本章出现实体列表】
{entities}

【本章内容】
{chapter_text}

请直接输出合法的 JSON 对象，不要包含 markdown 代码块标记（如 ```json），不要输出多余解释。"""


def _parse_entities(tl_text: str) -> tuple[str, list[str]]:
    """从时间线 LLM 输出中分离实体行，返回 (纯事件文本, 实体列表)。"""
    lines = tl_text.strip().split("\n")
    entities: list[str] = []
    event_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("实体：") or stripped.startswith("实体:"):
            raw = stripped.split("：", 1)[-1] if "：" in stripped else stripped.split(":", 1)[-1]
            entities = [e.strip() for e in raw.replace(",", "，").split("，") if e.strip()]
        else:
            event_lines.append(line)
    content = "\n".join(event_lines).strip()
    return content, entities

SUMMARY_PROMPT = """你是一个小说情节总结助手。请对以下章节内容进行精炼总结，突出关键情节转折和角色发展。
字数控制在 1500 字以内。

{chapters_text}

请输出情节总结："""


def _sse(event_type: str, payload: dict) -> str:
    data = json_mod.dumps({"type": event_type, **payload}, ensure_ascii=False)
    return f"data: {data}\n\n"


def _apply_entity_profiles_llm(
    novel_name: str, entities: list[str], ch_text: str, abs_idx: int
) -> None:
    try:
        ep_prompt = ENTITY_PROFILE_PROMPT.format(
            entities="，".join(entities), chapter_text=ch_text
        )
        ep_raw = llm_service.generate_sync(
            [{"role": "user", "content": ep_prompt}], max_tokens=2048
        )
        json_match = re.search(r"\{.*\}", ep_raw, re.DOTALL)
        if json_match:
            profiles = json_mod.loads(json_match.group())
            for ent_name, data in profiles.items():
                if isinstance(data, dict):
                    memory_service.update_entity_profile(
                        novel_name,
                        ent_name,
                        data.get("description", ""),
                        data.get("current_status", ""),
                        abs_idx,
                    )
    except Exception as e:
        print(f"提取实体档案失败: {e}")


@router.put("/{novel_name}/style")
def update_style_guidelines(novel_name: str, payload: dict):
    """手动更新文风规范"""
    memory_service.init_memory_files(novel_name)
    style = payload.get("style_guidelines", "")
    memory_service.write_style_guidelines(novel_name, style)
    return {"success": True, "message": "文风规范已更新"}

@router.post("/{novel_name}/style/generate")
def generate_style_guidelines(novel_name: str):
    """自动生成文风规范"""
    from fastapi import HTTPException
    memory_service.init_memory_files(novel_name)
    chapters = novel_service.get_chapters(novel_name)
    if not chapters:
        raise HTTPException(status_code=400, detail="小说暂无章节，无法生成文风规范")
    
    # 取前三章
    sample_chapters = chapters[:3]
    ch_text = "\n\n".join(f"### {c.get('title', f'第{i+1}章')}\n{c.get('text', '')}" for i, c in enumerate(sample_chapters))
    
    prompt = f"""请作为一名客观、中立的文学分析师，分析以下小说的前几章，提取并总结出一部用于指导后续写作的【文风规范】（Style Guidelines）。

【极其重要的要求】
1. 绝对客观真实：请完全基于原文的实际内容进行总结。如果原文包含极端、黑暗、情色、暴力、成人向（NSFW）等特殊题材或露骨描写，请务必【直言不讳地准确概括其核心驱动力和表达尺度】，绝对不要对其进行美化、净化、和谐或道德评判，更不要将其强行总结为浪漫或正能量的故事。
2. 重点关注整体基调，不需要列举具体人物的详细设定。
3. 请关注：
   - 核心题材与叙事基调（如：黑暗情色、权谋悲剧、废土生存等）
   - 尺度的描写特点与用词偏好（例如敏感场景的描写方式是隐晦还是极端露骨直白）
   - 整体情感基调与需要避免的“毒点”（即偏离当前硬核/黑暗设定的写法）

请直接输出规范内容，不要开头结尾的客套话。
【要求】必须极度精简，控制在 300 字左右，只提炼最核心的、能让写手一眼看懂的指导原则。

【小说原文参考】
{ch_text}
"""
    try:
        result = llm_service.generate_sync([{"role": "user", "content": prompt}], max_tokens=1024)
        style = result.strip()
        memory_service.write_style_guidelines(novel_name, style)
        return {"success": True, "style_guidelines": style}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成文风规范失败: {str(e)}")

@router.get("/{novel_name}")
def get_memory(novel_name: str) -> dict:
    memory_service.init_memory_files(novel_name)
    tl = memory_service.read_timeline(novel_name)
    tl_display = [
        {k: v for k, v in e.items() if k != "embedding"}
        for e in tl
    ]
    return {
        "worldview": memory_service.read_worldview(novel_name),
        "timeline": tl_display,
        "recent_summary": memory_service.read_recent_summary(novel_name),
        "entity_profiles": memory_service.read_entity_profiles(novel_name),
        "style_guidelines": memory_service.read_style_guidelines(novel_name),
    }


@router.post("/{novel_name}/cancel")
def cancel_update(novel_name: str):
    flag = _cancel_flags.get(novel_name)
    if flag:
        flag.set()
    return {"cancelled": True}


@router.get("/{novel_name}/update-status")
def get_update_status(novel_name: str) -> dict:
    return _update_progress.get(novel_name, {"running": False})


@router.post("/{novel_name}/update")
def update_memory(novel_name: str, start_chapter: int = -1, rebuild_target: str = "all"):
    import time
    with _update_locks_registry_lock:
        if novel_name not in _update_locks:
            _update_locks[novel_name] = threading.Lock()
        lock = _update_locks[novel_name]

    if not lock.acquire(blocking=False):
        locked_at = _update_lock_times.get(novel_name, 0)
        if time.time() - locked_at > _LOCK_TIMEOUT:
            try:
                lock.release()
            except RuntimeError:
                pass
            lock.acquire(blocking=False)
        else:
            return JSONResponse(
                status_code=409,
                content={"error": "该小说已有更新任务在运行，请等待完成或停止后再试"},
            )

    _update_lock_times[novel_name] = time.time()
    cancel_flag = threading.Event()
    _cancel_flags[novel_name] = cancel_flag

    def _set_progress(msg: str, running: bool = True):
        _update_progress[novel_name] = {"running": running, "message": msg}

    def gen():
        try:
            _set_progress("初始化...")
            memory_service.init_memory_files(novel_name)
            chapters = novel_service.get_chapters(novel_name)
            if not chapters:
                yield _sse("error", {"message": "没有章节数据，无法更新记忆"})
                return

            # 处理回滚逻辑
            if start_chapter >= 0:
                _set_progress(f"正在回滚记忆到第 {start_chapter + 1} 章之前...")
                yield _sse("progress", {"step": "start", "message": f"正在回滚记忆到第 {start_chapter + 1} 章之前..."})
                if rebuild_target == "all":
                    memory_service.rollback_memory(novel_name, start_chapter)
                elif rebuild_target == "worldview":
                    memory_service.rollback_worldview(novel_name, start_chapter)
                elif rebuild_target == "timeline":
                    memory_service.rollback_timeline(novel_name, start_chapter)
                    memory_service.rollback_entity_index(novel_name, start_chapter)
                    memory_service.rollback_entity_profiles(novel_name, start_chapter)
                
                # 如果是全量或者时间线重构，且回滚到了较早的章节，需要重置摘要
                if rebuild_target in ["all", "timeline"]:
                    summary_data = memory_service.read_recent_summary(novel_name)
                    last_idx = summary_data.get("last_updated_chapter_index", -1)
                    if last_idx >= start_chapter:
                        # 尝试恢复之前的摘要（这里简单处理为清空，后续重新生成）
                        memory_service.write_recent_summary(novel_name, [], "", start_chapter - 1)

            summary_data = memory_service.read_recent_summary(novel_name)
            last_idx = summary_data.get("last_updated_chapter_index", -1)

            summary_empty = not summary_data.get("recent_summary") and not summary_data.get("recent_3_chapters")

            # 确定起始章节
            if start_chapter >= 0:
                start = start_chapter
            else:
                start = last_idx + 1

            if start >= len(chapters) and not summary_empty:
                yield _sse("progress", {"step": "skip", "message": f"所有{len(chapters)}章已处理完毕，没有新章节需要更新"})
                yield _sse("done", {})
                return

            new_chapters = chapters[start:]
            total = len(new_chapters)
            if total > 0:
                msg = f"从第{start+1}章开始，共{total}章需要处理"
                _set_progress(msg)
                yield _sse("progress", {"step": "start", "message": msg})
            elif summary_empty:
                msg = "章节已处理完毕，补充生成近章摘要..."
                _set_progress(msg)
                yield _sse("progress", {"step": "start", "message": msg})

            existing_wv = memory_service.read_worldview(novel_name)
            existing_tl = memory_service.read_timeline(novel_name)

            for i, ch in enumerate(new_chapters):
                if cancel_flag.is_set():
                    _set_progress(f"已手动停止，处理到第{start + i}章", False)
                    yield _sse("progress", {"step": "stopped", "message": f"已手动停止，处理到第{start + i}章，进度已保存"})
                    yield _sse("stopped", {})
                    return

                abs_idx = start + i
                ch_title = ch.get("title", f"第{abs_idx + 1}章")
                ch_text = ch.get("text", "")

                # ===== 1) 世界观：先判断，再决定是否更新 =====
                if rebuild_target in ["all", "worldview"]:
                    msg = f"[{i+1}/{total}] {ch_title} — 判断世界观是否需要更新..."
                    _set_progress(msg)
                    yield _sse("progress", {
                        "step": "chapter",
                        "message": msg
                    })

                    judge_prompt = WORLDVIEW_JUDGE_PROMPT.format(
                        existing_worldview=existing_wv or "（空，尚未建立）",
                        chapter_title=ch_title,
                        chapter_text=ch_text,
                    )
                    try:
                        judge_result = llm_service.generate_sync(
                            [{"role": "user", "content": judge_prompt}],
                            max_tokens=8,
                        )
                    except Exception as e:
                        msg = f"判断世界观时发生错误，跳过本章世界观更新: {str(e)}"
                        _set_progress(msg, True)
                        yield _sse("progress", {"step": "chapter", "message": f"警告：{msg}"})
                        judge_result = "否"

                    if cancel_flag.is_set():
                        _set_progress("已手动停止，进度已保存", False)
                        yield _sse("progress", {"step": "stopped", "message": "已手动停止，进度已保存"})
                        yield _sse("stopped", {})
                        return

                    cleaned = judge_result.strip().lstrip("，。、：: \n")
                    need_update = cleaned.startswith("是")

                    if need_update:
                        msg = f"[{i+1}/{total}] {ch_title} — 更新世界观..."
                        _set_progress(msg)
                        yield _sse("progress", {"step": "chapter", "message": msg})
                        update_prompt = WORLDVIEW_UPDATE_PROMPT.format(
                            existing_worldview=existing_wv or "（空，请根据本章建立初始世界观）",
                            chapter_title=ch_title,
                            chapter_text=ch_text,
                        )
                        try:
                            existing_wv = llm_service.generate_sync(
                                [{"role": "user", "content": update_prompt}],
                                max_tokens=settings.llm_max_tokens,
                            )
                            memory_service.append_worldview(novel_name, abs_idx, existing_wv)
                            yield _sse("worldview_updated", {"content": existing_wv})
                            yield _sse("progress", {
                                "step": "chapter",
                                "message": f"[{i+1}/{total}] {ch_title} — 世界观已更新 ✓"
                            })
                        except Exception as e:
                            msg = f"更新世界观时发生错误，保留原世界观: {str(e)}"
                            _set_progress(msg, True)
                            yield _sse("progress", {"step": "chapter", "message": f"警告：{msg}"})
                    else:
                        yield _sse("progress", {
                            "step": "chapter",
                            "message": f"[{i+1}/{total}] {ch_title} — 世界观无需更新，跳过"
                        })

                if cancel_flag.is_set():
                    _set_progress("已手动停止，进度已保存", False)
                    yield _sse("progress", {"step": "stopped", "message": "已手动停止，进度已保存"})
                    yield _sse("stopped", {})
                    return

                # ===== 2) 时间线 =====
                if rebuild_target in ["all", "timeline"]:
                    msg = f"[{i+1}/{total}] {ch_title} — 提取时间线..."
                    _set_progress(msg)
                    yield _sse("progress", {"step": "chapter", "message": msg})

                    tl_prompt = TIMELINE_PROMPT.format(
                        chapter_title=ch_title,
                        chapter_text=ch_text,
                    )
                    try:
                        tl_raw = llm_service.generate_sync(
                            [{"role": "user", "content": tl_prompt}],
                            max_tokens=settings.llm_max_tokens,
                        )
                    except Exception as e:
                        msg = f"提取时间线时发生错误，跳过本章时间线: {str(e)}"
                        _set_progress(msg, True)
                        yield _sse("progress", {"step": "chapter", "message": f"警告：{msg}"})
                        tl_raw = ""

                    if cancel_flag.is_set():
                        _set_progress("已手动停止，进度已保存", False)
                        yield _sse("progress", {"step": "stopped", "message": "已手动停止，进度已保存"})
                        yield _sse("stopped", {})
                        return

                    tl_content, entities = _parse_entities(tl_raw)
                    if tl_content:
                        try:
                            emb = embedding_service.encode_single(tl_content)
                        except Exception:
                            emb = []
                        existing_tl.append({
                            "chapter_index": abs_idx,
                            "chapter": ch_title,
                            "content": tl_content,
                            "entities": entities,
                            "embedding": emb,
                        })
                        if entities:
                            memory_service.update_entity_index(novel_name, abs_idx, entities)
                            msg = f"[{i+1}/{total}] {ch_title} — 更新实体档案..."
                            _set_progress(msg)
                            yield _sse("progress", {"step": "chapter", "message": msg})
                            try:
                                _apply_entity_profiles_llm(
                                    novel_name, entities, ch_text, abs_idx
                                )
                            except Exception as e:
                                yield _sse("progress", {"step": "chapter", "message": f"警告：提取实体档案失败: {str(e)}"})
                    else:
                        yield _sse("progress", {
                            "step": "chapter",
                            "message": f"[{i+1}/{total}] {ch_title} 时间线为空，跳过"
                        })

                    memory_service.write_timeline(novel_name, existing_tl)

                    tl_display = [
                        {
                            "chapter": e["chapter"],
                            "content": e["content"],
                            "entities": e.get("entities", []),
                        }
                        for e in existing_tl
                    ]
                    yield _sse("timeline_updated", {"timeline": tl_display})

                # 更新摘要状态
                if rebuild_target in ["all", "timeline"]:
                    current_summary = summary_data.get("recent_summary", "")
                    current_recent_3 = summary_data.get("recent_3_chapters", [])
                    memory_service.write_recent_summary(
                        novel_name, current_recent_3, current_summary, abs_idx
                    )

                msg = f"[{i+1}/{total}] {ch_title} ✓（进度已保存）"
                _set_progress(msg)
                yield _sse("progress", {"step": "chapter", "message": msg})

            # ===== 全部章节处理完，最后做一次摘要 =====
            if cancel_flag.is_set():
                _set_progress("已手动停止，进度已保存", False)
                yield _sse("progress", {"step": "stopped", "message": "已手动停止，进度已保存"})
                yield _sse("stopped", {})
                return

            if rebuild_target in ["all", "timeline"]:
                _set_progress("正在生成近章摘要...")
                yield _sse("progress", {"step": "summary", "message": "正在生成近章摘要..."})

                ch_recent_4_to_10 = chapters[-10:-3] if len(chapters) > 3 else []
                if ch_recent_4_to_10:
                    ch_text_all = "\n\n".join(
                        f"### {c['title']}\n{c['text']}" for c in ch_recent_4_to_10
                    )
                    sum_prompt = SUMMARY_PROMPT.format(chapters_text=ch_text_all)
                    try:
                        sum_result = llm_service.generate_sync(
                            [{"role": "user", "content": sum_prompt}],
                            max_tokens=settings.llm_max_tokens,
                        )
                    except Exception as e:
                        msg = f"生成摘要时发生错误，跳过摘要: {str(e)}"
                        _set_progress(msg, True)
                        yield _sse("progress", {"step": "summary", "message": f"警告：{msg}"})
                        sum_result = ""
                else:
                    sum_result = ""

                recent_3 = [ch["text"] for ch in chapters[-3:]]
                memory_service.write_recent_summary(
                    novel_name, recent_3, sum_result, len(chapters) - 1
                )
                yield _sse("progress", {"step": "summary", "message": "近章摘要完成"})

            _set_progress("全部更新完成", False)
            yield _sse("done", {"updated_to_chapter": len(chapters)})
        except Exception as e:
            _set_progress(f"错误：{e}", False)
            yield _sse("error", {"message": str(e)})
        finally:
            _cancel_flags.pop(novel_name, None)
            if novel_name not in _update_progress or _update_progress[novel_name].get("running"):
                _update_progress[novel_name] = {"running": False, "message": "已结束"}
            lock.release()

    return StreamingResponse(gen(), media_type="text/event-stream")


def sync_memory_single_chapter(novel_name: str, chapter_index: int) -> None:
    """单章记忆提取（无 SSE）：世界观 → 时间线/实体索引 → 实体档案 → 可选近章摘要。"""
    memory_service.init_memory_files(novel_name)
    chapters = novel_service.get_chapters(novel_name)
    if not chapters or chapter_index < 0 or chapter_index >= len(chapters):
        return

    abs_idx = chapter_index
    ch = chapters[abs_idx]
    ch_title = ch.get("title", f"第{abs_idx + 1}章")
    ch_text = ch.get("text", "")

    existing_wv = memory_service.read_worldview(novel_name)
    existing_tl = memory_service.read_timeline(novel_name)
    summary_data = memory_service.read_recent_summary(novel_name)

    judge_prompt = WORLDVIEW_JUDGE_PROMPT.format(
        existing_worldview=existing_wv or "（空，尚未建立）",
        chapter_title=ch_title,
        chapter_text=ch_text,
    )
    judge_result = llm_service.generate_sync(
        [{"role": "user", "content": judge_prompt}],
        max_tokens=8,
    )
    cleaned = judge_result.strip().lstrip("，。、：: \n")
    need_update = cleaned.startswith("是")

    if need_update:
        update_prompt = WORLDVIEW_UPDATE_PROMPT.format(
            existing_worldview=existing_wv or "（空，请根据本章建立初始世界观）",
            chapter_title=ch_title,
            chapter_text=ch_text,
        )
        existing_wv = llm_service.generate_sync(
            [{"role": "user", "content": update_prompt}],
            max_tokens=settings.llm_max_tokens,
        )
        memory_service.append_worldview(novel_name, abs_idx, existing_wv)

    tl_prompt = TIMELINE_PROMPT.format(
        chapter_title=ch_title,
        chapter_text=ch_text,
    )
    tl_raw = llm_service.generate_sync(
        [{"role": "user", "content": tl_prompt}],
        max_tokens=settings.llm_max_tokens,
    )
    tl_content, entities = _parse_entities(tl_raw)

    if tl_content:
        try:
            emb = embedding_service.encode_single(tl_content)
        except Exception:
            emb = []
        existing_tl.append(
            {
                "chapter_index": abs_idx,
                "chapter": ch_title,
                "content": tl_content,
                "entities": entities,
                "embedding": emb,
            }
        )
        if entities:
            memory_service.update_entity_index(novel_name, abs_idx, entities)
            _apply_entity_profiles_llm(novel_name, entities, ch_text, abs_idx)

    memory_service.write_timeline(novel_name, existing_tl)

    current_summary = summary_data.get("recent_summary", "")
    current_recent_3 = summary_data.get("recent_3_chapters", [])
    memory_service.write_recent_summary(
        novel_name, current_recent_3, current_summary, abs_idx
    )

    if chapter_index == len(chapters) - 1:
        ch_recent_4_to_10 = chapters[-10:-3] if len(chapters) > 3 else []
        if ch_recent_4_to_10:
            ch_text_all = "\n\n".join(
                f"### {c['title']}\n{c['text']}" for c in ch_recent_4_to_10
            )
            sum_prompt = SUMMARY_PROMPT.format(chapters_text=ch_text_all)
            sum_result = llm_service.generate_sync(
                [{"role": "user", "content": sum_prompt}],
                max_tokens=settings.llm_max_tokens,
            )
        else:
            sum_result = ""

        recent_3 = [c["text"] for c in chapters[-3:]]
        memory_service.write_recent_summary(
            novel_name, recent_3, sum_result, len(chapters) - 1
        )
