import unittest

from src.nucleus_ledger_adapter import (
    KNOWN_REASON_CODES,
    validator_result_to_context_flags,
    validator_result_to_fail_tags,
)
from src.repair_playbook import SUPPORTED_FAIL_TAGS
from src.title_body_nucleus_validator import NucleusAlignmentResult, validate_title_body_nucleus


def _make_result(*, aligned=False, reason_code=None):
    return NucleusAlignmentResult(
        aligned=aligned,
        title_subject="坂本勇人",
        title_event="3安打",
        body_subject="坂本勇人" if aligned else "岡本和真",
        body_event="3安打" if aligned else "15号",
        reason_code=reason_code,
        detail=None,
    )


class NucleusLedgerAdapterTests(unittest.TestCase):
    def test_aligned_result_maps_to_empty_lists(self):
        result = _make_result(aligned=True, reason_code=None)

        self.assertEqual(validator_result_to_fail_tags(result), [])
        self.assertEqual(validator_result_to_context_flags(result), [])

    def test_subject_absent_maps_to_existing_fail_tag(self):
        result = _make_result(reason_code="SUBJECT_ABSENT")

        self.assertEqual(validator_result_to_fail_tags(result), ["title_body_mismatch"])

    def test_subject_absent_maps_to_context_flag(self):
        result = _make_result(reason_code="SUBJECT_ABSENT")

        self.assertEqual(validator_result_to_context_flags(result), ["ctx_subject_absent"])

    def test_event_diverge_maps_to_existing_fail_tag(self):
        result = _make_result(reason_code="EVENT_DIVERGE")

        self.assertEqual(validator_result_to_fail_tags(result), ["title_body_mismatch"])

    def test_event_diverge_maps_to_context_flag(self):
        result = _make_result(reason_code="EVENT_DIVERGE")

        self.assertEqual(validator_result_to_context_flags(result), ["ctx_event_diverge"])

    def test_multiple_nuclei_maps_to_existing_fail_tag(self):
        result = _make_result(reason_code="MULTIPLE_NUCLEI")

        self.assertEqual(validator_result_to_fail_tags(result), ["title_body_mismatch"])

    def test_multiple_nuclei_maps_to_context_flag(self):
        result = _make_result(reason_code="MULTIPLE_NUCLEI")

        self.assertEqual(validator_result_to_context_flags(result), ["ctx_multiple_nuclei"])

    def test_unknown_reason_maps_to_empty_lists(self):
        result = _make_result(reason_code="FOO_BAR")

        self.assertEqual(validator_result_to_fail_tags(result), [])
        self.assertEqual(validator_result_to_context_flags(result), [])

    def test_unaligned_without_reason_maps_to_empty_lists(self):
        result = _make_result(reason_code=None)

        self.assertEqual(validator_result_to_fail_tags(result), [])
        self.assertEqual(validator_result_to_context_flags(result), [])

    def test_empty_reason_maps_to_empty_lists(self):
        result = _make_result(reason_code="")

        self.assertEqual(validator_result_to_fail_tags(result), [])
        self.assertEqual(validator_result_to_context_flags(result), [])

    def test_fail_tag_calls_are_idempotent(self):
        result = _make_result(reason_code="SUBJECT_ABSENT")

        first = validator_result_to_fail_tags(result)
        second = validator_result_to_fail_tags(result)

        self.assertEqual(first, second)
        self.assertIsNot(first, second)

    def test_context_flag_calls_are_idempotent(self):
        result = _make_result(reason_code="EVENT_DIVERGE")

        first = validator_result_to_context_flags(result)
        second = validator_result_to_context_flags(result)

        self.assertEqual(first, second)
        self.assertIsNot(first, second)

    def test_fail_tags_stay_within_supported_ledger_schema(self):
        tags = {
            tag
            for reason_code in KNOWN_REASON_CODES
            for tag in validator_result_to_fail_tags(_make_result(reason_code=reason_code))
        }

        self.assertEqual(tags, {"title_body_mismatch"})
        self.assertTrue(tags.issubset(SUPPORTED_FAIL_TAGS))

    def test_fail_tags_do_not_introduce_new_schema_values(self):
        observed = []
        for reason_code in sorted(KNOWN_REASON_CODES):
            observed.extend(validator_result_to_fail_tags(_make_result(reason_code=reason_code)))

        self.assertEqual(set(observed), {"title_body_mismatch"})

    def test_context_flags_use_ctx_prefix(self):
        flags = [
            flag
            for reason_code in KNOWN_REASON_CODES
            for flag in validator_result_to_context_flags(_make_result(reason_code=reason_code))
        ]

        self.assertTrue(flags)
        self.assertTrue(all(flag.startswith("ctx_") for flag in flags))

    def test_none_argument_raises_type_error_for_fail_tags(self):
        with self.assertRaises(TypeError):
            validator_result_to_fail_tags(None)

    def test_none_argument_raises_type_error_for_context_flags(self):
        with self.assertRaises(TypeError):
            validator_result_to_context_flags(None)

    def test_validator_integration_subject_absent_maps_cleanly(self):
        result = validate_title_body_nucleus(
            "岡本和真 4番起用",
            "坂本勇人は3番で先発出場する。",
            "lineup",
        )

        self.assertEqual(result.reason_code, "SUBJECT_ABSENT")
        self.assertEqual(validator_result_to_fail_tags(result), ["title_body_mismatch"])
        self.assertEqual(validator_result_to_context_flags(result), ["ctx_subject_absent"])


if __name__ == "__main__":
    unittest.main()
