from __future__ import annotations

import hashlib
import json
import zipfile
from io import BytesIO

from veridra.core import demo_assessment
from veridra.exports import build_evidence_package


def test_evidence_package_is_deterministic() -> None:
    assessment = demo_assessment()
    first = build_evidence_package(assessment)
    second = build_evidence_package(assessment)

    assert first.content == second.content
    assert first.filename == "veridra-demo.veridra.local-evidence.zip"


def test_evidence_package_contents_and_manifest() -> None:
    package = build_evidence_package(demo_assessment())

    with zipfile.ZipFile(BytesIO(package.content)) as archive:
        assert set(archive.namelist()) == {
            "assessment.json",
            "report.html",
            "manifest.sha256",
        }
        assessment_json = archive.read("assessment.json")
        report_html = archive.read("report.html")
        manifest_text = archive.read("manifest.sha256").decode("utf-8")

    payload = json.loads(assessment_json)
    assert payload["mode"] == "demo"
    assert b"Veridra assessment report" in report_html
    assert hashlib.sha256(assessment_json).hexdigest() in manifest_text
    assert hashlib.sha256(report_html).hexdigest() in manifest_text
