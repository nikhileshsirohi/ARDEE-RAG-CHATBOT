"""Lightweight greeting / small-talk detection.

Why rule-based instead of a third-party library?
    There is no well-maintained Python library dedicated to greeting detection,
    and doing it with the LLM would add a classification call (latency + cost) to
    every message. A compact deterministic classifier is fast, free, and — most
    importantly for this RAG app — cannot hallucinate: it only decides *whether*
    a message is a social pleasantry, never what to answer.

A message is a greeting only when, after stripping punctuation/emoji, it is a
known greeting phrase or is composed entirely of greeting + filler tokens and is
short. This keeps mixed messages like "hi, what is attention?" out of the
greeting path so they still go through document retrieval.
"""

import re

# Multi-word pleasantries matched as a whole (fast path).
GREETING_PHRASES: frozenset[str] = frozenset(
    {
        "how are you",
        "how are you doing",
        "how are you doing today",
        "how are u",
        "how r u",
        "how is it going",
        "hows it going",
        "how goes it",
        "whats up",
        "what is up",
        "wassup",
        "wazzup",
        "nice to meet you",
        "nice to meet you too",
        "good to see you",
        "long time no see",
        "thank you",
        "thank you so much",
        "thank you very much",
        "thanks a lot",
        "thanks a ton",
        "many thanks",
        "good morning",
        "good afternoon",
        "good evening",
        "good night",
        "good day",
        "have a good day",
        "have a nice day",
        "see you",
        "see you later",
        "see ya",
        "take care",
        "talk to you later",
    }
)

# Single-token greetings.
GREETING_TOKENS: frozenset[str] = frozenset(
    {
        "hi",
        "hii",
        "hiii",
        "hiya",
        "hey",
        "heya",
        "hello",
        "helloo",
        "hellooo",
        "yo",
        "howdy",
        "hola",
        "namaste",
        "greetings",
        "sup",
        "gm",
        "morning",
        "afternoon",
        "evening",
        "goodmorning",
        "goodevening",
        "thanks",
        "thankyou",
        "thx",
        "ty",
        "cheers",
        "bye",
        "goodbye",
        "ciao",
        "adios",
        "welcome",
        "good",
        "day",
        "night",
    }
)

# Neutral words allowed to accompany a greeting without disqualifying it.
FILLER_TOKENS: frozenset[str] = frozenset(
    {
        "there",
        "everyone",
        "all",
        "team",
        "bot",
        "chatbot",
        "assistant",
        "sir",
        "maam",
        "madam",
        "guys",
        "folks",
        "mate",
        "buddy",
        "friend",
        "dear",
        "a",
        "an",
        "the",
        "lot",
        "ton",
        "so",
        "much",
        "very",
        "again",
        "please",
        "and",
        "to",
        "you",
        "u",
        "today",
        "then",
    }
)

# Messages longer than this are treated as substantive, never greetings.
MAX_GREETING_WORDS = 6

_NON_WORD = re.compile(r"[^a-z']+")


def _normalize(text: str) -> str:
    """Lower-case and collapse whitespace."""
    return " ".join(text.lower().split())


def is_greeting(text: str) -> bool:
    """Return True when ``text`` is a greeting or social pleasantry.

    Examples:
        >>> is_greeting("Hi")            # True
        >>> is_greeting("good morning!") # True
        >>> is_greeting("thanks a lot")  # True
        >>> is_greeting("What is attention?")        # False
        >>> is_greeting("hi, what is attention?")    # False (has a real question)
    """
    normalized = _normalize(text)
    if not normalized:
        return False

    stripped = normalized.strip(" .!?,;:").replace("'", "")
    if stripped in {phrase.replace("'", "") for phrase in GREETING_PHRASES}:
        return True

    tokens = [token for token in _NON_WORD.split(normalized) if token]
    if not tokens or len(tokens) > MAX_GREETING_WORDS:
        return False

    # A greeting must contain at least one real greeting token, with every other
    # token being a greeting or neutral filler word.
    has_greeting_token = any(token in GREETING_TOKENS for token in tokens)
    only_greeting_or_filler = all(
        token in GREETING_TOKENS or token in FILLER_TOKENS for token in tokens
    )
    return has_greeting_token and only_greeting_or_filler
