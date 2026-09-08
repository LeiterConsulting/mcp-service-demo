from __future__ import annotations

import tarfile

from mcp_service_demo.cli import package_splunk_app


def test_splunk_app_package_excludes_macos_metadata(monkeypatch, tmp_path):
    source = tmp_path / "splunk_app" / "mcp_service_demo"
    (source / "default").mkdir(parents=True)
    (source / "default" / "app.conf").write_text("[install]\n", encoding="utf-8")
    (source / "default" / ".DS_Store").write_text("metadata", encoding="utf-8")
    (source / "default" / "._app.conf").write_text("metadata", encoding="utf-8")
    (source / "__MACOSX").mkdir()
    (source / "__MACOSX" / "app.conf").write_text("metadata", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    output = package_splunk_app(tmp_path / "dist" / "app.tar.gz")

    with tarfile.open(output, "r:gz") as archive:
        assert archive.getnames() == ["mcp_service_demo/default/app.conf"]
