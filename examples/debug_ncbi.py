"""
Debug NCBI connectivity for specific DOIs.
"""

from pathlib import Path
import sys

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from elib.services.ncbi_client import NCBIClient
from elib.utils.config import Config


def test_dois():
    """Test NCBI lookup for the example DOIs."""

    # Try to load config
    try:
        config = Config.load()
        email = config.ncbi_email
        api_key = config.ncbi_api_key
    except:
        email = "nberry11@gmail.com"
        api_key = None
        print("⚠ Could not load config, using default email")

    print(f"Using email: {email}")
    print(f"API key: {'✓' if api_key else '✗'}")
    print()

    client = NCBIClient(email=email, api_key=api_key)

    test_dois = [
        "10.3389/fphys.2021.627320",
        "10.1016/j.medengphy.2014.07.021",
        "10.1038/nature12373",  # Known good DOI for testing
    ]

    for doi in test_dois:
        print(f"Testing DOI: {doi}")
        print("-" * 60)

        # Search for PMID
        pmid = client.search_by_doi(doi)

        if pmid:
            print(f"  ✓ Found PMID: {pmid}")

            # Try to fetch reference
            ref = client.fetch_reference(pmid)
            if ref:
                print(f"  ✓ Title: {ref.title[:60]}...")
                print(f"  ✓ Authors: {len(ref.authors)} author(s)")
                if ref.authors:
                    print(f"  ✓ First author: {ref.authors[0].last_name}")
            else:
                print("  ✗ Could not fetch reference data")
        else:
            print("  ✗ No PMID found")

        print()


if __name__ == "__main__":
    test_dois()
