"""設定から Analyzer を組み立てる. 既定はオフライン StubAnalyzer.

実 LLM を指定しても, 対応 API キーが無い・SDK が未導入なら StubAnalyzer に
フォールバックして起動を止めない（警告ログのみ・秘密情報は出さない）.
"""

from __future__ import annotations

import importlib.util
import logging

from app.analysis.llm import LLMAnalyzer
from app.analysis.stub import StubAnalyzer
from app.config import Settings
from app.ports.analyzer import Analyzer

logger = logging.getLogger(__name__)

# 各プロバイダの SDK 判定用モジュール名・APIキー属性名・既定モデル.
_SDK_MODULE = {
    "anthropic": "anthropic",
    "openai": "openai",
    "gemini": "google.genai",
    "ollama": "openai",  # Ollama は OpenAI 互換 API. openai SDK で base_url を向ける.
}
_API_KEY_ATTR = {
    "anthropic": "anthropic_api_key",
    "openai": "openai_api_key",
    "gemini": "gemini_api_key",
}
_DEFAULT_MODEL = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.5-flash-lite",  # 最安ティア（コスト重視）
    "ollama": "qwen2.5",                # 別PCに pull 済みのモデルを LLM_MODEL で上書き可
}


def build_analyzer(settings: Settings) -> Analyzer:
    choice = (settings.analyzer or "stub").lower()

    if choice == "stub":
        return StubAnalyzer()

    if choice in _SDK_MODULE:
        base_url: str | None = None
        if choice == "ollama":
            # Ollama は OpenAI 互換サーバ. 認証不要だが base_url（別PCのホスト）が必須.
            if not settings.ollama_base_url:
                logger.warning(
                    "analyzer=ollama だが OLLAMA_BASE_URL 未設定のため StubAnalyzer にフォールバック"
                )
                return StubAnalyzer()
            base_url = settings.ollama_base_url.rstrip("/") + "/v1"
            api_key = "ollama"  # ダミー（Ollama は認証不要）
        else:
            api_key = getattr(settings, _API_KEY_ATTR[choice], "")
            if not api_key:
                logger.warning(
                    "analyzer=%s だが API キー未設定のため StubAnalyzer にフォールバック",
                    choice,
                )
                return StubAnalyzer()
        if importlib.util.find_spec(_SDK_MODULE[choice]) is None:
            logger.warning(
                "analyzer=%s だが SDK 未導入のため StubAnalyzer にフォールバック",
                choice,
            )
            return StubAnalyzer()
        # llm_model 未指定ならプロバイダ別の既定を使う（誤プロバイダのモデル名混入を防ぐ）.
        model = settings.llm_model or _DEFAULT_MODEL[choice]
        return LLMAnalyzer(
            provider=choice,
            api_key=api_key,
            model=model,
            timeout_seconds=settings.llm_timeout_seconds,
            max_body_chars=settings.llm_max_body_chars,
            base_url=base_url,
        )

    logger.warning("未知の analyzer=%s のため StubAnalyzer にフォールバック", choice)
    return StubAnalyzer()
