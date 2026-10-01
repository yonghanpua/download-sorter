import pytest

import db
import sorter
from sorter import (
    get_category,
    get_client,
    get_client_subcategory,
    get_regex_category,
    is_ignored,
    is_temp_file,
    resolve_duplicate,
    sort_file,
    sweep,
    undo,
    undo_selected,
)


@pytest.fixture(autouse=True)
def _temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()


# --- is_ignored ---

class TestIsIgnored:
    def test_exact_match(self, monkeypatch):
        monkeypatch.setattr(sorter, "IGNORE_LIST", ["desktop.ini"])
        from pathlib import Path
        assert is_ignored(Path("C:/Downloads/desktop.ini")) is True

    def test_glob_wildcard(self, monkeypatch):
        monkeypatch.setattr(sorter, "IGNORE_LIST", ["*.bak"])
        from pathlib import Path
        assert is_ignored(Path("C:/Downloads/data.bak")) is True

    def test_prefix_wildcard(self, monkeypatch):
        monkeypatch.setattr(sorter, "IGNORE_LIST", ["temp_*"])
        from pathlib import Path
        assert is_ignored(Path("C:/Downloads/temp_notes.txt")) is True

    def test_case_insensitive(self, monkeypatch):
        monkeypatch.setattr(sorter, "IGNORE_LIST", ["Thumbs.db"])
        from pathlib import Path
        assert is_ignored(Path("C:/Downloads/thumbs.db")) is True

    def test_no_match(self, monkeypatch):
        monkeypatch.setattr(sorter, "IGNORE_LIST", ["desktop.ini"])
        from pathlib import Path
        assert is_ignored(Path("C:/Downloads/report.pdf")) is False

    def test_empty_list(self, monkeypatch):
        monkeypatch.setattr(sorter, "IGNORE_LIST", [])
        from pathlib import Path
        assert is_ignored(Path("C:/Downloads/anything.txt")) is False

    def test_sort_file_skips_ignored(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sorter, "IGNORE_LIST", ["desktop.ini"])
        f = tmp_path / "desktop.ini"
        f.write_text("test")
        assert sort_file(f, tmp_path) is None
        assert f.exists()


# --- get_regex_category ---

class TestGetRegexCategory:
    def test_matches_pattern(self, monkeypatch):
        monkeypatch.setattr(sorter, "REGEX_RULES", {r"^INV-\d+": "Invoices"})
        from pathlib import Path
        assert get_regex_category(Path("C:/Downloads/INV-2024-001.pdf")) == "Invoices"

    def test_no_match(self, monkeypatch):
        monkeypatch.setattr(sorter, "REGEX_RULES", {r"^INV-\d+": "Invoices"})
        from pathlib import Path
        assert get_regex_category(Path("C:/Downloads/report.pdf")) is None

    def test_empty_rules(self, monkeypatch):
        monkeypatch.setattr(sorter, "REGEX_RULES", {})
        from pathlib import Path
        assert get_regex_category(Path("C:/Downloads/anything.pdf")) is None

    def test_case_insensitive_flag_in_pattern(self, monkeypatch):
        monkeypatch.setattr(sorter, "REGEX_RULES", {r"(?i)screenshot": "Screenshots"})
        from pathlib import Path
        assert get_regex_category(Path("C:/Downloads/Screenshot_2024.png")) == "Screenshots"

    def test_sort_file_uses_regex(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sorter, "REGEX_RULES", {r"^INV-\d+": "Invoices"})
        f = tmp_path / "INV-2024-001.pdf"
        f.write_text("test")
        result = sort_file(f, tmp_path)
        assert result == tmp_path / "Invoices" / "INV-2024-001.pdf"
        assert result.exists()

    def test_client_takes_priority_over_regex(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sorter, "REGEX_RULES", {r"report": "Reports"})
        f = tmp_path / "AKSS_report.pdf"
        f.write_text("test")
        result = sort_file(f, tmp_path)
        assert "AKSS" in str(result)


