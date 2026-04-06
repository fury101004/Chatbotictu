from __future__ import annotations

from collections.abc import Callable
from typing import Any, Optional

from models.chat import ChatGraphState

try:
    from langgraph.graph import END, START, StateGraph  # type: ignore
except ImportError:  # pragma: no cover
    END = "__end__"
    START = "__start__"
    StateGraph = None


Node = Callable[[ChatGraphState], ChatGraphState]


class _SequentialGraph:
    def __init__(
        self,
        normalize: Node,
        persist_user: Node,
        guardrails: Node,
        generate: Node,
        finalize: Node,
        retrieve: Optional[Node] = None,
        route_rag: Optional[Node] = None,
        tool_nodes: Optional[dict[str, Node]] = None,
        default_tool: Optional[str] = None,
    ) -> None:
        self._normalize = normalize
        self._persist_user = persist_user
        self._guardrails = guardrails
        self._retrieve = retrieve
        self._route_rag = route_rag
        self._tool_nodes = tool_nodes or {}
        self._default_tool = default_tool
        self._generate = generate
        self._finalize = finalize

    def invoke(self, state: ChatGraphState) -> ChatGraphState:
        current = self._normalize(dict(state))
        if current.get("stop_graph"):
            return current

        current = self._persist_user(current)
        current = self._guardrails(current)

        if not current.get("handled"):
            if self._tool_nodes and self._route_rag is not None:
                current = self._route_rag(current)
                tool_name = current.get("rag_tool") or self._default_tool
                node = self._tool_nodes.get(tool_name or "") or self._tool_nodes.get(self._default_tool or "")
                if node is not None:
                    current = node(current)
            elif self._retrieve is not None:
                current = self._retrieve(current)

            current = self._generate(current)

        return self._finalize(current)


class RAGChatGraph:
    def __init__(
        self,
        normalize: Node,
        persist_user: Node,
        guardrails: Node,
        generate: Node,
        finalize: Node,
        retrieve: Optional[Node] = None,
        route_rag: Optional[Node] = None,
        tool_nodes: Optional[dict[str, Node]] = None,
        default_tool: Optional[str] = None,
    ) -> None:
        self._normalize = normalize
        self._persist_user = persist_user
        self._guardrails = guardrails
        self._retrieve = retrieve
        self._route_rag = route_rag
        self._tool_nodes = tool_nodes or {}
        self._default_tool = default_tool
        self._generate = generate
        self._finalize = finalize
        self.engine = "langgraph" if StateGraph is not None else "sequential_fallback"
        self._graph = self._build()

    def _build(self) -> Any:
        if StateGraph is None:
            return _SequentialGraph(
                normalize=self._normalize,
                persist_user=self._persist_user,
                guardrails=self._guardrails,
                retrieve=self._retrieve,
                route_rag=self._route_rag,
                tool_nodes=self._tool_nodes,
                default_tool=self._default_tool,
                generate=self._generate,
                finalize=self._finalize,
            )

        workflow = StateGraph(ChatGraphState)
        workflow.add_node("normalize", self._normalize)
        workflow.add_node("persist_user", self._persist_user)
        workflow.add_node("guardrails", self._guardrails)
        workflow.add_node("generate", self._generate)
        workflow.add_node("finalize", self._finalize)

        workflow.add_edge(START, "normalize")
        workflow.add_conditional_edges(
            "normalize",
            self._route_after_normalize,
            {
                "persist_user": "persist_user",
                END: END,
            },
        )
        workflow.add_edge("persist_user", "guardrails")

        if self._tool_nodes and self._route_rag is not None:
            workflow.add_node("route_rag", self._route_rag)
            workflow.add_conditional_edges(
                "guardrails",
                self._route_after_guardrails_to_tools,
                {
                    "route_rag": "route_rag",
                    "finalize": "finalize",
                },
            )

            route_targets: dict[str, str] = {}
            for tool_name, node in self._tool_nodes.items():
                workflow.add_node(tool_name, node)
                workflow.add_edge(tool_name, "generate")
                route_targets[tool_name] = tool_name

            workflow.add_conditional_edges("route_rag", self._route_after_route_rag, route_targets)
        else:
            workflow.add_node("retrieve", self._retrieve)
            workflow.add_conditional_edges(
                "guardrails",
                self._route_after_guardrails_to_single_retriever,
                {
                    "retrieve": "retrieve",
                    "finalize": "finalize",
                },
            )
            workflow.add_edge("retrieve", "generate")

        workflow.add_edge("generate", "finalize")
        workflow.add_edge("finalize", END)
        return workflow.compile()

    @staticmethod
    def _route_after_normalize(state: ChatGraphState) -> str:
        return END if state.get("stop_graph") else "persist_user"

    @staticmethod
    def _route_after_guardrails_to_single_retriever(state: ChatGraphState) -> str:
        return "finalize" if state.get("handled") else "retrieve"

    @staticmethod
    def _route_after_guardrails_to_tools(state: ChatGraphState) -> str:
        return "finalize" if state.get("handled") else "route_rag"

    def _route_after_route_rag(self, state: ChatGraphState) -> str:
        tool_name = state.get("rag_tool") or self._default_tool
        if tool_name in self._tool_nodes:
            return str(tool_name)
        return str(self._default_tool)

    def invoke(self, state: ChatGraphState) -> ChatGraphState:
        return self._graph.invoke(state)






