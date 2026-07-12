import pytest
from aim_api.schemas.scenario import TestStepCreate
from pydantic import ValidationError


def test_fill_accepts_a_valid_secret_reference() -> None:
    step = TestStepCreate(
        action="fill",
        target="#password",
        value="{{secret:LOGIN_PASSWORD}}",
    )

    assert step.value == "{{secret:LOGIN_PASSWORD}}"


def test_fill_accepts_reference_mixed_with_text() -> None:
    step = TestStepCreate(
        action="fill",
        target="#email",
        value="monitor+{{secret:SUFFIX}}@example.com",
    )

    assert step.value == "monitor+{{secret:SUFFIX}}@example.com"


@pytest.mark.parametrize(
    "bad_value",
    [
        "{{secret:lowercase}}",
        "{{secret:}}",
        "{{secret LOGIN_PASSWORD}}",
        "{{ Secret:LOGIN_PASSWORD }}",
        "{{secret:1STARTS_WITH_DIGIT}}",
    ],
)
def test_fill_rejects_malformed_secret_references(bad_value: str) -> None:
    with pytest.raises(ValidationError, match="시크릿 참조 문법"):
        TestStepCreate(action="fill", target="#password", value=bad_value)


def test_non_fill_values_are_not_secret_validated() -> None:
    # assert_text_exists는 화면 텍스트를 그대로 비교하므로 검증 대상이 아니다.
    step = TestStepCreate(action="assert_text_exists", value="{{secret:lowercase}}")

    assert step.value == "{{secret:lowercase}}"
