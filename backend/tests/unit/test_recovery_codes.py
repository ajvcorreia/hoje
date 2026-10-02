import re

from hoje.security.tokens import generate_recovery_codes, normalize_recovery_code


def test_ten_unique_codes_in_format() -> None:
    codes = generate_recovery_codes()
    assert len(codes) == 10
    assert len(set(codes)) == 10
    assert all(re.fullmatch(r"[A-Z2-7]{5}-[A-Z2-7]{5}", c) for c in codes)


def test_codes_differ_between_calls() -> None:
    assert set(generate_recovery_codes()).isdisjoint(generate_recovery_codes())


def test_normalisation_ignores_case_spaces_and_hyphens() -> None:
    assert normalize_recovery_code("abcde-fghij") == "ABCDEFGHIJ"
    assert normalize_recovery_code(" ABCDE FGHIJ ") == "ABCDEFGHIJ"
    assert normalize_recovery_code("AbCdEfGhIj") == "ABCDEFGHIJ"


def test_normalisation_rejects_other_input() -> None:
    for bad in ("123456", "ABCDE-FGHI", "ABCDE-FGHIJK", "ABCDE-FGHI1", "", "abcde-fghi!"):
        assert normalize_recovery_code(bad) is None


def test_generated_codes_normalise_to_themselves() -> None:
    for code in generate_recovery_codes():
        assert normalize_recovery_code(code) == code.replace("-", "")
