from native_multimodal import QwenMultimodalEmbeddings


def test_multimodal_response_parser(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"output": {"embeddings": [{"embedding": [0.1, 0.2]}]}}

    monkeypatch.setattr("native_multimodal.httpx.post", lambda *args, **kwargs: Response())
    client = QwenMultimodalEmbeddings()
    client.api_key = "test"
    assert client.embed_text("机柜布局") == [0.1, 0.2]
