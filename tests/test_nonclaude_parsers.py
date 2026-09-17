import json

from app.interception.chatgpt import parse_chatgpt_web
from app.interception.deepseek import DeepSeekStreamParser, parse_deepseek_web
from app.interception.gemini import parse_gemini_web


def test_deepseek_uses_response_fragment_not_title_metadata():
    body = "\n".join([
        'data: {"v":{"response":{"fragments":[{"type":"RESPONSE","content":"Hello! How can I help you today?"}]}}}',
        'data: {"response":"Greeting"}',
    ])
    assert parse_deepseek_web(body) == "Hello! How can I help you today?"


def test_deepseek_handles_nested_response_fragment_text():
    body = 'data: {"v":{"response":{"fragments":[{"type":"RESPONSE","content":{"text":"Hello from DeepSeek"}}]}}}'
    assert parse_deepseek_web(body) == "Hello from DeepSeek"


def test_deepseek_does_not_duplicate_overlapping_fragments():
    body = "\n".join([
        'data: {"p":"response/fragments/-1/content","o":"APPEND","v":"Doing"}',
        'data: {"p":"response/fragments/-1/content","o":"APPEND","v":"ing well"}',
    ])
    assert parse_deepseek_web(body) == "Doing well"


def test_deepseek_carries_patch_path_and_operation_across_token_frames():
    body = "\n".join([
        'data: {"p":"response/fragments/-1/content","o":"APPEND","v":"I"}',
        'data: {"v":"\'m"}',
        'data: {"v":" doing"}',
        'data: {"v":" well"}',
    ])
    assert parse_deepseek_web(body) == "I'm doing well"


def test_deepseek_supports_set_patch():
    body = 'data: {"p":"response/fragments/-1/content","o":"SET","v":"Final answer"}'
    assert parse_deepseek_web(body) == "Final answer"


def test_deepseek_stateful_parser_does_not_replay_cumulative_snapshots():
    body1 = 'data: {"p":"response/fragments/-1/content","o":"APPEND","v":"You\'re"}'
    body2 = body1 + '\ndata: {"v":{"response":{"fragments":[{"type":"RESPONSE","content":"You\'re chatting with **DeepSek**"}]}}}'
    body3 = body2 + '\ndata: {"v":{"response":{"fragments":[{"type":"RESPONSE","content":"You\'re chatting with **DeepSek** — an AI assistant created by DeepSek"}]}}}'
    parser = DeepSeekStreamParser()
    assert parser.feed(body1) == "You're"
    assert parser.feed(body2) == "You're chatting with **DeepSek**"
    assert parser.feed(body3) == "You're chatting with **DeepSek** — an AI assistant created by DeepSek"
    assert parser.feed(body3) == "You're chatting with **DeepSek** — an AI assistant created by DeepSek"


def test_deepseek_prefers_web_fragments_over_openai_choice_view():
    body = "\n".join([
        'data: {"v":{"response":{"fragments":[{"type":"RESPONSE","content":"Hello!"}]}}}',
        'data: {"choices":[{"delta":{"content":"Hello!"}}]}',
    ])
    assert parse_deepseek_web(body) == "Hello!"


def test_chatgpt_extracts_assistant_message_only():
    body = "\n".join([
        'data: {"message":{"author":{"role":"user"},"content":{"parts":["hi"]}}}',
        'data: {"message":{"author":{"role":"assistant"},"content":{"parts":["Hello! How can I help you today?"]}}}',
        "data: [DONE]",
    ])
    assert parse_chatgpt_web(body) == "Hello! How can I help you today?"


def test_chatgpt_extracts_current_delta_patch():
    body = "\n".join([
        'data: {"p":"/message/content/parts/0","o":"append","v":"Hello!"}',
        'data: {"p":"/message/content/parts/0","o":"append","v":" How can I help you today?"}',
        "data: [DONE]",
    ])
    assert parse_chatgpt_web(body) == "Hello! How can I help you today?"


def test_chatgpt_handles_replace_patch_list():
    body = 'data: {"p":"/message/content/parts/0","o":"replace","v":["Final answer"]}'
    assert parse_chatgpt_web(body) == "Final answer"


def test_gemini_extracts_streamgenerate_candidate():
    inner = json.dumps([None, None, None, None, [[None, ["Hello! How can I help you today?"]]]])
    body = json.dumps(["wrb.fr", None, inner, None])
    assert parse_gemini_web(body) == "Hello! How can I help you today?"


def test_gemini_accepts_xssi_prefixed_frame():
    inner = json.dumps([None, None, None, None, [[None, ["Hello from Gemini"]]]])
    body = ")]}'\n" + json.dumps(["wrb.fr", None, inner, None])
    assert parse_gemini_web(body) == "Hello from Gemini"
