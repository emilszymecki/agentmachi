import json

from send import _print_message


def test_print_message_malformed_frame_is_visible_and_next_frame_still_prints(
        capsys):
    _print_message("{to nie jest json")
    _print_message(json.dumps({"from": "beta", "text": "dalej dziala"}))

    assert capsys.readouterr().out.splitlines() == [
        "{to nie jest json",
        "beta: dalej dziala",
    ]


def test_print_message_valid_json_scalar_does_not_crash(capsys):
    _print_message("null")
    assert capsys.readouterr().out.strip() == "null"
