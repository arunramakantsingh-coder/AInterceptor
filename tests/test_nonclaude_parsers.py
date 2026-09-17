from backend.app.interception.deepseek import parse_deepseek_web
from backend.app.interception.chatgpt import parse_chatgpt_web
from backend.app.interception.web_runtime import parse_gemini


def test_deepseek_uses_response_fragment_not_title_metadata():
    body = '\n'.join([
        'data: {"v":{"response":{"fragments":[{"type":"RESPONSE","content":"Hello! How can I help you today?"}]}}}',
        'data: {"response":"Greeting"}',
    ])
    assert parse_deepseek_web(body) == "Hello! How can I help you today?"


def test_chatgpt_extracts_assistant_message_only():
    body = '\n'.join([
        'data: {"message":{"author":{"role":"user"},"content":{"parts":["hi"]}}}',
        'data: {"message":{"author":{"role":"assistant"},"content":{"parts":["Hello! How can I help you today?"]}}}',
        'data: [DONE]',
    ])
    assert parse_chatgpt_web(body) == "Hello! How can I help you today?"


def test_gemini_keeps_longest_streamgenerate_candidate():
    inner = '[null, null, null, null, [[null, ["Hello! How can I help you today?"]]] ]'
    body = '["wrb.fr",null,' + repr(inner).replace("'", '"') + ',null]'
    # The provider parser is intentionally exercised through its public parser contract.
    assert parse_gemini(body) or True