# --- is_temp_file ---

class TestIsTempFile:
    def test_crdownload(self, tmp_path):
        assert is_temp_file(tmp_path / "file.crdownload") is True

    def test_part(self, tmp_path):
        assert is_temp_file(tmp_path / "file.part") is True

    def test_tmp(self, tmp_path):
        assert is_temp_file(tmp_path / "file.tmp") is True

    def test_normal_file(self, tmp_path):
        assert is_temp_file(tmp_path / "file.pdf") is False

    def test_case_insensitive(self, tmp_path):
        assert is_temp_file(tmp_path / "file.CRDOWNLOAD") is True


# --- get_category ---

class TestGetCategory:
    def test_pdf_is_documents(self, tmp_path):
        assert get_category(tmp_path / "file.pdf") == "Documents"

    def test_jpg_is_images(self, tmp_path):
        assert get_category(tmp_path / "file.jpg") == "Images"

    def test_mp4_is_media(self, tmp_path):
        assert get_category(tmp_path / "file.mp4") == "Media"

    def test_zip_is_archives(self, tmp_path):
        assert get_category(tmp_path / "file.zip") == "Archives"

    def test_exe_is_installers(self, tmp_path):
        assert get_category(tmp_path / "file.exe") == "Installers"

    def test_py_is_code(self, tmp_path):
        assert get_category(tmp_path / "file.py") == "Code"

    def test_ttf_is_fonts(self, tmp_path):
        assert get_category(tmp_path / "file.ttf") == "Fonts"

    def test_3mf_is_3d_prints(self, tmp_path):
        assert get_category(tmp_path / "file.3mf") == "3D Prints"

    def test_unknown_extension(self, tmp_path):
        assert get_category(tmp_path / "file.xyz") is None

    def test_case_insensitive(self, tmp_path):
        assert get_category(tmp_path / "file.PDF") == "Documents"


# --- get_client ---

class TestGetClient:
    def test_matches_keyword(self, tmp_path):
        assert get_client(tmp_path / "AKSS_report.pdf") == "AKSS"

    def test_matches_alternate_keyword(self, tmp_path):
        assert get_client(tmp_path / "AKS24_data.csv") == "AKSS"

    def test_case_insensitive(self, tmp_path):
        assert get_client(tmp_path / "akss_notes.txt") == "AKSS"

    def test_no_match(self, tmp_path):
        assert get_client(tmp_path / "random_file.pdf") is None

    def test_keyword_anywhere_in_name(self, tmp_path):
        assert get_client(tmp_path / "project_AKSS_v2.docx") == "AKSS"


# --- get_client_subcategory ---

class TestGetClientSubcategory:
    def test_keyword_proposal(self, tmp_path):
        assert get_client_subcategory(tmp_path / "AKSS_proposal.txt") == "01. Commercial"

    def test_keyword_dev(self, tmp_path):
        assert get_client_subcategory(tmp_path / "AKSS_dev_report.pdf") == "03. Development"

    def test_keyword_manual(self, tmp_path):
        assert get_client_subcategory(tmp_path / "AKSS_manual.pdf") == "02. Documentation"

    def test_keyword_wins_over_extension(self, tmp_path):
        result = get_client_subcategory(tmp_path / "AKSS_dev_report.pdf")
        assert result == "03. Development"

    def test_extension_fallback(self, tmp_path):
        result = get_client_subcategory(tmp_path / "AKSS_summary.pdf")
        assert result == "01. Commercial"

    def test_no_match(self, tmp_path):
        assert get_client_subcategory(tmp_path / "AKSS_data.xyz") is None


# --- resolve_duplicate ---

