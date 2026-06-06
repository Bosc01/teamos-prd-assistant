"""Central JSON-backed document store for PM knowledge artifacts."""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
DOCS_FILE = ROOT / "data" / "docs" / "documents.json"
_ALLOWED_DOC_TYPES = {"prd", "prfaq", "rfc", "field_note", "customer_call", "other"}


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------

def load_all() -> List[Dict]:
    """Load all stored documents from disk."""
    if not DOCS_FILE.exists():
        return []
    return json.loads(DOCS_FILE.read_text(encoding="utf-8"))


def save_all(documents: List[Dict]) -> None:
    """Write all documents back to disk atomically."""
    DOCS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = DOCS_FILE.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(documents, indent=2), encoding="utf-8")
    tmp_path.replace(DOCS_FILE)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def add_document(
    title: str,
    doc_url: str,
    doc_type: str,
    author: str,
    product_area: str,
    customers: List[str],
    tags: List[str],
    content_snippet: str,
    full_content: Optional[str] = None,
    created_at: Optional[str] = None,
) -> Dict:
    """Add a document to the local store and return the stored record."""
    if doc_type not in _ALLOWED_DOC_TYPES:
        raise ValueError(f"Invalid doc_type '{doc_type}'. Must be one of: {sorted(_ALLOWED_DOC_TYPES)}")

    created_at_value = created_at or _now_iso()
    added_at_value = _now_iso()
    document: Dict = {
        "id": str(uuid.uuid4()),
        "title": title,
        "doc_url": doc_url,
        "doc_type": doc_type,
        "author": author,
        "product_area": product_area,
        "customers": list(customers),
        "tags": list(tags),
        "content_snippet": content_snippet[:500],
        "full_content": full_content,
        "created_at": created_at_value,
        "added_at": added_at_value,
    }
    all_documents = load_all()
    all_documents.append(document)
    save_all(all_documents)
    return document


def get_document(doc_id: str) -> Dict:
    """Fetch a single document by ID. Raise ValueError if not found."""
    for document in load_all():
        if document["id"] == doc_id:
            return document
    raise ValueError(f"No document found with id: {doc_id}")


def search_documents(query: str, filters: Optional[Dict] = None) -> List[Dict]:
    """Search documents by text query and optional field filters."""
    normalized_query = (query or "").strip().lower()
    filters = filters or {}
    results: List[Dict] = []

    for document in load_all():
        if not _matches_filters(document, filters):
            continue
        if normalized_query and not _matches_query(document, normalized_query):
            continue
        results.append(document)

    return results


def list_documents(
    doc_type: Optional[str] = None,
    product_area: Optional[str] = None,
    customer: Optional[str] = None,
) -> List[Dict]:
    """List documents with optional metadata filters."""
    filters = {
        key: value
        for key, value in {
            "doc_type": doc_type,
            "product_area": product_area,
            "customer": customer,
        }.items()
        if value
    }
    return search_documents(query="", filters=filters)


def delete_document(doc_id: str) -> None:
    """Delete a document by ID."""
    documents = load_all()
    filtered = [document for document in documents if document["id"] != doc_id]
    if len(filtered) == len(documents):
        raise ValueError(f"No document found with id: {doc_id}")
    save_all(filtered)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _matches_query(document: Dict, normalized_query: str) -> bool:
    haystacks = [
        document.get("title", ""),
        document.get("content_snippet", ""),
        document.get("full_content", ""),
    ]
    for field in haystacks:
        if normalized_query in str(field).lower():
            return True

    for tag in document.get("tags", []):
        if normalized_query in str(tag).lower():
            return True

    for customer in document.get("customers", []):
        if normalized_query in str(customer).lower():
            return True

    return False


def _matches_filters(document: Dict, filters: Dict) -> bool:
    doc_type = filters.get("doc_type")
    if doc_type and document.get("doc_type") != doc_type:
        return False

    product_area = filters.get("product_area")
    if product_area and document.get("product_area") != product_area:
        return False

    customer = filters.get("customer")
    if customer:
        normalized_customer = str(customer).lower()
        if not any(normalized_customer in str(item).lower() for item in document.get("customers", [])):
            return False

    return True


def _format_documents(documents: List[Dict]) -> str:
    if not documents:
        return "No documents found."

    lines = []
    for document in documents:
        lines.append(
            f"{document['id'][:8]}  {document['doc_type']}  {document['title']}  "
            f"{document.get('product_area', '')}  {', '.join(document.get('customers', []))}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the local PM document repository.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Add a new document.")
    p_add.add_argument("--title", required=True, help="Document title.")
    p_add.add_argument("--url", required=True, help="Document URL.")
    p_add.add_argument("--type", required=True, choices=sorted(_ALLOWED_DOC_TYPES), help="Document type.")
    p_add.add_argument("--author", required=True, help="Document author.")
    p_add.add_argument("--product-area", required=True, help="Product area tag.")
    p_add.add_argument("--customers", nargs="+", required=True, help="Customer names.")
    p_add.add_argument("--tags", nargs="+", required=True, help="Free-form tags.")
    p_add.add_argument("--content", required=True, help="Pasted content or snippet text.")

    p_search = sub.add_parser("search", help="Search documents.")
    p_search.add_argument("--query", required=True, help="Search text.")
    p_search.add_argument("--type", dest="doc_type", choices=sorted(_ALLOWED_DOC_TYPES), help="Filter by type.")
    p_search.add_argument("--product-area", help="Filter by product area.")
    p_search.add_argument("--customer", help="Filter by customer.")

    p_list = sub.add_parser("list", help="List documents.")
    p_list.add_argument("--type", dest="doc_type", choices=sorted(_ALLOWED_DOC_TYPES), help="Filter by type.")
    p_list.add_argument("--product-area", help="Filter by product area.")
    p_list.add_argument("--customer", help="Filter by customer.")

    p_show = sub.add_parser("show", help="Show a document by ID.")
    p_show.add_argument("--id", required=True, help="Document ID.")

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "add":
        doc = add_document(
            title=args.title,
            doc_url=args.url,
            doc_type=args.doc_type,
            author=args.author,
            product_area=args.product_area,
            customers=args.customers,
            tags=args.tags,
            content_snippet=args.content,
            full_content=args.content,
        )
        print(f"Created document: {doc['id']}")
        print(json.dumps(doc, indent=2))

    elif args.command == "search":
        docs = search_documents(
            args.query,
            filters={
                key: value
                for key, value in {
                    "doc_type": args.doc_type,
                    "product_area": args.product_area,
                    "customer": args.customer,
                }.items()
                if value
            },
        )
        print(_format_documents(docs))

    elif args.command == "list":
        docs = list_documents(doc_type=args.doc_type, product_area=args.product_area, customer=args.customer)
        print(_format_documents(docs))

    elif args.command == "show":
        doc = get_document(args.id)
        print(json.dumps(doc, indent=2))


if __name__ == "__main__":
    main()
