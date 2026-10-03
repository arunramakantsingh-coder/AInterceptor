import pytest

from app.interception.claude_transport import ClaudeSSEParser


def test_claude_sse_parser_handles_split_frames_incrementally():
    parser = ClaudeSSEParser()

    assert parser.feed(b'data: {"completion":"Hel') == []
    events = parser.feed(b'lo"}\n\ndata: {"completion":" world"}\n\n')

    assert [event.delta for event in events] == ["Hello", " world"]
    assert all(not event.done for event in events)


def test_claude_sse_parser_handles_done_and_finish_reason():
    parser = ClaudeSSEParser()

    events = parser.feed(
        b'data: {"completion":"answer","stop_reason":"stop_sequence"}\n\n'
        b'data: [DONE]\n\n'
    )

    assert events[0].delta == "answer"
    assert events[0].finish_reason == "stop_sequence"
    assert events[1].done is True
    assert events[1].finish_reason == "stop"


def test_claude_sse_parser_ignores_comments_and_invalid_json():
    parser = ClaudeSSEParser()

    events = parser.feed(
        b": heartbeat\n\n"
        b"data: not-json\n\n"
        b'data: {"delta":{"text":"ok"}}\n\n'
    )

    assert len(events) == 1
    assert events[0].delta == "ok"


def test_claude_sse_parser_preserves_utf8_split_across_transport_chunks():
    parser = ClaudeSSEParser()
    payload = 'data: {"completion":"caf\u00e9"}\n\n'.encode("utf-8")

    split_at = payload.index(b"\xc3") + 1
    assert parser.feed(payload[:split_at]) == []
    events = parser.feed(payload[split_at:])

    assert events[0].delta == "café"


def test_claude_sse_parser_flushes_terminal_frame_without_separator():
    parser = ClaudeSSEParser()

    assert parser.feed(b'data: {"completion":"tail"}') == []
    events = parser.finish()

    assert len(events) == 1
    assert events[0].delta == "tail"