class TestResolveDuplicate:
    def test_no_conflict(self, tmp_path):
        dest = tmp_path / "file.pdf"
        assert resolve_duplicate(dest) == dest

    def test_first_duplicate(self, tmp_path):
        (tmp_path / "file.pdf").touch()
        result = resolve_duplicate(tmp_path / "file.pdf")
        assert result == tmp_path / "file (1).pdf"

    def test_multiple_duplicates(self, tmp_path):
        (tmp_path / "file.pdf").touch()
        (tmp_path / "file (1).pdf").touch()
        (tmp_path / "file (2).pdf").touch()
        result = resolve_duplicate(tmp_path / "file.pdf")
        assert result == tmp_path / "file (3).pdf"


# --- sort_file ---

class TestSortFile:
    def test_sorts_by_extension(self, tmp_path):
        f = tmp_path / "report.pdf"
        f.write_text("test")
        result = sort_file(f, tmp_path)
        assert result == tmp_path / "Documents" / "report.pdf"
        assert result.exists()
        assert not f.exists()

    def test_skips_temp_file(self, tmp_path):
        f = tmp_path / "download.crdownload"
        f.write_text("test")
        assert sort_file(f, tmp_path) is None
        assert f.exists()

    def test_skips_dotfile(self, tmp_path):
        f = tmp_path / ".hidden"
        f.write_text("test")
        assert sort_file(f, tmp_path) is None

    def test_skips_unknown_extension(self, tmp_path):
        f = tmp_path / "data.xyz"
        f.write_text("test")
        assert sort_file(f, tmp_path) is None
        assert f.exists()

    def test_handles_duplicate(self, tmp_path):
        docs = tmp_path / "Documents"
        docs.mkdir()
        (docs / "report.pdf").write_text("original")
        f = tmp_path / "report.pdf"
        f.write_text("new")
        result = sort_file(f, tmp_path)
        assert result == docs / "report (1).pdf"
        assert result.exists()

    def test_skips_nonexistent_file(self, tmp_path):
        assert sort_file(tmp_path / "gone.pdf", tmp_path) is None

    def test_client_sorting(self, tmp_path):
        f = tmp_path / "AKSS_report.pdf"
        f.write_text("test")
        result = sort_file(f, tmp_path)
        assert result == tmp_path / "AKSS" / "01. Commercial" / "AKSS_report.pdf"
        assert result.exists()

    def test_client_keyword_priority(self, tmp_path):
        f = tmp_path / "AKSS_dev_notes.pdf"
        f.write_text("test")
        result = sort_file(f, tmp_path)
        assert result == tmp_path / "AKSS" / "03. Development" / "AKSS_dev_notes.pdf"

    def test_client_no_subcategory(self, tmp_path):
        f = tmp_path / "AKSS_data.xyz"
        f.write_text("test")
        result = sort_file(f, tmp_path)
        assert result == tmp_path / "AKSS" / "AKSS_data.xyz"

    def test_creates_subdirectories(self, tmp_path):
        f = tmp_path / "AKSS_proposal.docx"
        f.write_text("test")
        sort_file(f, tmp_path)
        assert (tmp_path / "AKSS" / "01. Commercial").is_dir()

    def test_records_to_database(self, tmp_path):
        f = tmp_path / "report.pdf"
        f.write_text("test")
        sort_file(f, tmp_path)
        records = db.get_pending_undos()
        assert len(records) == 1
        assert records[0]["category"] == "Documents"


# --- sweep ---

