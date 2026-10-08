import asyncio
import json
import unittest
import httpx

from did_ml import Candidate, PlanningContext, ResearchPlanner
from did_ml.mai_provider import MAIProvider
from did_ml.provider import ProviderError, SYSTEM_PROMPT, build_prompt
from did_ml.settings import LLMSettings

GOAL = {"action": "explore", "target": {"x": 1, "y": 0}, "reason": "test", "hypothesis_id": None}


def envelope(content=None, finish="stop"):
    return {"choices": [{"finish_reason": finish, "message": {
        "content": json.dumps(GOAL) if content is None else content,
        "reasoning_content": "must not be used as the final answer"}}]}


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_and_final_content(self):
        def handle(request):
            self.assertEqual(str(request.url), "https://api-ai.mai.ru/v1/chat/completions")
            self.assertEqual(request.headers["authorization"], "Bearer test-only-token")
            data = json.loads(request.content)
            self.assertEqual(data["model"], "deepseek-v4.1-flash")
            self.assertEqual(data["messages"][0], {"role": "system", "content": SYSTEM_PROMPT})
            self.assertEqual(json.loads(data["messages"][1]["content"]), {"observation": {"signal": .2}})
            self.assertEqual(data["thinking"], {"type": "disabled"})
            self.assertEqual(data["response_format"], {"type": "json_object"})
            self.assertFalse(data["stream"])
            return httpx.Response(200, json=envelope())
        async with MAIProvider(LLMSettings("test-only-token"), transport=httpx.MockTransport(handle)) as provider:
            output = await provider.complete(build_prompt({"observation": {"signal": .2}}))
        self.assertEqual(json.loads(output), GOAL)

    async def test_compatibility_options(self):
        def handle(request):
            data = json.loads(request.content)
            self.assertNotIn("thinking", data)
            self.assertNotIn("response_format", data)
            self.assertEqual(request.url.path, "/chat/completions")
            return httpx.Response(200, json=envelope())
        settings = LLMSettings("test-only-token", endpoint="https://api-ai.mai.ru/chat/completions",
                               thinking="omit", json_mode=False)
        async with MAIProvider(settings, transport=httpx.MockTransport(handle)) as provider:
            await provider.complete("Return JSON")

    async def test_status_errors_do_not_leak_response(self):
        for status, retryable in ((401, False), (403, False), (404, False), (429, False),
                                  (400, False), (500, True), (503, True), (302, False)):
            def handle(request):
                return httpx.Response(status, text="secret-token private error", headers={"location": "https://example.com"})
            async with MAIProvider(LLMSettings("test-only-token"), transport=httpx.MockTransport(handle)) as provider:
                with self.subTest(status=status), self.assertRaises(ProviderError) as caught:
                    await provider.complete("JSON")
                self.assertEqual(caught.exception.retryable, retryable)
                self.assertEqual(caught.exception.status_code, status)
                self.assertNotIn("secret-token", str(caught.exception))

    async def test_timeout_and_transport_sanitized(self):
        for error in (httpx.ReadTimeout("secret"), httpx.ConnectError("secret")):
            def handle(request):
                raise error
            async with MAIProvider(LLMSettings("test-only-token"), transport=httpx.MockTransport(handle)) as provider:
                with self.assertRaises(ProviderError) as caught:
                    await provider.complete("JSON")
                self.assertTrue(caught.exception.retryable)
                self.assertNotIn("secret", str(caught.exception))

    async def test_total_deadline_and_cancellation(self):
        started = asyncio.Event()
        async def handle(request):
            started.set()
            await asyncio.sleep(10)
            return httpx.Response(200, json=envelope())
        async with MAIProvider(LLMSettings("test-only-token", timeout=.01), transport=httpx.MockTransport(handle)) as provider:
            with self.assertRaises(ProviderError) as caught:
                await provider.complete("JSON")
            self.assertEqual(caught.exception.code, "timeout")
        started.clear()
        async with MAIProvider(LLMSettings("test-only-token"), transport=httpx.MockTransport(handle)) as provider:
            task = asyncio.create_task(provider.complete("JSON"))
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

    async def test_invalid_response_shapes(self):
        responses = [b'not-json', b'[]', b'{"choices":[]}',
                     json.dumps(envelope(finish="length")).encode(),
                     json.dumps(envelope(content="")).encode(),
                     json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": None}}]}).encode(),
                     b'x' * 256001]
        for raw in responses:
            async with MAIProvider(LLMSettings("test-only-token"), transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, content=raw))) as provider:
                with self.subTest(length=len(raw)), self.assertRaises(ProviderError):
                    await provider.complete("JSON")

    async def test_auth_failure_falls_back_without_second_request(self):
        requests = []
        def handle(request):
            requests.append(request)
            return httpx.Response(401, text="secret")
        async with MAIProvider(LLMSettings("test-only-token"), transport=httpx.MockTransport(handle)) as provider:
            planner = ResearchPlanner(provider=provider)
            planner.set_context(PlanningContext(1, 0, 0, 0, (Candidate("a", 1, 0, 2, 2),)))
            obs = {"sim_time": 1, "pose": {"x": 0, "y": 0}, "battery": 60, "signal": .2,
                   "pose_time": 1, "battery_time": 1, "signal_time": 1, "scan_time": 1, "obstacle_ahead": False}
            output = await planner.propose(obs)
            self.assertEqual(output["action"], "explore")
            self.assertEqual(planner.history[-1]["source"], "offline")
            self.assertEqual(planner.history[0]["code"], "authentication")
            self.assertEqual(len(requests), 1)


class SettingsTests(unittest.TestCase):
    def test_environment_and_redaction(self):
        settings = LLMSettings.from_env({"DID_LLM_API_KEY": "test-only-token", "DID_LLM_TIMEOUT": "7"})
        self.assertEqual(settings.timeout, 7)
        self.assertNotIn("test-only-token", repr(settings))
        with self.assertRaises(ValueError):
            LLMSettings.from_env({})
        with self.assertRaises(ValueError) as caught:
            LLMSettings.from_env({"DID_LLM_API_KEY": "test-only-token", "DID_LLM_TIMEOUT": "private-secret"})
        self.assertNotIn("private-secret", str(caught.exception))

    def test_insecure_endpoint_and_invalid_options(self):
        for endpoint in ("http://api-ai.mai.ru/v1/chat/completions", "https://user:secret@example.com/",
                         "https://api-ai.mai.ru/?key=secret", "https://api-ai.mai.ru/#secret"):
            with self.assertRaises(ValueError):
                LLMSettings("test-only-token", endpoint=endpoint)
        for kwargs in ({"timeout": float("nan")}, {"max_tokens": 0}, {"thinking": "typo"}):
            with self.assertRaises(ValueError):
                LLMSettings("test-only-token", **kwargs)


if __name__ == "__main__":
    unittest.main()
