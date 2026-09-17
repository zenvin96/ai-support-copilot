from app.services.agent.graph import _is_readonly_sql, _parse_json, redact
from app.services.llm.openai_provider import DeepSeekProvider, OpenAIProvider
from app.services.rag.ingest import split_text


def test_parse_json_extracts_object_from_noise():
    assert _parse_json('sure: {"intent": "chit_chat", "order_id": null}') == {"intent": "chit_chat", "order_id": None}
    assert _parse_json("no json") == {}


def test_readonly_sql_guard():
    assert _is_readonly_sql("SELECT * FROM orders WHERE id = 123")
    assert not _is_readonly_sql("DELETE FROM orders")
    assert not _is_readonly_sql("SELECT 1; DROP TABLE orders")


def test_redact_phone_and_email():
    out = redact("客户手机 13800001234，邮箱 zhang.san@example.com")
    assert "13800001234" not in out and "138****1234" in out
    assert "zhang.san@" not in out and "z***@example.com" in out


def test_cost_calc():
    assert OpenAIProvider().cost("gpt-4o-mini", 1_000_000, 0) == 0.15
    assert DeepSeekProvider().cost("deepseek-chat", 0, 1_000_000) == 1.10
    assert DeepSeekProvider().cost("deepseek-flash", 1_000_000, 1_000_000) == 1.50
    assert OpenAIProvider().cost("unknown", 100, 100) == 0.0


def test_split_text_respects_size():
    text = "\n\n".join(f"第{i}段。" + "内容" * 100 for i in range(5))
    chunks = split_text(text, chunk_size=300, overlap=30)
    assert len(chunks) >= 5
    assert all(len(c) <= 300 for c in chunks)


def test_email_message_build():
    from app.services.notify.email import build_message
    msg = build_message("新工单 #1", "正文", sender="bot@example.com", to=["a@x.com", "b@x.com"])
    assert msg["Subject"] == "新工单 #1"
    assert msg["To"] == "a@x.com, b@x.com"
    assert msg.get_content().strip() == "正文"
