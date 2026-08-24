import json
import tempfile
import unittest
from pathlib import Path

from ios_app_store_submit.recovery.models import RejectionSource
from ios_app_store_submit.recovery.parser import parse_rejection, parse_rejection_file, redact_secrets


class GuidelineExtractionTests(unittest.TestCase):
    def test_explicit_guideline_is_parsed(self):
        rejection = parse_rejection("Guideline 2.1 - Performance: something is wrong.", rejection_id="r1")
        self.assertEqual(rejection.guideline_refs, ("2.1",))

    def test_no_guideline_invented_when_absent(self):
        rejection = parse_rejection("We found some issues with your app.", rejection_id="r1")
        self.assertEqual(rejection.guideline_refs, ())

    def test_multiple_distinct_guidelines_are_all_captured_in_order(self):
        rejection = parse_rejection(
            "Guideline 2.1 - Performance and also Guideline 5.1.1 - Legal apply here.", rejection_id="r1",
        )
        self.assertEqual(rejection.guideline_refs, ("2.1", "5.1.1"))

    def test_raw_text_is_preserved_verbatim(self):
        text = "Guideline 2.1 - Performance: crash on launch."
        rejection = parse_rejection(text, rejection_id="r1")
        self.assertEqual(rejection.raw_text, text)


class SignalExtractionTests(unittest.TestCase):
    def test_review_access_signal_detected(self):
        rejection = parse_rejection("We could not sign in using the demo account credentials.", rejection_id="r1")
        self.assertIn("review_access", rejection.metadata["signals"])

    def test_localization_signal_detected(self):
        rejection = parse_rejection("Your app's localized content is incomplete for some languages.", rejection_id="r1")
        self.assertIn("localization", rejection.metadata["signals"])

    def test_guideline_header_words_do_not_leak_into_signals(self):
        # "Performance" and "Legal" are Apple's own section-name words in the
        # guideline header line, not a content signal -- they must not be
        # mistaken for a crash/performance or legal/policy complaint.
        rejection = parse_rejection(
            "Guideline 2.3 - Performance - Accurate Metadata\n\n"
            "Your app description contains placeholder text.", rejection_id="r1",
        )
        self.assertNotIn("crash_performance", rejection.metadata["signals"])
        self.assertIn("metadata_refs", rejection.metadata["signals"])

    def test_legal_header_word_does_not_leak_into_signals(self):
        rejection = parse_rejection(
            "Guideline 5.1.1 - Legal - Privacy - Data Collection and Storage\n\n"
            "Your app's privacy practices were not accurately reflected.", rejection_id="r1",
        )
        self.assertNotIn("legal_policy", rejection.metadata["signals"])
        self.assertIn("privacy", rejection.metadata["signals"])

    def test_guideline_number_still_extracted_from_header_line(self):
        rejection = parse_rejection(
            "Guideline 2.3 - Performance - Accurate Metadata\n\nPlaceholder text found.", rejection_id="r1",
        )
        self.assertEqual(rejection.guideline_refs, ("2.3",))


class RedactionTests(unittest.TestCase):
    def test_password_is_redacted(self):
        redacted = redact_secrets("password: hunter2secret")
        self.assertNotIn("hunter2secret", redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_email_is_redacted(self):
        redacted = redact_secrets("Contact reviewer@apple.com for details.")
        self.assertNotIn("reviewer@apple.com", redacted)
        self.assertIn("[REDACTED_EMAIL]", redacted)

    def test_non_secret_text_is_unchanged(self):
        text = "Please provide valid demo account credentials."
        self.assertEqual(redact_secrets(text), text)


class ParseRejectionFileTests(unittest.TestCase):
    def test_txt_file_is_parsed_as_manual_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rejection.txt"
            path.write_text("Guideline 2.1 - Performance: crash on launch.")
            rejection = parse_rejection_file(path)
        self.assertEqual(rejection.source, RejectionSource.MANUAL_TEXT)
        self.assertEqual(rejection.guideline_refs, ("2.1",))

    def test_json_file_is_parsed_with_its_own_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rejection.json"
            path.write_text(json.dumps({
                "rejection_id": "custom-id", "raw_text": "Guideline 5.1.1 - Legal - Privacy: issue found.",
                "received_at": "2026-08-23",
            }))
            rejection = parse_rejection_file(path)
        self.assertEqual(rejection.rejection_id, "custom-id")
        self.assertEqual(rejection.guideline_refs, ("5.1.1",))
        self.assertEqual(rejection.source, RejectionSource.ASC_EXPORT)


if __name__ == "__main__":
    unittest.main()
