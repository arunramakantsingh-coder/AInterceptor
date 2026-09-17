from app.providers.catalog import all_provider_profiles, model_profile, provider_profile


def test_catalog_contains_active_web_providers():
    profiles = {profile.provider: profile for profile in all_provider_profiles()}
    assert {"chatgpt", "claude", "gemini", "deepseek"}.issubset(profiles)
    for name in ("chatgpt", "gemini", "deepseek"):
        profile = profiles[name]
        assert profile.status == "active"
        assert "web_cdp" in profile.transports
        assert profile.web["home_url"]
        assert profile.web["response_markers"]
        assert profile.web["request_markers"]


def test_catalog_contains_future_router_providers():
    profiles = {profile.provider: profile for profile in all_provider_profiles()}
    assert {"grok", "mistral", "qwen", "perplexity"}.issubset(profiles)
    assert profiles["grok"].status == "catalog_only"
    assert profiles["mistral"].status == "catalog_only"
    assert profiles["qwen"].status == "catalog_only"
    assert profiles["perplexity"].status == "catalog_only"


def test_model_profile_exposes_capability_metadata():
    model = model_profile("chatgpt", "gpt-5.6-sol")
    assert model.role == "frontier"
    assert "complex_reasoning" in model.strengths
    assert model.context_tokens == 1050000
    assert model.max_output_tokens == 128000


def test_provider_profile_is_config_backed():
    profile = provider_profile("deepseek")
    assert profile.web["default_model"] == "deepseek-flash"
    assert "coding" in profile.capabilities
    assert model_profile("perplexity", "sonar-pro").strengths