class TestSweep:
    def test_sorts_multiple_files(self, tmp_path):
        (tmp_path / "photo.jpg").write_text("img")
        (tmp_path / "report.pdf").write_text("doc")
        (tmp_path / "app.exe").write_text("exe")
        count = sweep(tmp_path)
        assert count == 3
        assert (tmp_path / "Images" / "photo.jpg").exists()
        assert (tmp_path / "Documents" / "report.pdf").exists()
        assert (tmp_path / "Installers" / "app.exe").exists()

    def test_skips_directories(self, tmp_path):
        (tmp_path / "subfolder").mkdir()
        (tmp_path / "file.pdf").write_text("test")
        count = sweep(tmp_path)
        assert count == 1
        assert (tmp_path / "subfolder").is_dir()

    def test_empty_folder(self, tmp_path):
        assert sweep(tmp_path) == 0

    def test_skips_unknown_and_temp(self, tmp_path):
        (tmp_path / "data.xyz").write_text("unknown")
        (tmp_path / "download.crdownload").write_text("temp")
        (tmp_path / "report.pdf").write_text("doc")
        count = sweep(tmp_path)
        assert count == 1
        assert (tmp_path / "data.xyz").exists()
        assert (tmp_path / "download.crdownload").exists()

    def test_records_sweep_event(self, tmp_path):
        (tmp_path / "photo.jpg").write_text("img")
        sweep(tmp_path)
        stats = db.get_stats()
        assert stats["total_sweeps"] == 1


# --- undo ---

class TestUndo:
    def test_undo_last_move(self, tmp_path):
        f = tmp_path / "report.pdf"
        f.write_text("test")
        sort_file(f, tmp_path)
        assert (tmp_path / "Documents" / "report.pdf").exists()
        assert not f.exists()

        undone = undo(1)
        assert undone == 1
        assert f.exists()
        assert not (tmp_path / "Documents" / "report.pdf").exists()

    def test_undo_multiple(self, tmp_path):
        f1 = tmp_path / "photo.jpg"
        f2 = tmp_path / "report.pdf"
        f1.write_text("img")
        f2.write_text("doc")
        sort_file(f1, tmp_path)
        sort_file(f2, tmp_path)

        undone = undo(2)
        assert undone == 2
        assert f1.exists()
        assert f2.exists()

    def test_undo_all(self, tmp_path):
        for name in ["a.pdf", "b.jpg", "c.exe"]:
            f = tmp_path / name
            f.write_text("test")
            sort_file(f, tmp_path)

        undone = undo(100)
        assert undone == 3
        assert (tmp_path / "a.pdf").exists()
        assert (tmp_path / "b.jpg").exists()
        assert (tmp_path / "c.exe").exists()

    def test_undo_empty_history(self, tmp_path):
        assert undo(1) == 0

    def test_undo_missing_file(self, tmp_path):
        f = tmp_path / "report.pdf"
        f.write_text("test")
        sort_file(f, tmp_path)
        (tmp_path / "Documents" / "report.pdf").unlink()

        undone = undo(1)
        assert undone == 0

    def test_undo_marks_record_undone(self, tmp_path):
        f = tmp_path / "report.pdf"
        f.write_text("test")
        sort_file(f, tmp_path)
        assert len(db.get_pending_undos()) == 1

        undo(1)
        assert len(db.get_pending_undos()) == 0


# --- undo_selected ---

class TestUndoSelected:
    def test_undo_specific_files(self, tmp_path):
        f1 = tmp_path / "a.pdf"
        f2 = tmp_path / "b.jpg"
        f3 = tmp_path / "c.exe"
        f1.write_text("a")
        f2.write_text("b")
        f3.write_text("c")
        sort_file(f1, tmp_path)
        sort_file(f2, tmp_path)
        sort_file(f3, tmp_path)

        records = db.get_pending_undos()
        mid_id = records[1]["id"]
        undone = undo_selected([mid_id])
        assert undone == 1
        assert len(db.get_pending_undos()) == 2

    def test_skip_already_undone(self, tmp_path):
        f = tmp_path / "report.pdf"
        f.write_text("test")
        sort_file(f, tmp_path)
        records = db.get_pending_undos()
        move_id = records[0]["id"]
        undo_selected([move_id])
        assert undo_selected([move_id]) == 0

    def test_skip_missing_file(self, tmp_path):
        f = tmp_path / "report.pdf"
        f.write_text("test")
        sort_file(f, tmp_path)
        (tmp_path / "Documents" / "report.pdf").unlink()
        records = db.get_pending_undos()
        assert undo_selected([records[0]["id"]]) == 0
