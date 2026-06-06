"""Unit tests for src/doc_store.py."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import doc_store


def _add_doc(**kwargs) -> dict:
    defaults = dict(
        title="Terraform Cloud PRD",
        doc_url="https://example.com/doc",
        doc_type="prd",
        author="@pm",
        product_area="terraform_cloud",
        customers=["Acme"],
        tags=["launch", "platform"],
        content_snippet="This document describes the launch plan.",
        full_content="This document describes the launch plan in full.",
    )
    defaults.update(kwargs)
    return doc_store.add_document(**defaults)


class TestAddAndRetrieveDocument(unittest.TestCase):
    def test_add_document_persists_and_can_be_retrieved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_file = Path(tmp) / "documents.json"
            with mock.patch.object(doc_store, "DOCS_FILE", docs_file):
                created = _add_doc(title="Persisted PRD")
                self.assertTrue(docs_file.exists())
                saved = json.loads(docs_file.read_text(encoding="utf-8"))
                self.assertEqual(len(saved), 1)
                self.assertEqual(saved[0]["title"], "Persisted PRD")

                loaded = doc_store.get_document(created["id"])
                self.assertEqual(loaded["id"], created["id"])
                self.assertEqual(loaded["title"], "Persisted PRD")


class TestSearchDocuments(unittest.TestCase):
    def test_search_finds_by_title_keyword(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_file = Path(tmp) / "documents.json"
            with mock.patch.object(doc_store, "DOCS_FILE", docs_file):
                _add_doc(
                    title="Terraform Cloud launch plan",
                    tags=["launch-plan"],
                    content_snippet="Launch planning notes.",
                    full_content="Launch planning notes.",
                )
                _add_doc(
                    title="Ansible customer review",
                    tags=["review"],
                    customers=["Initech"],
                    content_snippet="Customer interview notes.",
                    full_content="Customer interview notes.",
                )

                results = doc_store.search_documents("launch")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Terraform Cloud launch plan")

    def test_search_finds_by_customer_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_file = Path(tmp) / "documents.json"
            with mock.patch.object(doc_store, "DOCS_FILE", docs_file):
                _add_doc(customers=["Acme", "Globex"])
                _add_doc(customers=["Umbrella"])

                results = doc_store.search_documents("globex")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["customers"], ["Acme", "Globex"])


class TestListDocuments(unittest.TestCase):
    def test_list_filters_by_doc_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_file = Path(tmp) / "documents.json"
            with mock.patch.object(doc_store, "DOCS_FILE", docs_file):
                _add_doc(doc_type="prd", title="PRD One")
                _add_doc(doc_type="rfc", title="RFC One")

                results = doc_store.list_documents(doc_type="prd")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["doc_type"], "prd")

    def test_list_filters_by_product_area(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_file = Path(tmp) / "documents.json"
            with mock.patch.object(doc_store, "DOCS_FILE", docs_file):
                _add_doc(product_area="terraform_cloud", title="Cloud Doc")
                _add_doc(product_area="terraform_core", title="Core Doc")

                results = doc_store.list_documents(product_area="terraform_core")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["product_area"], "terraform_core")


if __name__ == "__main__":
    unittest.main()
