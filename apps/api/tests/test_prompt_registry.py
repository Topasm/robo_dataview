from __future__ import annotations

import unittest

from packages.prompts import UnknownPromptTemplateError, get_prompt_template, list_prompt_templates


class PromptRegistryTest(unittest.TestCase):
    def test_registry_loads_episode_autolabel_prompt(self) -> None:
        prompts = list_prompt_templates()
        prompt = get_prompt_template("episode_autolabel_v1")

        self.assertEqual([item.prompt_id for item in prompts], ["episode_autolabel_v1"])
        self.assertEqual(prompt.version, "v1")
        self.assertIn("sampled frames", prompt.body)
        self.assertIn("subtasks", prompt.body)
        self.assertIn("subtask", prompt.expected_outputs)
        self.assertIn("important_frame", prompt.expected_outputs)

    def test_unknown_prompt_raises(self) -> None:
        with self.assertRaises(UnknownPromptTemplateError):
            get_prompt_template("missing_prompt")


if __name__ == "__main__":
    unittest.main()
