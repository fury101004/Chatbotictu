from typing import Any, Dict, Optional
import re
import time

from config.system_prompt import get_system_prompt
from config.rag_tools import get_tool_profile, is_valid_rag_tool
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from shared.prompt_loader import render_prompt
from services.chat.session_service import (
    append_session_history,
    get_last_call_at,
    get_session_history,
    get_session_language,
    get_session_state,
    mark_call,
    set_session_language,
)

from services.llm.langchain_service import invoke_text_prompt_chain
from services.llm.llm_service import get_model, resolve_model_choice
from services.rag.ictu_scope_service import normalize_scope_text

_GENERATION_PROMPT_TEMPLATE = ChatPromptTemplate.from_messages(
    [
        MessagesPlaceholder("history"),
        ("user", "{prompt}"),
    ]
)

DANGEROUS_KEYWORDS = [
    "multilingual_handler",
    "gemini_client",
    "vector_store",
    "chat_multilingual",
    ".py",
    ".js",
    ".tsx",
    "def ",
    "import ",
    "from ",
    "session_state",
    "BOT_RULE_FULL",
    "safety_settings",
    "BLOCK_NONE",
    "generate_content",
    "```python",
    "source code",
    "ai viết",
    "ai code",
    "file nào",
    "who wrote",
    "who created",
]

_ENGLISH_SWITCH_MARKERS = (
    "english",
    "speak english",
    "use english",
    "reply in english",
    "trả lời bằng tiếng Anh",
    "nói tiếng Anh",
    "switch to english",
)
_VIETNAMESE_SWITCH_MARKERS = (
    "vietnamese",
    "tiếng Việt",
    "dùng tiếng Việt",
    "trả lời tiếng Việt",
    "switch to vietnamese",
    "về tiếng Việt",
)
_NORMALIZED_ENGLISH_SWITCH_MARKERS = tuple(normalize_scope_text(marker) for marker in _ENGLISH_SWITCH_MARKERS)
_NORMALIZED_VIETNAMESE_SWITCH_MARKERS = tuple(normalize_scope_text(marker) for marker in _VIETNAMESE_SWITCH_MARKERS)


def _get_session(sid: str) -> Dict[str, Any]:
    return get_session_state(sid)


def _detect_switch(text: str) -> Optional[str]:
    normalized = normalize_scope_text(text)

    if any(marker in normalized for marker in _NORMALIZED_ENGLISH_SWITCH_MARKERS):
        return "en"
    if any(marker in normalized for marker in _NORMALIZED_VIETNAMESE_SWITCH_MARKERS):
        return "vi"
    return None


def get_current_language(sid: str) -> str:
    return get_session_language(sid)


def _clean_context(context_text: str) -> str:
    lines = context_text.splitlines()
    clean_lines = []
    for line in lines:
        lowered = line.lower()
        if any(keyword in lowered for keyword in DANGEROUS_KEYWORDS):
            continue
        if line.strip().startswith("```"):
            continue
        if len(line) > 800:
            line = line[:800] + "..."
        clean_lines.append(line)
    return "\n".join(clean_lines[:250]).strip()


def _build_language_instruction(current_lang: str) -> str:
    if current_lang == "en":
        return (
            "Reply 100% in English. Do not mix Vietnamese unless the user asks to switch back. "
            "Be clear, professional, sufficiently detailed, and natural."
        )
    return (
        "BẮT BUỘC trả lời 100% bằng tiếng Việt tự nhiên, rõ ràng, dễ hiểu. "
        "Không trộn tiếng Anh trừ khi người dùng yêu cầu chuyển ngôn ngữ."
    )


def _build_output_instruction(current_lang: str) -> str:
    if current_lang == "en":
        return (
            "- Answer directly first, then explain with enough professional detail for the user to understand the reasoning and practical implications.\n"
            "- When the context contains procedures, requirements, deadlines, documents, eligibility, exceptions, units, locations, or years, preserve those details and structure them with clear bullet points or short sections.\n"
            "- If the context is partial, state the reliable part, explain what is missing, and end with exactly one short clarification question.\n"
            "- Prefer a well-structured answer of about 2-5 short paragraphs or bullet groups. Do not be overly terse, but do not invent details beyond the current context."
        )

    return (
        "- Trả lời trực tiếp ý chính ngay phần đầu, sau đó giải thích đủ chi tiết theo hướng chuyên môn để người dùng hiểu căn cứ và cách áp dụng.\n"
        "- Nếu ngữ cảnh có quy trình, điều kiện, hồ sơ, thời hạn, năm học, đối tượng áp dụng, ngoại lệ, đơn vị xử lý hoặc địa điểm, phải giữ các chi tiết đó và trình bày bằng gạch đầu dòng hoặc các đoạn ngắn rõ ràng.\n"
        "- Nếu ngữ cảnh chỉ có một phần thông tin, hãy nêu phần chắc chắn, giải thích phần còn thiếu, rồi kết thúc bằng đúng 1 câu hỏi làm rõ ngắn.\n"
        "- Ưu tiên câu trả lời có cấu trúc khoảng 2-5 đoạn ngắn hoặc nhóm gạch đầu dòng. Không trả lời cụt lủn, nhưng cũng không bịa thêm ngoài ngữ cảnh hiện tại."
    )


