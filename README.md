
# eLib (electronic Library)

elib is an *Electronic Library Management System* that provides a command-line interface (CLI) for managing and searching your library of documents. This README summarizes the available commands and provides examples for searching terms like ~heart rate~, ~growth hormone~, and ~locomotion~.

*** Features
+ Process PDF documents and extract metadata.
+ Search your local library, PubMed, or both.
+ Display library statistics.
+ Rebuild the full-text search index.

*** Installation
To use the CLI, ensure you have Python installed and the required dependencies. Then, run the script using:

#+BEGIN_SRC shell
python src/elib/cli.py
#+END_SRC

*** Commands

**** General Options
+ ~-v/--verbose~: Increase verbosity (e.g., ~-v~ for INFO, ~-vv~ for DEBUG).
+ ~-q/--quiet~: Quiet mode (only show ERROR and CRITICAL messages).
+ ~--log-level~: Explicitly set the log level (e.g., DEBUG, INFO).

**** ~process~
Processes PDF files in a specified directory.

+ **Usage**:
  #+BEGIN_SRC shell
  elib process <source_dir> [--target-dir <target_dir>] [--use-cli]
  #+END_SRC

+ **Options**:
  - ~<source_dir>~: Directory containing PDFs to process.
  - ~--target-dir~: Directory to save processed files (optional).
  - ~--use-cli~: Use CLI tools instead of HTTP API.

+ **Example**:
  #+BEGIN_SRC shell
  elib process ./pdfs --target-dir ./processed
  #+END_SRC

**** ~search~
Searches your local library, PubMed, or both.

+ **Usage**:
  #+BEGIN_SRC shell
  elib search [OPTIONS]
  #+END_SRC

+ **Options**:
  - ~--text~: Full-text search in title, abstract, and keywords.
  - ~--author~: Filter by author name.
  - ~--year-from~ and ~--year-to~: Filter by publication year range.
  - ~--journal~: Filter by journal name.
  - ~--doi~: Filter by DOI.
  - ~--pmid~: Filter by PMID.
  - ~--keyword~: Add keyword filters (repeatable).
  - ~--sort-by~: Sort results by relevance, year, title, or added date.
  - ~--sort-order~: Sort order (ascending or descending).
  - ~--limit~: Limit the number of results (default: 20).
  - ~--offset~: Offset for pagination.
  - ~--source~: Search source (local, pubmed, or both).
  - ~--json~: Return results as JSON.

+ **Examples**:
  1. Search for ~heart rate~ in the local library:
     #+BEGIN_SRC shell
     elib search --text "heart rate"
     #+END_SRC

  2. Search for ~growth hormone~ in PubMed:
     #+BEGIN_SRC shell
     elib search --text "growth hormone" --source pubmed
     #+END_SRC

  3. Search for ~locomotion~ in both local library and PubMed:
     #+BEGIN_SRC shell
     elib search --text "locomotion" --source both
     #+END_SRC

**** ~stats~
Displays statistics about your library.

+ **Usage**:
  #+BEGIN_SRC shell
  elib stats
  #+END_SRC

+ **Example**:
  #+BEGIN_SRC shell
  elib stats
  #+END_SRC

  _Output_:
  #+BEGIN_QUOTE
  Total documents: 120
  Synced to S3: 80

  Documents by year:
    2023: 30
    2022: 25
    2021: 20
  #+END_QUOTE

**** ~rebuild_index~
Rebuilds the full-text search (FTS) index for your library.

+ **Usage**:
  #+BEGIN_SRC shell
  elib rebuild_index
  #+END_SRC

+ **Example**:
  #+BEGIN_SRC shell
  elib rebuild_index
  #+END_SRC

  _Output_:
  #+BEGIN_QUOTE
  Rebuilding FTS index...
  ✓ Rebuilt FTS index for 120 documents
  #+END_QUOTE

*** Notes
+ Ensure your configuration file is properly set up for database paths and PubMed API keys.
+ Use the ~--json~ flag for machine-readable output when integrating with other tools.

*** License
elib is licensed under the MIT License.
