from app.interception.claude_transport import ClaudeSSEParser


def frame(payload: dict) -> bytes:
    import json

    return ("event: message\ndata: " + json.dumps(payload) + "\n\n").encode()


def test_live_claude_content_block_delta():
    parser = ClaudeSSEParser()
    events = parser.feed(frame({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "hello"}}))
    assert [(event.delta, event.finish_reason, event.done) for event in events] == [("hello", None, False)]


def test_live_claude_message_delta_and_message_stop():
    parser = ClaudeSSEParser()
    payload = b"".join(
        [
            frame({"type": "message_delta", "delta": {"stop_reason": "end_turn"}}),
            frame({"type": "message_stop"}),
        ]
    )
    events = parser.feed(payload)
    assert events[0].finish_reason == "end_turn"
    assert events[0].done is False
    assert events[1].done is True
    assert events[1].finish_reason == "stop"
