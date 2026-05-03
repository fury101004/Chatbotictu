from typing import Any, Dict, Optional
import re
import time

from config.system_prompt import get_system_prompt
from config.rag_tools import get_tool_profile, is_valid_rag_tool
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from services.langchain_service import invoke_text_prompt_chain
from services.llm_service import get_model, resolve_model_choice

SESSIONS: Dict[str, Dict[str, Any]] = {}
LAST_CALL: Dict[str, float] = {}
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
    "SESSIONS",
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


def _get_session(sid: str) -> Dict[str, Any]:
    if sid not in SESSIONS:
        SESSIONS[sid] = {"lang": "vi", "history": []}
    return SESSIONS[sid]


def _detect_switch(text: str) -> Optional[str]:
    normalized = re.sub(r"\s+", " ", text.lower()).strip()

    english_markers = [
        "english",
        "speak english",
        "use english",
        "reply in english",
        "trả lời bằng tiếng anh",
        "tra loi bang tieng anh",
        "nói tiếng anh",
        "noi tieng anh",
        "switch to english",
    ]
    vietnamese_markers = [
        "vietnamese",
        "tiếng việt",
        "tieng viet",
        "dùng tiếng việt",
        "dung tieng viet",
        "trả lời tiếng việt",
        "tra loi tieng viet",
        "switch to vietnamese",
        "về tiếng việt",
        "ve tieng viet",
    ]

    if any(marker in normalized for marker in english_markers):
        return "en"
    if any(marker in normalized for marker in vietnamese_markers):
        return "vi"
    return None


def get_current_language(sid: str) -> str:
    return _get_session(sid).get("lang", "vi") or "vi"


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


def _build_tool_instruction(current_lang: str, rag_tool: Optional[str]) -> str:
    profile = get_tool_profile(rag_tool) if is_valid_rag_tool(rag_tool) else None
    tool_label = str(profile.get("label", rag_tool)) if profile else None

    if current_lang == "en":
        if rag_tool == "school_policy_rag":
            detail = (
                "This turn is grounded in policy and regulation documents. Preserve document years, target audience, "
                "conditions, deadlines, and official constraints whenever they appear in context."
            )
        elif rag_tool == "student_handbook_rag":
            detail = (
                "This turn is grounded in handbook documents. Start with a short orientation-style explanation, "
                "then add practical details only if the context clearly contains them."
            )
        elif rag_tool == "student_faq_rag":
            detail = (
                "This turn is grounded in FAQ and operational guidance. Answer the user's question directly first, "
                "then list the next step, contact point, or location only if the context provides it."
            )
        else:
            detail = "Use the current context as the highest-priority source for this turn."

        if tool_label:
            return f"Current knowledge group: {tool_label}. {detail}"
        return detail

    if rag_tool == "school_policy_rag":
        detail = (
            "Lượt này ưu tiên tài liệu quy định/chính sách. Nếu ngữ cảnh có số văn bản, năm, đối tượng áp dụng, "
            "thời hạn hoặc điều kiện thì phải giữ nguyên các chi tiết đó."
        )
    elif rag_tool == "student_handbook_rag":
        detail = (
            "Lượt này ưu tiên sổ tay/cẩm nang. Hãy giải thích theo hướng định hướng, nêu bối cảnh áp dụng, "
            "sau đó trình bày các chi tiết thực hiện nếu ngữ cảnh có."
        )
    elif rag_tool == "student_faq_rag":
        detail = (
            "Lượt này ưu tiên FAQ/quy trình tác vụ. Hãy trả lời thẳng vào câu hỏi trước, "
            "sau đó mới nêu bước làm, nơi xử lý hoặc đầu mối liên hệ nếu ngữ cảnh có."
        )
    else:
        detail = "Ưu tiên độ chính xác của ngữ cảnh hiện tại hơn lịch sử hội thoại trước đó."

    if tool_label:
        return f"Nhóm tri thức hiện tại: {tool_label}. {detail}"
    return detail


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


