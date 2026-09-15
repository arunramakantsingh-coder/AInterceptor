import pytest
from app.providers.fake import FakeProvider


@pytest.mark.asyncio
async def test_fake_streams_chunks():
    p = FakeProvider(reply="hi there")
    await p.authenticate()
    chunks = [c async for c in p.send_prompt([{"role":"user","content":"x"}])]
    assert "".join(c.delta for c in chunks).strip() == "hi there"
    assert chunks[-1].finish_reason == "stop"


@pytest.mark.asyncio
async def test_fake_requires_auth():
    p = FakeProvider()
    with pytest.raises(RuntimeError):
        async for _ in p.send_prompt([]):
            pass
