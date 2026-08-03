# ABOUTME: Tests for JSON narrowing helpers and record types.
# ABOUTME: Covers both the success and failure path of every helper.
"""Tests for JSON narrowing helpers and record types."""

import pytest

from pylbry.errors import DaemonInternalError
from pylbry.models import (
    as_bool,
    as_int,
    as_list,
    as_object,
    as_str,
    opt_int,
    opt_str,
)

TWO = 2
THREE = 3


def test_as_object_returns_a_mapping() -> None:
    """as_object passes a JSON object through unchanged."""
    assert as_object({"a": 1}) == {"a": 1}


def test_as_object_rejects_a_non_object() -> None:
    """as_object raises when the value is not a JSON object."""
    with pytest.raises(DaemonInternalError, match="expected object"):
        as_object("nope")


def test_as_list_returns_a_sequence() -> None:
    """as_list passes a JSON array through unchanged."""
    assert as_list([1, 2]) == [1, 2]


def test_as_list_rejects_a_non_list() -> None:
    """as_list raises when the value is not a JSON array."""
    with pytest.raises(DaemonInternalError, match="expected list"):
        as_list({})


def test_as_str_returns_a_string() -> None:
    """as_str passes a string through unchanged."""
    assert as_str("x") == "x"


def test_as_str_rejects_a_non_string() -> None:
    """as_str raises when the value is not a string."""
    with pytest.raises(DaemonInternalError, match="expected str"):
        as_str(1)


def test_as_int_returns_an_integer() -> None:
    """as_int passes an integer through unchanged."""
    assert as_int(THREE) == THREE


def test_as_int_rejects_a_non_integer() -> None:
    """as_int raises when the value is not an integer."""
    with pytest.raises(DaemonInternalError, match="expected int"):
        as_int("3")


def test_as_int_rejects_a_boolean() -> None:
    """as_int rejects booleans, which are a subclass of int in Python."""
    with pytest.raises(DaemonInternalError, match="expected int"):
        as_int(True)


def test_as_bool_returns_a_boolean() -> None:
    """as_bool passes a boolean through unchanged."""
    assert as_bool(True) is True


def test_as_bool_rejects_a_non_boolean() -> None:
    """as_bool raises when the value is not a boolean."""
    with pytest.raises(DaemonInternalError, match="expected bool"):
        as_bool(1)


def test_opt_str_maps_none_to_none() -> None:
    """opt_str returns None for a missing value and passes strings through."""
    assert opt_str(None) is None
    assert opt_str("x") == "x"


def test_opt_str_rejects_a_non_string() -> None:
    """opt_str raises when a present value is not a string."""
    with pytest.raises(DaemonInternalError, match="expected str"):
        opt_str(1)


def test_opt_int_maps_none_to_none() -> None:
    """opt_int returns None for a missing value and passes integers through."""
    assert opt_int(None) is None
    assert opt_int(TWO) == TWO


def test_opt_int_rejects_a_non_integer() -> None:
    """opt_int raises when a present value is not an integer."""
    with pytest.raises(DaemonInternalError, match="expected int"):
        opt_int("2")
