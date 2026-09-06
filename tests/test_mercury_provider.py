"""Mercury 2 is a provider, not an integration.

Inception Labs' diffusion LLM speaks the OpenAI protocol, so adding it is a row
in the provider table. These tests pin the three things a row can get wrong and
that no unit test would otherwise notice until someone deployed with a key:
the endpoint, the model id, and the environment variable the key is read from.

Deliberately no network. A test that needs a live key is a test that gets
skipped in CI and rots.
"""

import os

import pytest

from misata.llm_parser import LLMSchemaGenerator


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setenv("INCEPTION_API_KEY", "sk-test-not-a-real-key")


class TestTheProviderRow:
    def test_mercury_is_registered(self):
        assert "mercury" in LLMSchemaGenerator.PROVIDERS

    def test_it_points_at_inceptions_endpoint(self):
        row = LLMSchemaGenerator.PROVIDERS["mercury"]
        assert row["base_url"] == "https://api.inceptionlabs.ai/v1"
        assert row["default_model"] == "mercury-2"
        assert row["env_key"] == "INCEPTION_API_KEY"

    def test_it_speaks_the_openai_protocol(self):
        """The reason this is ten lines rather than a client."""
        assert LLMSchemaGenerator.PROVIDERS["mercury"]["protocol"] == "openai"


class TestItConstructs:
    """Constructing the client needs the `openai` package, which is in the
    [llm] extra rather than the base install. The publish job installs
    [dev] only, so these skip there while the provider-row tests above,
    which touch no client, still run everywhere."""

    @pytest.fixture(autouse=True)
    def _needs_openai(self):
        pytest.importorskip("openai")

    def test_the_client_is_built_against_the_right_host(self, keyed):
        gen = LLMSchemaGenerator(provider="mercury")
        assert gen.model == "mercury-2"
        assert str(gen.client.base_url).rstrip("/") == "https://api.inceptionlabs.ai/v1"

    def test_the_key_comes_from_the_documented_variable(self, monkeypatch):
        monkeypatch.delenv("INCEPTION_API_KEY", raising=False)
        monkeypatch.setenv("INCEPTION_API_KEY", "sk-from-env")
        assert LLMSchemaGenerator(provider="mercury").api_key == "sk-from-env"

    def test_an_explicit_model_overrides_the_default(self, keyed):
        """Inception ships previews alongside the stable id, so pinning one
        must not require a code change."""
        gen = LLMSchemaGenerator(provider="mercury", model="mercury-2.5-preview")
        assert gen.model == "mercury-2.5-preview"

    def test_switching_between_groq_and_mercury_changes_the_endpoint(self, keyed, monkeypatch):
        """The whole point: one setting moves the schema designer between them
        and nothing else in the engine notices."""
        monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
        mercury = LLMSchemaGenerator(provider="mercury")
        groq = LLMSchemaGenerator(provider="groq")
        assert "inceptionlabs" in str(mercury.client.base_url)
        assert "inceptionlabs" not in str(groq.client.base_url)
        assert mercury.model != groq.model


def test_mercury_gets_json_mode(keyed):
    """Gemini and Ollama are excluded from response_format because their
    compatibility layers reject it. Mercury supports it, so it must not be
    swept into that exclusion by someone widening the list later."""
    import inspect

    source = inspect.getsource(LLMSchemaGenerator)
    excluded = source.split('if self.provider not in (')[1].split(')')[0]
    assert "mercury" not in excluded, (
        "mercury was added to the response_format exclusion list; it supports "
        "structured output and asking for plain text loses the JSON guarantee"
    )
