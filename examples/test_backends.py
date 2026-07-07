"""
Test both HTTP and CLI backends.
"""

from pathlib import Path
import sys

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from elib.services.ncbi_client import NCBIClient


def test_backend(use_cli: bool):
    """Test a specific backend."""
    backend_name = "CLI" if use_cli else "HTTP"
    print(f"\n{'=' * 60}")
    print(f"Testing {backend_name} Backend")
    print(f"{'=' * 60}\n")

    try:
        client = NCBIClient(email="nberry11@gmail.com", use_cli=use_cli)

        # Test DOI
        test_doi = "10.3389/fphys.2021.627320"
        print(f"Searching for DOI: {test_doi}")

        pmid = client.search_by_doi(test_doi)
        if pmid:
            print(f"✓ Found PMID: {pmid}\n")

            # Fetch reference
            ref = client.fetch_reference(pmid)
            if ref:
                print(f"✓ Title: {ref.title[:60]}...")
                print(f"✓ Authors: {len(ref.authors)} author(s)")
                print(f"✓ Journal: {ref.journal.title}")
                print(f"✓ Year: {ref.publication_year()}")
            else:
                print("✗ Failed to fetch reference")
        else:
            print("✗ No PMID found")

    except Exception as e:
        print(f"✗ Backend failed: {e}")


if __name__ == "__main__":
    # Test HTTP backend
    test_backend(use_cli=False)

    # Test CLI backend (if available)
    test_backend(use_cli=True)
