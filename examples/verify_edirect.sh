#!/usr/bin/bash
# Verify all E-utilities components are installed

echo "=== Checking E-utilities Installation ==="
echo ""

TOOLS=("esearch" "efetch" "xtract" "epost" "elink")
MISSING=()

for tool in "${TOOLS[@]}"; do
    if command -v $tool &> /dev/null; then
        echo "✓ $tool found at: $(which $tool)"
    else
        echo "✗ $tool NOT FOUND"
        MISSING+=($tool)
    fi
done

echo ""

if [ ${#MISSING[@]} -eq 0 ]; then
    echo "✓ All tools installed!"
    echo ""
    echo "Testing with sample query..."
    esearch -db pubmed -query "10.1038/nature12373[DOI]" | efetch -format uid
else
    echo "✗ Missing tools: ${MISSING[*]}"
    echo ""
    echo "To fix, run:"
    echo "  cd ~"
    echo "  sh -c \"\$(curl -fsSL ftp://ftp.ncbi.nlm.nih.gov/entrez/entrezdirect/install-edirect.sh)\""
fi
