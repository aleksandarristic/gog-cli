from __future__ import annotations

from pathlib import Path

from gog_cli.layout import BackupLayout, sanitize_directory_name, sanitize_filename


def test_backup_layout_top_level_dirs() -> None:
    layout = BackupLayout(root=Path("/backups"))
    assert layout.metadata_dir == Path("/backups/metadata")
    assert layout.games_dir == Path("/backups/games")


def test_backup_layout_metadata_files() -> None:
    layout = BackupLayout(root=Path("/backups"))
    assert layout.manifest_file == Path("/backups/metadata/manifest.json")
    assert layout.library_snapshot == Path("/backups/metadata/library.json")


def test_backup_layout_game_paths() -> None:
    layout = BackupLayout(root=Path("/backups"))
    assert layout.game_dir("example_game") == Path("/backups/games/example_game")
    assert layout.game_metadata("example_game") == Path("/backups/games/example_game/metadata.json")


def test_backup_layout_game_subdirs() -> None:
    layout = BackupLayout(root=Path("/backups"))
    game = layout.game_dir("example_game")
    assert layout.installers_dir(game) == Path("/backups/games/example_game/installers")
    assert layout.patches_dir(game) == Path("/backups/games/example_game/patches")
    assert layout.extras_dir(game) == Path("/backups/games/example_game/extras")
    assert layout.language_packs_dir(game) == Path("/backups/games/example_game/language-packs")
    assert layout.manuals_dir(game) == Path("/backups/games/example_game/manuals")
    assert layout.other_dir(game) == Path("/backups/games/example_game/other")


def test_sanitize_filename_path_separators() -> None:
    assert sanitize_filename("path/to/file") == "path_to_file"
    assert sanitize_filename("path\\to\\file") == "path_to_file"


def test_sanitize_filename_control_chars() -> None:
    assert sanitize_filename("hello\x00world") == "helloworld"
    assert sanitize_filename("hello\x1fworld") == "helloworld"
    assert sanitize_filename("hello\x7fworld") == "helloworld"


def test_sanitize_filename_windows_reserved_chars() -> None:
    assert sanitize_filename("file<name>") == "file_name_"
    assert sanitize_filename("file:name") == "file_name"
    assert sanitize_filename('file"name') == "file_name"
    assert sanitize_filename("file|name") == "file_name"
    assert sanitize_filename("file?name") == "file_name"
    assert sanitize_filename("file*name") == "file_name"


def test_sanitize_filename_strips_whitespace() -> None:
    assert sanitize_filename("  hello  ") == "hello"


def test_sanitize_filename_strips_trailing_dots() -> None:
    assert sanitize_filename("hello...") == "hello"


def test_sanitize_filename_preserves_leading_dots() -> None:
    assert sanitize_filename("  .hello.  ") == ".hello"


def test_sanitize_filename_empty_returns_underscore() -> None:
    assert sanitize_filename("") == "_"
    assert sanitize_filename("...") == "_"
    assert sanitize_filename("\x00\x01") == "_"
    assert sanitize_filename("   ") == "_"


def test_sanitize_filename_truncates_at_200_chars() -> None:
    long_name = "a" * 300
    result = sanitize_filename(long_name)
    assert len(result) == 200


def test_sanitize_filename_normal_name_unchanged() -> None:
    assert sanitize_filename("The Witcher 3") == "The Witcher 3"
    assert sanitize_filename("cyberpunk-2077") == "cyberpunk-2077"


def test_sanitize_directory_name_without_product_id() -> None:
    assert sanitize_directory_name("Example Game") == "Example Game"


def test_sanitize_directory_name_with_product_id() -> None:
    assert sanitize_directory_name("Example Game", "1234567890") == "Example Game_1234567890"


def test_sanitize_directory_name_sanitizes_before_appending() -> None:
    assert sanitize_directory_name("Bad/Name", "42") == "Bad_Name_42"
