import unittest

from ios_app_store_submit.resubmit.command_builder import build_commands


class ResubmitCommandBuilderTests(unittest.TestCase):
    def test_commands_use_exact_ids_and_include_fallback(self):
        result = build_commands(app_id="app-1", version="2.0.0", build_id="build-7", submission_id="sub-9")
        self.assertTrue(result.ready)
        self.assertIn("--app app-1", result.commands[0])
        self.assertIn("--version 2.0.0", result.commands[0])
        self.assertIn("--build build-7", result.commands[0])
        self.assertIn("--id sub-9", result.commands[1])
        self.assertIn("asc review submit", result.preview)
        self.assertIn("asc review submissions-submit", result.preview)

    def test_missing_any_required_id_generates_no_command(self):
        result = build_commands(app_id="app-1", version="2.0.0", build_id=None, submission_id="sub-9")
        self.assertFalse(result.ready)
        self.assertEqual(result.commands, ())
        self.assertIn("missing_build_id", result.blockers)

    def test_generated_commands_contain_no_secret_material(self):
        result = build_commands(app_id="app-1", version="2.0.0", build_id="build-7", submission_id="sub-9")
        rendered = result.preview.lower()
        for word in ("password", "api_key", "secret", "token", ".p8"):
            self.assertNotIn(word, rendered)


if __name__ == "__main__":
    unittest.main()
