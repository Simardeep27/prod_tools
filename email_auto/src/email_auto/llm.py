from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MlxLMClient:
    model_name: str
    default_max_tokens: int
    _model: Any = field(default=None, init=False, repr=False)
    _tokenizer: Any = field(default=None, init=False, repr=False)
    _generate: Any = field(default=None, init=False, repr=False)

    def complete(self, messages: list[dict[str, str]], max_tokens: int | None = None) -> str:
        self._ensure_loaded()
        prompt = self._build_prompt(messages)
        return self._generate(
            self._model,
            self._tokenizer,
            prompt=prompt,
            max_tokens=max_tokens or self.default_max_tokens,
            verbose=False,
        ).strip()

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            from mlx_lm import generate, load
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "mlx-lm is not installed. Run `uv add mlx-lm` inside the email_auto project."
            ) from exc

        self._model, self._tokenizer = load(self.model_name)
        self._generate = generate

    def _build_prompt(self, messages: list[dict[str, str]]) -> str:
        if hasattr(self._tokenizer, "apply_chat_template"):
            return self._tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )

        rendered = [f"{message['role'].upper()}: {message['content']}" for message in messages]
        rendered.append("ASSISTANT:")
        return "\n\n".join(rendered)
