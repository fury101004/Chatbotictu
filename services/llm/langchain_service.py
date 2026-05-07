from __future__ import annotations

from typing import Any, Optional

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from pydantic import ConfigDict, Field

from shared.message_utils import message_content
from services.llm.llm_service import PRIMARY_MODEL_NAME, generate_content_with_fallback


def _base_messages_to_chat_messages(input_messages: list[BaseMessage]) -> list[dict[str, str]]:
    chat_messages: list[dict[str, str]] = []
    for message in input_messages:
        role = str(getattr(message, "type", "human")).lower()
        if role == "human":
            mapped_role = "user"
        elif role == "ai":
            mapped_role = "assistant"
        elif role == "system":
            mapped_role = "system"
        else:
            mapped_role = "user"

        content = message_content(getattr(message, "content", ""))
        if content.strip():
            chat_messages.append({"role": mapped_role, "content": content})
    return chat_messages


class FallbackChatModel(BaseChatModel):
    generation_config: Optional[dict[str, Any]] = None
    request_options: Optional[dict[str, Any]] = None
    preferred_model: str = PRIMARY_MODEL_NAME
    rotate: bool = True
    invoke_fn: Any = Field(default=None, exclude=True)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def _llm_type(self) -> str:
        return "fallback-chat-model"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {
            "preferred_model": self.preferred_model,
            "rotate": self.rotate,
        }

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        payload = _base_messages_to_chat_messages(messages)
        invoke_fn = self.invoke_fn or generate_content_with_fallback
        response, used_model = invoke_fn(
            payload,
            generation_config=self.generation_config,
            request_options=self.request_options,
            preferred_model=self.preferred_model,
            rotate=self.rotate,
        )
        text = getattr(response, "text", "") or ""
        message = AIMessage(content=text, response_metadata={"used_model": used_model})
        generation = ChatGeneration(
            message=message,
            generation_info={"used_model": used_model},
        )
        return ChatResult(
            generations=[generation],
            llm_output={"used_model": used_model},
        )


def _build_chat_model(
    *,
    generation_config: Optional[dict] = None,
    request_options: Optional[dict] = None,
    preferred_model: str = PRIMARY_MODEL_NAME,
    rotate: bool = True,
) -> FallbackChatModel:
    return FallbackChatModel(
        generation_config=generation_config,
        request_options=request_options,
        preferred_model=preferred_model,
        rotate=rotate,
    )


def _parse_text_payload(message: BaseMessage) -> dict[str, str]:
    parser = StrOutputParser()
    response_metadata = getattr(message, "response_metadata", {}) or {}
    return {
        "text": parser.parse(message_content(getattr(message, "content", ""))),
        "used_model": str(response_metadata.get("used_model", "")),
    }


def _parse_json_payload(message: BaseMessage) -> dict[str, Any]:
    parser = JsonOutputParser()
    response_metadata = getattr(message, "response_metadata", {}) or {}
    raw_text = message_content(getattr(message, "content", ""))
    parsed: Optional[dict[str, Any]]
    try:
        parsed = parser.parse(raw_text)
    except Exception:
        parsed = None

    return {
        "parsed": parsed,
        "raw_text": raw_text,
        "used_model": str(response_metadata.get("used_model", "")),
    }


def _build_prompt_chain(
    prompt_template: ChatPromptTemplate,
    *,
    parser_fn: Any,
    generation_config: Optional[dict] = None,
    request_options: Optional[dict] = None,
    preferred_model: str = PRIMARY_MODEL_NAME,
    rotate: bool = True,
):
    model = _build_chat_model(
        generation_config=generation_config,
        request_options=request_options,
        preferred_model=preferred_model,
        rotate=rotate,
    )
    return prompt_template | model | RunnableLambda(parser_fn)


def _invoke_prompt_chain(
    prompt_template: ChatPromptTemplate,
    prompt_input: dict[str, Any],
    *,
    parser_fn: Any,
    generation_config: Optional[dict] = None,
    request_options: Optional[dict] = None,
    preferred_model: str = PRIMARY_MODEL_NAME,
    rotate: bool = True,
) -> dict[str, Any]:
    chain = _build_prompt_chain(
        prompt_template,
        parser_fn=parser_fn,
        generation_config=generation_config,
        request_options=request_options,
        preferred_model=preferred_model,
        rotate=rotate,
    )
    result = chain.invoke(prompt_input)
    return result if isinstance(result, dict) else {}


def build_text_prompt_chain(
    prompt_template: ChatPromptTemplate,
    *,
    generation_config: Optional[dict] = None,
    request_options: Optional[dict] = None,
    preferred_model: str = PRIMARY_MODEL_NAME,
    rotate: bool = True,
):
    return _build_prompt_chain(
        prompt_template,
        parser_fn=_parse_text_payload,
        generation_config=generation_config,
        request_options=request_options,
        preferred_model=preferred_model,
        rotate=rotate,
    )


def invoke_text_prompt_chain(
    prompt_template: ChatPromptTemplate,
    prompt_input: dict[str, Any],
    *,
    generation_config: Optional[dict] = None,
    request_options: Optional[dict] = None,
    preferred_model: str = PRIMARY_MODEL_NAME,
    rotate: bool = True,
) -> tuple[str, str]:
    result = _invoke_prompt_chain(
        prompt_template,
        prompt_input,
        parser_fn=_parse_text_payload,
        generation_config=generation_config,
        request_options=request_options,
        preferred_model=preferred_model,
        rotate=rotate,
    )
    return str(result.get("text", "")), str(result.get("used_model", ""))


def build_json_prompt_chain(
    prompt_template: ChatPromptTemplate,
    *,
    generation_config: Optional[dict] = None,
    request_options: Optional[dict] = None,
    preferred_model: str = PRIMARY_MODEL_NAME,
    rotate: bool = False,
):
    return _build_prompt_chain(
        prompt_template,
        parser_fn=_parse_json_payload,
        generation_config=generation_config,
        request_options=request_options,
        preferred_model=preferred_model,
        rotate=rotate,
    )


def invoke_json_prompt_chain(
    prompt_template: ChatPromptTemplate,
    prompt_input: dict[str, Any],
    *,
    generation_config: Optional[dict] = None,
    request_options: Optional[dict] = None,
    preferred_model: str = PRIMARY_MODEL_NAME,
    rotate: bool = False,
) -> tuple[Optional[dict[str, Any]], str, str]:
    result = _invoke_prompt_chain(
        prompt_template,
        prompt_input,
        parser_fn=_parse_json_payload,
        generation_config=generation_config,
        request_options=request_options,
        preferred_model=preferred_model,
        rotate=rotate,
    )
    parsed = result.get("parsed")
    raw_text = str(result.get("raw_text", ""))
    used_model = str(result.get("used_model", ""))
    return parsed if isinstance(parsed, dict) else None, raw_text, used_model

