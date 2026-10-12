import json
from app.interception.deepseek import parse_deepseek_web


def test_response_fragment_keeps_snapshot_prefix():
    """Snapshot gives RESPONSE content 'Hello'; APPEND adds '!'.
    Bug (pre-fix): leading 'Hello' was dropped, output began with '!'.
    """
    body = "\n".join([
        'data: {"v":{"response":{"fragments":[{"id":1,"type":"RESPONSE","content":"Hello"}]}}}',
        'data: {"p":"response/fragments/-1/content","o":"APPEND","v":"!"}',
        'data: {"v":" How"}',
        'data: {"v":" can"}',
        'data: {"v":" I"}',
        'data: {"v":" help"}',
        'data: {"v":"?"}',
    ])
    assert parse_deepseek_web(body) == "Hello! How can I help?"


def test_think_then_response_isolated():
    """THINK fragment appended first; RESPONSE fragment added later.
    The RESPONSE must not inherit THINK content."""
    body = "\n".join([
        'data: {"v":{"response":{"fragments":[{"id":2,"type":"THINK","content":"We"}]}}}',
        'data: {"p":"response/fragments/-1/content","o":"APPEND","v":" need"}',
        'data: {"p":"response/fragments/-1/content","o":"APPEND","v":" answer"}',
        'data: {"p":"response/fragments","o":"APPEND","v":[{"id":3,"type":"RESPONSE","content":"zz"}]}',
        'data: {"p":"response/fragments/-1/content","o":"APPEND","v":"-m"}',
        'data: {"v":"arker"}',
        'data: {"v":"-"}',
        'data: {"v":"7"}',
        'data: {"v":" acknowledged"}',
        'data: {"v":"."}',
    ])
    assert parse_deepseek_web(body) == "zz-marker-7 acknowledged."