def _empty_context_text(current_lang: str) -> str:
    if current_lang == "en":
        return "No relevant context is available yet."
    return "Chưa có thêm ngữ cảnh liên quan."


def _session_history_to_lc_messages(history: list[dict[str, str]]):
    messages = []
    for item in history[-10:]:
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if item.get("role") == "user":
            messages.append(HumanMessage(content=content))
        else:
            messages.append(AIMessage(content=content))
    return messages


_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", flags=re.IGNORECASE | re.DOTALL)
_THINK_TAG_RE = re.compile(r"</?think>", flags=re.IGNORECASE)


def _sanitize_model_reply(reply: str) -> str:
    cleaned = str(reply or "")
    cleaned = _THINK_BLOCK_RE.sub("", cleaned)
    cleaned = _THINK_TAG_RE.sub("", cleaned)
    return cleaned.strip()


def _knowledge_scope_label(current_lang: str, rag_tool: Optional[str]) -> str:
    profile = get_tool_profile(rag_tool) if is_valid_rag_tool(rag_tool) else None
    if profile:
        return str(profile.get("label", "")).strip()
    return "General ICTU knowledge" if current_lang == "en" else "Tri thức ICTU tổng quát"


def _build_final_prompt(
    system_prompt: str,
    current_lang: str,
    safe_context: str,
    user_question: str,
    rag_tool: Optional[str] = None,
) -> str:
    language_instruction = _build_language_instruction(current_lang)
    output_instruction = _build_output_instruction(current_lang)
    knowledge_scope = _knowledge_scope_label(current_lang, rag_tool)
    no_info_reply = (
        "This information is not currently available in my documents."
        if current_lang == "en"
        else "Thông tin này hiện chưa có trong tài liệu của em."
    )

    if current_lang == "en":
        rules_heading = "TURN RULES"
        output_heading = "OUTPUT CONTRACT"
        context_heading = "CURRENT CONTEXT"
        question_heading = "USER QUESTION"
        scope_instruction = f"Current knowledge scope: {knowledge_scope}."
        context_instruction = "Only answer from the current context below."
        qa_instruction = (
            "If the context contains a matching Question/Answer pair, use that answer as the main basis and preserve its "
            "numbers, thresholds, years, and conditions exactly."
        )
        clarification_instruction = (
            "If the context is relevant but incomplete, state the reliable part first and then ask exactly one short "
            "clarification question."
        )
        ambiguity_instruction = (
            "If the question lacks a required discriminator such as academic year, semester, round, cohort, training "
            "system, or target group, ask exactly one short clarification question instead of guessing."
        )
        privacy_instruction = "Do not mention sources, filenames, routes, tool names, or internal system details."
    else:
        rules_heading = "LUẬT CHO LƯỢT HIỆN TẠI"
        output_heading = "YÊU CẦU ĐẦU RA"
        context_heading = "NGỮ CẢNH HIỆN TẠI"
        question_heading = "CÂU HỎI NGƯỜI DÙNG"
        scope_instruction = f"Phạm vi tri thức hiện tại: {knowledge_scope}."
        context_instruction = "Chỉ được trả lời từ ngữ cảnh hiện tại bên dưới."
        qa_instruction = (
            "Nếu ngữ cảnh có cặp Question/Answer khớp với câu hỏi, hãy lấy Answer làm căn cứ chính và giữ nguyên số "
            "liệu, ngưỡng điểm, năm học, điều kiện."
        )
        clarification_instruction = (
            "Nếu ngữ cảnh liên quan nhưng chưa đủ để kết luận đầy đủ, hãy nêu rõ phần chắc chắn trước rồi hỏi lại đúng "
            "một câu ngắn để làm rõ."
        )
        ambiguity_instruction = (
            "Nếu câu hỏi thiếu mốc phân biệt bắt buộc như năm học, học kỳ, đợt, khóa, hệ đào tạo hoặc đối tượng áp "
            "dụng, hãy hỏi lại đúng một câu ngắn thay vì tự đoán."
        )
        privacy_instruction = "Không nêu tên nguồn, tên file, route, tool hay chi tiết hệ thống nội bộ."

    return render_prompt(
        "rag_prompt.md",
        system_prompt=system_prompt,
        rules_heading=rules_heading,
        language_instruction=language_instruction,
        scope_instruction=scope_instruction,
        context_instruction=context_instruction,
        qa_instruction=qa_instruction,
        clarification_instruction=clarification_instruction,
        no_info_reply=no_info_reply,
        ambiguity_instruction=ambiguity_instruction,
        privacy_instruction=privacy_instruction,
        output_heading=output_heading,
        output_instruction=output_instruction,
        context_heading=context_heading,
        safe_context=safe_context,
        question_heading=question_heading,
        user_question=user_question,
    )


