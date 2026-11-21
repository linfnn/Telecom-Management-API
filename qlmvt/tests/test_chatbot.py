import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from qlmvt.views.chatbot import _explicit_export_request, api_chatbot_ask


class FakeProviderResponse:
    def __init__(self, data=None):
        self.data = data or {
            "choices": [{"message": {"content": "Xin chào!"}}]
        }

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps(self.data).encode("utf-8")


class ChatbotApiTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def request(self, payload, is_staff=False):
        request = self.factory.post(
            "/qlmvt/api_chatbot_ask/",
            payload,
            format="json",
        )
        force_authenticate(
            request,
            user=SimpleNamespace(is_authenticated=True, is_staff=is_staff),
        )
        return api_chatbot_ask(request)

    def test_export_requires_an_explicit_action_request(self):
        self.assertTrue(_explicit_export_request("Export a JSON backup"))
        self.assertTrue(_explicit_export_request("Xuất file backup JSON"))
        self.assertFalse(_explicit_export_request("How do I export a JSON backup?"))
        self.assertFalse(_explicit_export_request("Backup là gì?"))

    @override_settings(CHATBOT_API_KEY="")
    def test_requires_provider_configuration(self):
        response = self.request({"message": "Xin chào"})

        self.assertEqual(response.status_code, 503)
        self.assertIn("CHATBOT_API_KEY", json.loads(response.content)["error"])

    def test_rejects_invalid_history(self):
        response = self.request(
            {"message": "Xin chào", "history": [{"role": "system", "content": "no"}]}
        )

        self.assertEqual(response.status_code, 400)

    @override_settings(
        CHATBOT_API_KEY="test-key",
        CHATBOT_BASE_URL="https://ai.example/v1",
        CHATBOT_MODEL="test-model",
        CHATBOT_TIMEOUT_SECONDS=5,
    )
    @patch("qlmvt.views.chatbot.urlopen")
    def test_sends_conversation_to_openai_compatible_provider(self, mock_urlopen):
        mock_urlopen.return_value = FakeProviderResponse()

        response = self.request(
            {
                "message": "Giúp tôi",
                "history": [{"role": "model", "content": "Xin chào"}],
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["message"], "Xin chào!")
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://ai.example/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        body = json.loads(request.data)
        self.assertEqual(body["model"], "test-model")
        self.assertEqual(body["messages"][1]["role"], "assistant")
        self.assertEqual(body["messages"][-1]["content"], "Giúp tôi")
        self.assertIn("MỌI câu trả lời luôn phải bằng tiếng Việt", body["messages"][0]["content"])

    @override_settings(
        CHATBOT_API_KEY="test-key",
        CHATBOT_BASE_URL="https://ai.example/v1",
        CHATBOT_MODEL="test-model",
        CHATBOT_TIMEOUT_SECONDS=5,
    )
    @patch("qlmvt.views.chatbot.backup_to_json", return_value='{"models":{}}')
    @patch("qlmvt.views.chatbot.urlopen")
    def test_admin_export_returns_backup_without_sending_it_to_provider(
        self, mock_urlopen, mock_backup
    ):
        mock_urlopen.return_value = FakeProviderResponse(
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "export-1",
                                    "type": "function",
                                    "function": {
                                        "name": "export_backup_json",
                                        "arguments": "{}",
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        )

        response = self.request({"message": "Export a JSON backup"}, is_staff=True)

        body = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["type"], "export")
        self.assertEqual(body["file_content"], '{"models":{}}')
        self.assertEqual(body["file_name"], "qlmvt_backup.json")
        self.assertEqual(mock_urlopen.call_count, 1)
        self.assertEqual(json.loads(mock_urlopen.call_args.args[0].data)["messages"][-1]["content"], "Export a JSON backup")
        mock_backup.assert_called_once_with()

    @override_settings(
        CHATBOT_API_KEY="test-key",
        CHATBOT_BASE_URL="https://ai.example/v1",
        CHATBOT_MODEL="test-model",
        CHATBOT_TIMEOUT_SECONDS=5,
    )
    @patch("qlmvt.views.chatbot.backup_to_json")
    @patch("qlmvt.views.chatbot.urlopen")
    def test_employee_cannot_export_even_if_provider_requests_it(
        self, mock_urlopen, mock_backup
    ):
        tool_call_response = FakeProviderResponse(
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "export-1",
                                    "type": "function",
                                    "function": {
                                        "name": "export_backup_json",
                                        "arguments": "{}",
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        )
        mock_urlopen.side_effect = [
            tool_call_response,
            FakeProviderResponse(
                {"choices": [{"message": {"content": "Chỉ Admin mới được xuất backup."}}]}
            ),
        ]

        response = self.request({"message": "Export a backup"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["type"], "text")
        self.assertEqual(mock_urlopen.call_count, 2)
        first_request_body = json.loads(mock_urlopen.call_args_list[0].args[0].data)
        available_tools = [
            tool["function"]["name"] for tool in first_request_body["tools"]
        ]
        self.assertNotIn("export_backup_json", available_tools)
        mock_backup.assert_not_called()
