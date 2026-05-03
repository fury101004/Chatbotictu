from __future__ import annotations

from typing import Optional

from langchain_core.prompts import ChatPromptTemplate

from config.rag_tools import FALLBACK_RAG_NODE, RAG_TOOL_PROFILES


_RAW_TEXT_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("human", "{prompt}"),
    ]
)


def _build_rag_router_prompt(message: str) -> str:
    tool_descriptions = "\n".join(
        f"- {tool_name}: {profile.get('description', profile.get('label', tool_name))}"
        for tool_name, profile in RAG_TOOL_PROFILES.items()
    )

    return f"""You are the RAG tool router for an ICTU chatbot.

Goal:
- Choose exactly one RAG tool for the user question.
- Do not answer the question.
- Return only valid JSON.

Available tools:
{tool_descriptions}
- fallback_rag: use this when the question is ambiguous, spans multiple groups, or no specific tool is reliable.

Required JSON:
{{
  "tool": "<tool_name>",
  "reason": "one short reason",
  "confidence": 0.0
}}

User question:
{message}
"""


_RAG_ROUTER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Bạn là bộ định tuyến cho hệ thống RAG của trường. "
            "Không trả lời nội dung câu hỏi. "
            "Chỉ trả về JSON hợp lệ theo format "
            '{"tool":"<tool_name>","reason":"<1 câu ngắn>","confidence":0.0}.',
        ),
        (
            "human",
            "Chỉ được chọn 1 trong các tool sau:\n"
            "{tool_descriptions}\n"
            "- fallback_rag: dùng khi câu hỏi mơ hồ, không chắc chắn, hoặc liên quan nhiều nhóm.\n\n"
            "Câu hỏi người dùng:\n"
            "{message}",
        ),
    ]
)

_RETRIEVAL_FLOW_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Bạn là bộ lập kế hoạch truy xuất trước khi chatbot trả lời. "
            "Không trả lời câu hỏi của người dùng. "
            "Chỉ trả về JSON hợp lệ với các trường source, priority, reason, confidence.",
        ),
        (
            "human",
            "Nhóm tri thức RAG đã được router gợi ý:\n"
            "{current_tool}\n\n"
            "Mô tả các nhóm tri thức:\n"
            "{tool_descriptions}\n\n"
            "Nguồn có thể chọn:\n"
            "- local_data: dùng corpus nội bộ đã nạp, gồm sổ tay sinh viên, quy định, FAQ, tài liệu upload và vector store.\n"
            "- web_search: dùng tìm kiếm web ưu tiên domain chính thức ICTU cho thông tin mới, thông báo, lịch, tin tức, tuyển sinh, deadline, số liệu/cơ cấu có thể thay đổi.\n"
            "- hybrid: lấy local_data làm nền và bổ sung web_search, hoặc web_search trước rồi đối chiếu local_data.\n\n"
            "Quy tắc quyết định:\n"
            "- Chọn local_data/local_first khi câu hỏi hỏi về nội dung ổn định trong tài liệu đã nạp: sổ tay sinh viên, quy chế, quy định, điều kiện, định nghĩa, quy trình, câu hỏi Q&A có sẵn.\n"
            "- Chọn web_search/web_first khi câu hỏi có dấu hiệu thời gian thực hoặc cần cập nhật: hôm nay, mới nhất, gần đây, năm nay, thông báo mới, lịch, deadline, tuyển sinh hiện tại, chỉ tiêu, học phí mới, tin tức.\n"
            "- Chọn hybrid khi câu hỏi cần cả quy định nền trong tài liệu nội bộ và tình trạng/thông báo mới trên website.\n"
            "- Nếu không chắc chắn, ưu tiên local_data/local_first, trừ khi câu hỏi rõ ràng cần thông tin mới.\n\n"
            "JSON bắt buộc:\n"
            "{\n"
            '  "source": "local_data | web_search | hybrid",\n'
            '  "priority": "local_first | web_first",\n'
            '  "reason": "một câu ngắn nêu lý do",\n'
            '  "confidence": 0.0\n'
            "}\n\n"
            "Câu hỏi người dùng:\n"
            "{message}",
        ),
    ]
)


def _build_retrieval_flow_prompt(message: str, rag_tool: Optional[str]) -> str:
    tool_descriptions = "\n".join(
        f"- {tool_name}: {profile.get('description', profile.get('label', tool_name))}"
        for tool_name, profile in RAG_TOOL_PROFILES.items()
    )
    current_tool = rag_tool if rag_tool in RAG_TOOL_PROFILES else FALLBACK_RAG_NODE

    return f"""Bạn là bộ lập kế hoạch truy xuất trước khi chatbot trả lời.

Mục tiêu:
- Quyết định câu hỏi nên lấy thông tin từ dữ liệu nội bộ, web search ICTU, hay kết hợp cả hai.
- Không trả lời câu hỏi của người dùng.
- Chỉ trả về JSON hợp lệ, không thêm giải thích ngoài JSON.

Nguồn có thể chọn:
- local_data: dùng corpus nội bộ đã nạp, gồm sổ tay sinh viên, quy định, FAQ, tài liệu upload và vector store.
- web_search: dùng tìm kiếm web ưu tiên domain chính thức ICTU cho thông tin mới, thông báo, lịch, tin tức, tuyển sinh, deadline, số liệu/cơ cấu có thể thay đổi.
- hybrid: lấy local_data làm nền và bổ sung web_search, hoặc web_search trước rồi đối chiếu local_data.

Nhóm tri thức RAG đã được router gợi ý:
{current_tool}

Mô tả các nhóm tri thức:
{tool_descriptions}

Quy tắc quyết định:
- Chọn local_data/local_first khi câu hỏi hỏi về nội dung ổn định trong tài liệu đã nạp: sổ tay sinh viên, quy chế, quy định, điều kiện, định nghĩa, quy trình, câu hỏi Q&A có sẵn.
- Chọn web_search/web_first khi câu hỏi có dấu hiệu thời gian thực hoặc cần cập nhật: "hôm nay", "mới nhất", "gần đây", "năm nay", "thông báo mới", lịch, deadline, tuyển sinh hiện tại, chỉ tiêu, học phí mới, tin tức.
- Chọn hybrid khi câu hỏi cần cả quy định nền trong tài liệu nội bộ và tình trạng/thông báo mới trên website.
- Nếu không chắc chắn, ưu tiên local_data/local_first, trừ khi câu hỏi rõ ràng cần thông tin mới.

JSON bắt buộc:
{{
  "source": "local_data | web_search | hybrid",
  "priority": "local_first | web_first",
  "reason": "một câu ngắn nêu lý do",
  "confidence": 0.0
}}

Câu hỏi người dùng:
{message}
"""
