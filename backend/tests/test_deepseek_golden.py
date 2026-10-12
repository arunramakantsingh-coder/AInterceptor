import pathlib
from app.interception.deepseek import parse_deepseek_web

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "deepseek_golden_synthetic.raw"


def test_deepseek_golden_synthetic_round_trip():
    body = FIXTURE.read_text(encoding="utf-8")
    result = parse_deepseek_web(body)
    assert result == "hi how are you", f"got {result!r}"


def test_deepseek_no_word_loss_across_fragments():
    lines = [
        'data: {"p":"response/fragments/-1/content","o":"APPEND","v":"That"}',
        'data: {"p":"response/fragments/-1/content","o":"APPEND","v":"\u0027s a "}',
        'data: {"p":"response/fragments/-1/content","o":"APPEND","v":"good thing "}',
        'data: {"p":"response/fragments/-1/content","o":"APPEND","v":"to want."}',
    ]
    body = "\n".join(lines)
    result = parse_deepseek_web(body)
    assert result == "That's a good thing to want.", f"got {result!r}"
