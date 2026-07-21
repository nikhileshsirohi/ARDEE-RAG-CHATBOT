"""Tests for greeting / small-talk detection."""

import pytest

from app.services.greeting import is_greeting


@pytest.mark.parametrize(
    "message",
    [
        "hi",
        "Hi!",
        "hello",
        "Hello there",
        "hey",
        "hey there",
        "good morning",
        "Good Morning!",
        "good afternoon",
        "good evening",
        "good night",
        "greetings",
        "howdy",
        "yo",
        "namaste",
        "hola",
        "thanks",
        "thank you",
        "thank you so much",
        "thanks a lot",
        "how are you",
        "how are you doing today",
        "what's up",
        "bye",
        "goodbye",
        "hi team 👋",
        "hello everyone",
    ],
)
def test_detects_greetings(message: str) -> None:
    """Pure greetings and pleasantries should be detected."""
    assert is_greeting(message) is True


@pytest.mark.parametrize(
    "message",
    [
        "What is multi-head attention?",
        "Explain scaled dot-product attention",
        "hi, what is attention?",  # greeting + real question → not a greeting
        "hello, how many heads are used in the transformer?",
        "good morning, summarize the paper",
        "define positional encoding",
        "tell me about the refund policy",
        "",
        "   ",
        "capital of France",
    ],
)
def test_rejects_non_greetings(message: str) -> None:
    """Substantive questions (even with a greeting prefix) are not greetings."""
    assert is_greeting(message) is False
