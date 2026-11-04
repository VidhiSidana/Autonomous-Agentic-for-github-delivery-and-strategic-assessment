"""
Improved Local LLM Gateway for the Samsung PRISM Unified Engineering Agent.

Improvements over the original:
  - Fully configurable via environment variables / config/settings.py
  - Supports multi-turn conversation (message history)
  - Supports system prompts
  - Model availability check on startup
  - Configurable temperature, max_tokens, timeout
  - Clean interface for future vLLM / OpenAI-compatible endpoints
  - No secrets exposed in logs or error messages
"""

import logging
import sys
from pathlib import Path
from typing import Optional

import requests

# Allow running standalone (python agent/llm.py)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    OLLAMA_BASE_URL,
    OLLAMA_MAX_TOKENS,
    OLLAMA_MODEL,
    OLLAMA_TEMPERATURE,
    OLLAMA_TIMEOUT,
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Message type alias
# ------------------------------------------------------------------
Message = dict  # {"role": "system"|"user"|"assistant", "content": str}


class LocalLLM:
    """
    Gateway to a locally running Ollama LLM.

    Provides a common interface so a future vLLM or OpenAI-compatible
    internal endpoint can be swapped in without changing the agent.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> None:
        self.model = model or OLLAMA_MODEL
        self.base_url = (base_url or OLLAMA_BASE_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else OLLAMA_TIMEOUT
        self.temperature = temperature if temperature is not None else OLLAMA_TEMPERATURE
        self.max_tokens = max_tokens if max_tokens is not None else OLLAMA_MAX_TOKENS
        self._chat_url = f"{self.base_url}/api/chat"
        self._tags_url = f"{self.base_url}/api/tags"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_availability(self) -> tuple[bool, str]:
        """
        Check whether Ollama is reachable and the configured model is available.

        Returns (available: bool, message: str).
        Does NOT raise — safe to call at startup.
        """
        try:
            response = requests.get(self._tags_url, timeout=5)
            response.raise_for_status()
            models = [m["name"] for m in response.json().get("models", [])]
            # Normalize: "qwen2.5:1.5b" may appear as "qwen2.5:1.5b" or "qwen2.5"
            model_base = self.model.split(":")[0]
            found = any(
                self.model == m or m.startswith(model_base)
                for m in models
            )
            if found:
                return True, f"Model '{self.model}' is available."
            available_list = ", ".join(models) if models else "(none)"
            return False, (
                f"Model '{self.model}' not found in Ollama. "
                f"Available: {available_list}. "
                f"Run: ollama pull {self.model}"
            )
        except requests.exceptions.ConnectionError:
            return False, (
                f"Cannot connect to Ollama at {self.base_url}. "
                "Ensure Ollama is running."
            )
        except requests.exceptions.RequestException as exc:
            return False, f"Ollama availability check failed: {exc}"

    def generate_response(self, prompt: str) -> str:
        """
        Generate a response to a plain string prompt.

        Convenience wrapper around chat() for single-turn use.
        """
        return self.chat([{"role": "user", "content": prompt}])

    def chat(
        self,
        messages: list[Message],
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Send a conversation (list of messages) to the LLM and return the reply.

        Parameters
        ----------
        messages:
            List of {"role": ..., "content": ...} dicts.
            Roles: "system", "user", "assistant".
        system_prompt:
            Convenience parameter. If provided, prepended as a system message
            before *messages*. Ignored if messages already starts with a system
            message.

        Returns
        -------
        str
            The assistant's reply, or an error string if the call fails.
        """
        content, _ = self.chat_with_metadata(messages, system_prompt=system_prompt)
        return content

    def chat_with_metadata(
        self,
        messages: list[Message],
        system_prompt: Optional[str] = None,
    ) -> tuple[str, dict]:
        """
        Send conversation to LLM and return both reply content and generation metadata
        (such as token counts and latency metrics from Ollama).
        """
        full_messages: list[Message] = []

        # Prepend system prompt if provided and not already present
        if system_prompt and (
            not messages or messages[0].get("role") != "system"
        ):
            full_messages.append({"role": "system", "content": system_prompt})

        full_messages.extend(messages)

        payload: dict = {
            "model": self.model,
            "messages": full_messages,
            "stream": False,
            "options": {
                "temperature": self.temperature,
            },
        }
        if self.max_tokens > 0:
            payload["options"]["num_predict"] = self.max_tokens

        try:
            response = requests.post(
                self._chat_url,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = response.json()
            content = result.get("message", {}).get("content", "")
            meta = {
                "prompt_eval_count": result.get("prompt_eval_count"),
                "eval_count": result.get("eval_count"),
                "total_duration": result.get("total_duration"),
                "load_duration": result.get("load_duration"),
                "prompt_eval_duration": result.get("prompt_eval_duration"),
                "eval_duration": result.get("eval_duration"),
            }
            return content, meta

        except requests.exceptions.ConnectionError:
            msg = (
                f"Cannot connect to Ollama at {self.base_url}. "
                "Ensure Ollama is running."
            )
            logger.error(msg)
            return msg, {}

        except requests.exceptions.Timeout:
            msg = f"Ollama request timed out after {self.timeout}s."
            logger.error(msg)
            return msg, {}

        except requests.exceptions.HTTPError as exc:
            msg = f"Ollama HTTP error: {exc.response.status_code}"
            logger.error(msg)
            return msg, {}

        except (KeyError, ValueError) as exc:
            msg = f"Unexpected Ollama response format: {exc}"
            logger.error(msg)
            return msg, {}

        except requests.exceptions.RequestException as exc:
            msg = f"LLM request failed: {type(exc).__name__}"
            logger.error(msg)
            return msg, {}


# ------------------------------------------------------------------
# Standalone test
# ------------------------------------------------------------------
if __name__ == "__main__":
    llm = LocalLLM()
    ok, status = llm.check_availability()
    print(f"Ollama availability: {status}")
    if ok:
        answer = llm.generate_response("What is the MCP protocol in one sentence?")
        print("\nQwen Response:", answer)