def chat_multilingual(
    user_question: str,
    context_text: str,
    session_id: str,
    rag_tool: Optional[str] = None,
    selected_model: Optional[str] = None,
) -> tuple[str, Optional[str]]:
    session = _get_session(session_id)

    switch = _detect_switch(user_question)
    if switch:
        set_session_language(session_id, switch)
        reply = "Đã chuyển sang tiếng Việt." if switch == "vi" else "Switched to English."
        append_session_history(
            session_id,
            [
                {"role": "user", "content": user_question},
                {"role": "model", "content": reply},
            ],
        )
        return reply, "local:language_switch"

    current_lang = get_session_language(session_id)

    if any(keyword in user_question.lower() for keyword in ["ai viết", "ai code", "source", "file nào", "who wrote"]):
        reply = "Thông tin này hiện chưa công khai." if current_lang == "vi" else "This information is not public."
        append_session_history(
            session_id,
            [
                {"role": "user", "content": user_question},
                {"role": "model", "content": reply},
            ],
        )
        return reply, "local:guardrail"

    now = time.time()
    last_call_at = get_last_call_at(session_id)
    if last_call_at is not None and now - last_call_at < 0.7:
        time.sleep(0.5)
    mark_call(session_id, now)

    safe_context = _clean_context(context_text) or _empty_context_text(current_lang)
    system_prompt = get_system_prompt().strip()
    final_prompt = _build_final_prompt(
        system_prompt,
        current_lang,
        safe_context,
        user_question,
        rag_tool=rag_tool,
    )
    history_messages = _session_history_to_lc_messages(get_session_history(session_id))

    if get_model() is None:
        reply = (
            "Trợ lý AI chưa được cấu hình xong. Bạn kiểm tra lại GROQ_API_KEY hoặc cấu hình Ollama rồi thử lại nhé."
            if current_lang == "vi"
            else "The AI assistant is not configured yet. Please check GROQ_API_KEY or your Ollama configuration and try again."
        )
        append_session_history(
            session_id,
            [
                {"role": "user", "content": user_question},
                {"role": "model", "content": reply},
            ],
        )
        return reply, "unconfigured"

    for attempt in range(3):
        try:
            preferred_model, rotate_model = resolve_model_choice(selected_model)
            reply, used_model = invoke_text_prompt_chain(
                _GENERATION_PROMPT_TEMPLATE,
                {
                    "history": history_messages,
                    "prompt": final_prompt,
                },
                generation_config={"temperature": 0.1, "max_output_tokens": 1800},
                request_options={"timeout": 90},
                preferred_model=preferred_model,
                rotate=rotate_model,
            )
            reply = _sanitize_model_reply(reply)
            primary_model = get_model(preferred_model)
            if not rotate_model and primary_model is not None and used_model != primary_model.label:
                print(f"chat_multilingual switched to fallback model: {used_model}")

            if reply:
                append_session_history(
                    session_id,
                    [
                        {"role": "user", "content": user_question},
                        {"role": "model", "content": reply},
                    ],
                )
                return reply, used_model
        except Exception as exc:
            print(f"LLM error (attempt {attempt + 1}): {exc}")

    fallback_reply = (
        "Mình đang kiểm tra thêm thông tin trong tài liệu, bạn thử hỏi lại giúp mình nhé."
        if current_lang == "vi"
        else "I'm checking the documents again. Please try asking again in a moment."
    )
    return fallback_reply, "llm:error"

