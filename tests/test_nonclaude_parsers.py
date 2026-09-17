import json

from app.interception.chatgpt import parse_chatgpt_web
from app.interception.deepseek import parse_deepseek_web
from app.interception.web_runtime import parse_gemini


def test_deepseek_uses_response_fragment_not_title_metadata():
    body = "\n".join([
        'data: {"v":{"response":{"fragments":[{"type":"RESPONSE","content":"Hello! How can I help you today?"}]}}}',
        'data: {"response":"Greeting"}',
    ])
    assert parse_deepseek_web(body) == "Hello! How can I help you today?"


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


def test_gemini_extracts_streamgenerate_candidate():
    inner = json.dumps([None, None, None, None, [[None, ["Hello! How can I help you today?"]]]])
    body = json.dumps(["wrb.fr", None, inner, None])
    assert parse_gemini(body) == "Hello! How can I help you today?"
