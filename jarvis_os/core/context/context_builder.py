from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from jarvis_os.core.domain.entities import LLMMessage

from .exceptions import ContextBuilderError
from .models import ContextAssemblyResult, ContextPriority, ContextSection
from .token_budget import ContextBudget


TokenEstimator = Callable[[str], int]


class ContextBuilder:
    """Build final prompt payload for the LLM.

    Requirements satisfied:
      - No Ollama knowledge.
      - Deterministic, rule-based.
      - Thread-safe: no shared mutable state.
      - Enforces token budget using provided estimator.
      - Trims and prioritizes sections.
      - Supports future summarization hooks via callbacks (not implemented).
    """

    def __init__(
        self,
        system_prompt: str,
        budget: ContextBudget,
        token_estimator: Optional[TokenEstimator] = None,
    ) -> None:
        self._system_prompt = system_prompt
        self._budget = budget
        self._token_estimator = token_estimator or (lambda s: len((s or "").split()))
        self._lock = threading.Lock()

    def build(
        self,
        user_request: str,
        conversation_history: Sequence[LLMMessage] = (),
        retrieved_memories: Sequence[ContextSection] = (),
        retrieved_documents: Sequence[ContextSection] = (),
        runtime_context: Dict[str, Any] | None = None,
    ) -> ContextAssemblyResult:
        if runtime_context is None:
            runtime_context = {}

        if not isinstance(user_request, str) or not user_request.strip():
            raise ContextBuilderError("user_request must be a non-empty string")

        with self._lock:
            warnings: List[str] = []

            # Compose prompt sections.
            history_sections: List[ContextSection] = []
            for msg in conversation_history:
                if not isinstance(msg.content, str):
                    continue
                # Map roles to priority.
                pri = ContextPriority.HISTORY
                if msg.role == "user":
                    pri = ContextPriority.USER
                history_sections.append(
                    ContextSection(
                        name=f"history:{msg.role}",
                        priority=pri,
                        content=msg.content,
                        metadata={"role": msg.role},
                    )
                )

            runtime_text = (
                "".join(f"{k}: {v}\n" for k, v in sorted(runtime_context.items()))
                if runtime_context
                else ""
            )
            runtime_sections: List[ContextSection] = []
            if runtime_text.strip():
                runtime_sections.append(
                    ContextSection(
                        name="runtime_context",
                        priority=ContextPriority.RUNTIME,
                        content=runtime_text.strip(),
                        metadata={"keys": list(sorted(runtime_context.keys()))},
                    )
                )

            # Ensure system prompt always included conceptually (counted).
            included: List[ContextSection] = []
            excluded: List[ContextSection] = []

            # Collect all candidate sections with priorities.
            candidates: List[ContextSection] = []
            candidates.extend(list(retrieved_memories))
            candidates.extend(list(retrieved_documents))
            candidates.extend(runtime_sections)
            candidates.extend(history_sections)

            # Stable deterministic ordering: sort by priority desc, then name.
            candidates_sorted = sorted(
                candidates,
                key=lambda s: (-int(s.priority.value), s.name),
            )

            # Budgeting: system prompt + included sections + user request.
            remaining = self._budget.max_prompt_tokens - self._token_estimator(self._system_prompt)
            if remaining < 0:
                warnings.append("System prompt exceeds budget; truncation may occur.")
                remaining = 0

            for section in candidates_sorted:
                sec_tokens = self._token_estimator(section.content)
                if sec_tokens <= remaining:
                    included.append(section)
                    remaining -= sec_tokens
                else:
                    # If nothing fits, stop (deterministic trimming)
                    if remaining <= 0:
                        excluded.append(section)
                    else:
                        # Trim content to fit by rough token count.
                        words = section.content.split()
                        keep_n = min(len(words), remaining)
                        if keep_n > 0:
                            trimmed = " ".join(words[:keep_n])
                            included.append(
                                ContextSection(
                                    name=section.name,
                                    priority=section.priority,
                                    content=trimmed,
                                    metadata=section.metadata,
                                )
                            )
                        else:
                            excluded.append(section)
                        remaining = 0

                if remaining <= 0:
                    # any further sections are excluded
                    continue

            # Build final LLM messages (provider-agnostic):
            prompt_messages: List[Tuple[str, str]] = []
            prompt_messages.append(("system", self._system_prompt))

            for sec in included:
                # Convert context sections into a user message prefix.
                prompt_messages.append(("user", f"[{sec.name}]\n{sec.content}"))

            prompt_messages.append(("user", user_request.strip()))

            budget_used = self._budget.max_prompt_tokens - remaining

            return ContextAssemblyResult(
                system_prompt=self._system_prompt,
                prompt_messages=tuple(prompt_messages),
                included_sections=tuple(included),
                excluded_sections=tuple(excluded),
                budget=budget_used,
                warnings=tuple(warnings),
            )

