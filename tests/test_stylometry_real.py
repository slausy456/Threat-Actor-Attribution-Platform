import json

from scripts import evaluate_stylometry_real as evaluator


def _write_pair(folder, filename, pair_id, same):
    folder.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": pair_id,
        "pair": ["hello, this is a sample text.", "another sample text with words!"],
        "same": same,
    }
    (folder / filename).write_text(json.dumps(payload), encoding="utf-8")


def test_loader_reads_only_train_val_test_split_folders(tmp_path):
    root = tmp_path / "veridark"
    _write_pair(root / "train", "train-1.json", "train-1", True)
    _write_pair(root / "val", "val-1.json", "val-1", False)
    _write_pair(root / "test", "test-1.json", "test-1", True)
    _write_pair(root / "val+test", "duplicate.json", "duplicate-val-test", False)
    _write_pair(root / "train+val+test", "duplicate.json", "duplicate-all", True)

    assert [item["id"] for item in evaluator.load_split(root, "train")] == ["train-1"]
    assert [item["id"] for item in evaluator.load_split(root, "val")] == ["val-1"]
    assert [item["id"] for item in evaluator.load_split(root, "test")] == ["test-1"]
    assert evaluator.load_split(root, "val") == [
        {
            "id": "val-1",
            "pair": ["hello, this is a sample text.", "another sample text with words!"],
            "same": False,
        }
    ]


def test_missing_dataset_prints_expected_layout_and_exits_cleanly(tmp_path, capsys):
    result = evaluator.evaluate(tmp_path / "missing-veridark")
    output = capsys.readouterr().out
    assert result == 0
    assert "data/veridark/" in output
    assert "train/<one JSON file per pair>" in output
    assert "val/<one JSON file per pair>" in output
    assert "test/<one JSON file per pair>" in output


def test_scoring_constructs_personas_without_identifiers(monkeypatch):
    captured = []

    class Result:
        score = 0.75

    def fake_compare(persona_a, persona_b):
        captured.extend((persona_a, persona_b))
        return Result()

    monkeypatch.setattr(evaluator, "compare", fake_compare)
    scored = evaluator.score_pairs(
        [{"id": "sample-1", "pair": ["first text", "second text"], "same": True}]
    )

    assert scored == [(True, 0.75)]
    assert all(not persona.identifiers for persona in captured)
    assert [persona.texts[0].text for persona in captured] == ["first text", "second text"]