def _build_final_prompt(
    system_prompt: str,
    current_lang: str,
    safe_context: str,
    user_question: str,
    rag_tool: Optional[str] = None,
) -> str:
    language_instruction = _build_language_instruction(current_lang)
    tool_instruction = _build_tool_instruction(current_lang, rag_tool)
    output_instruction = _build_output_instruction(current_lang)
    no_info_reply = (
        "This information is not currently available in my documents."
        if current_lang == "en"
        else "Thông tin này hiện chưa có trong tài liệu của em."
    )

    if current_lang == "en":
        return f"""{system_prompt}

TURN-SPECIFIC RULES:
- {language_instruction}
- {tool_instruction}
- If prior chat history conflicts with the current context, prioritize the current context.
- Only answer from the CURRENT CONTEXT section below.
- If CURRENT CONTEXT contains a matching **Question:**/**Answer:** pair, use the **Answer:** text as the primary answer and preserve its numbers, thresholds, years, and conditions exactly.
- If the current context contains relevant but partial information, state the reliable part first and then ask exactly one short clarification question for the missing discriminator.
- Reply with exactly "{no_info_reply}" only when the current context is empty or not relevant to the user's question.
- If the question is ambiguous because it lacks a required discriminator such as academic year, semester, round, intake, training system, or target group, and the context already hints at likely discriminators, mention those hints before asking exactly one short clarification question.
- Do not mention sources, filenames, tool names, routing, or internal system details.

OUTPUT STYLE:
{output_instruction}

CURRENT CONTEXT:
{safe_context}

USER QUESTION:
{user_question}
"""

    return f"""{system_prompt}

LUẬT CHO LƯỢT HIỆN TẠI:
- {language_instruction}
- {tool_instruction}
- Nếu lịch sử hội thoại trước mâu thuẫn với ngữ cảnh hiện tại, hãy ưu tiên ngữ cảnh hiện tại.
- Chỉ được trả lời từ phần NGỮ CẢNH HIỆN TẠI bên dưới.
- Nếu NGỮ CẢNH HIỆN TẠI có cặp `**Question:**`/`**Answer:**` khớp câu hỏi, hãy lấy phần `**Answer:**` làm căn cứ chính và giữ nguyên các số liệu, ngưỡng điểm, năm học, điều kiện.
- Nếu ngữ cảnh hiện tại có thông tin liên quan nhưng chưa đủ để kết luận đầy đủ, hãy nêu rõ phần chắc chắn trước rồi hỏi lại đúng 1 câu ngắn để làm rõ phần còn thiếu.
- Chỉ được trả lời đúng câu "{no_info_reply}" khi ngữ cảnh hiện tại không có thông tin liên quan đến câu hỏi của người dùng.
- Nếu câu hỏi mơ hồ vì thiếu mốc phân biệt bắt buộc như năm học, học kỳ, đợt, khóa, hệ đào tạo hoặc đối tượng áp dụng, và ngữ cảnh đã gợi ý được các mốc cần phân biệt, hãy nêu các mốc đó trước rồi hỏi lại đúng 1 câu ngắn để làm rõ.
- Không nêu tên nguồn, tên file, tên tool, route hay chi tiết hệ thống nội bộ.

YÊU CẦU ĐẦU RA:
{output_instruction}

NGỮ CẢNH HIỆN TẠI:
{safe_context}

CÂU HỎI NGƯỜI DÙNG:
{user_question}
"""


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
        session["lang"] = switch
        reply = "Đã chuyển sang tiếng Việt." if switch == "vi" else "Switched to English."
        session["history"].extend(
            [
                {"role": "user", "content": user_question},
                {"role": "model", "content": reply},
            ]
        )
        session["history"] = session["history"][-30:]
        return reply, "local:language_switch"

    current_lang = session.get("lang", "vi") or "vi"

    if any(keyword in user_question.lower() for keyword in ["ai viết", "ai code", "source", "file nào", "who wrote"]):
        reply = "Thông tin này hiện chưa công khai." if current_lang == "vi" else "This information is not public."
        session["history"].extend(
            [
                {"role": "user", "content": user_question},
                {"role": "model", "content": reply},
            ]
        )
        session["history"] = session["history"][-30:]
        return reply, "local:guardrail"

    now = time.time()
    if session_id in LAST_CALL and now - LAST_CALL[session_id] < 0.7:
        time.sleep(0.5)
    LAST_CALL[session_id] = now

    safe_context = _clean_context(context_text) or _empty_context_text(current_lang)
    system_prompt = get_system_prompt().strip()
    final_prompt = _build_final_prompt(
        system_prompt,
        current_lang,
        safe_context,
        user_question,
        rag_tool=rag_tool,
    )
    history_messages = _session_history_to_lc_messages(session["history"])

    if get_model() is None:
        reply = (
            "Trợ lý AI chưa được cấu hình xong. Bạn kiểm tra lại GROQ_API_KEY hoặc cấu hình Ollama rồi thử lại nhé."
            if current_lang == "vi"
            else "The AI assistant is not configured yet. Please check GROQ_API_KEY or your Ollama configuration and try again."
        )
        session["history"].extend(
            [
                {"role": "user", "content": user_question},
                {"role": "model", "content": reply},
            ]
        )
        session["history"] = session["history"][-30:]
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
                session["history"].extend(
                    [
                        {"role": "user", "content": user_question},
                        {"role": "model", "content": reply},
                    ]
                )
                session["history"] = session["history"][-30:]
                return reply, used_model
        except Exception as exc:
            print(f"LLM error (attempt {attempt + 1}): {exc}")

    fallback_reply = (
        "Mình đang kiểm tra thêm thông tin trong tài liệu, bạn thử hỏi lại giúp mình nhé."
        if current_lang == "vi"
        else "I'm checking the documents again. Please try asking again in a moment."
    )
    return fallback_reply, "llm:error"
