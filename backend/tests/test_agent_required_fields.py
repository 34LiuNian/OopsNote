from __future__ import annotations

import unittest

from app.agents.agent_flow import LLMAgent, PromptTemplate


class _ClientReturnsDict:
    def __init__(self, payload):
        self.payload = payload

    def structured_chat(self, system_prompt, user_prompt, thinking=None):
        return self.payload


class _ClientReturnsNonDict:
    def structured_chat(self, system_prompt, user_prompt, thinking=None):
        return "not-a-dict"


class LLMAgentRequiredFieldsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.template = PromptTemplate(
            name="test",
            system_prompt="SYS",
            user_template="USER",
        )

    def test_missing_required_fields_raises(self) -> None:
        agent = LLMAgent(
            "solver",
            _ClientReturnsDict({"answer": "42"}),
            self.template,
            required_keys=("answer", "explanation"),
        )

        with self.assertRaises(RuntimeError) as ctx:
            agent.run({})

        self.assertIn("missing required fields", str(ctx.exception))
        self.assertIn("explanation", str(ctx.exception))

    def test_non_object_output_raises(self) -> None:
        agent = LLMAgent(
            "solver",
            _ClientReturnsNonDict(),
            self.template,
            required_keys=("answer", "explanation"),
        )

        with self.assertRaises(RuntimeError) as ctx:
            agent.run({})

        self.assertIn("non-object output", str(ctx.exception))

    def test_required_fields_present_passes(self) -> None:
        payload = {"answer": "42", "explanation": "because"}
        agent = LLMAgent(
            "solver",
            _ClientReturnsDict(payload),
            self.template,
            required_keys=("answer", "explanation"),
        )

        result = agent.run({})
        self.assertEqual(result.output, payload)


if __name__ == "__main__":
    unittest.main()
