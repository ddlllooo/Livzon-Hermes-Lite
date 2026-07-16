from services.dazah_agent_service import (
    DazahAIAgent,
    DazahChatRequest,
    _user_message_with_attachments,
)


def test_dazah_proxy_keeps_multimodal_message_parts() -> None:
    agent = object.__new__(DazahAIAgent)
    assert agent._model_supports_vision() is True


def test_document_attachment_is_added_as_user_content() -> None:
    payload = DazahChatRequest(
        session_id="session-1",
        message="请总结",
        attachments=[
            {
                "filename": "记录.txt",
                "content_type": "text/plain",
                "size": 12,
                "kind": "document",
                "text": "批次状态正常",
            }
        ],
    )

    content = _user_message_with_attachments(payload)

    assert isinstance(content, str)
    assert "记录.txt" in content
    assert "批次状态正常" in content


def test_image_attachment_builds_multimodal_user_content() -> None:
    payload = DazahChatRequest(
        session_id="session-1",
        message="识别图片",
        attachments=[
            {
                "filename": "现场.png",
                "content_type": "image/png",
                "size": 3,
                "kind": "image",
                "data_base64": "YWJj",
            }
        ],
    )

    content = _user_message_with_attachments(payload)

    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert content[1]["image_url"]["url"] == "data:image/png;base64,YWJj"
