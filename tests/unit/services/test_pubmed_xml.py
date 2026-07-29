"""
tests/unit/services/test_pubmed_xml.py
"""

from elib.services.pubmed_xml import parse_first_pubmed_article, parse_pubmed_xml

STRUCTURED_ABSTRACT_XML = """<?xml version="1.0"?>
<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2024//EN" "https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_240101.dtd">
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>11111111</PMID>
      <Article>
        <Journal>
          <Title>Test Journal</Title>
          <ISOAbbreviation>Test J</ISOAbbreviation>
          <JournalIssue>
            <Volume>1</Volume>
            <Issue>2</Issue>
            <PubDate>
              <Year>2021</Year>
              <Month>Mar</Month>
              <Day>15</Day>
            </PubDate>
          </JournalIssue>
        </Journal>
        <ArticleTitle>A Structured Abstract Paper</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND" NlmCategory="BACKGROUND">Background text here.</AbstractText>
          <AbstractText Label="METHODS" NlmCategory="METHODS">Methods text here.</AbstractText>
          <AbstractText Label="RESULTS" NlmCategory="RESULTS">Results text here.</AbstractText>
          <AbstractText Label="CONCLUSIONS" NlmCategory="CONCLUSIONS">Conclusions text here.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author>
            <LastName>Smith</LastName>
            <ForeName>Alice</ForeName>
            <Initials>A</Initials>
          </Author>
          <Author>
            <LastName>Jones</LastName>
            <ForeName>Bob</ForeName>
            <Initials>B</Initials>
          </Author>
        </AuthorList>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="pubmed">11111111</ArticleId>
        <ArticleId IdType="doi">10.1234/test.doi</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
"""


def test_multipart_abstract():
    ref = parse_first_pubmed_article(STRUCTURED_ABSTRACT_XML)
    assert ref is not None
    assert ref.pmid == "11111111"
    assert ref.doi == "10.1234/test.doi"
    assert ref.title == "A Structured Abstract Paper"
    assert len(ref.authors) == 2
    assert ref.authors[0].last_name == "Smith"
    assert ref.journal.title == "Test Journal"
    assert ref.publication_date is not None
    assert ref.publication_date.year == 2021
    assert ref.abstract is not None
    assert "BACKGROUND: Background text here." in ref.abstract
    assert "METHODS: Methods text here." in ref.abstract
    assert "RESULTS: Results text here." in ref.abstract
    assert "CONCLUSIONS: Conclusions text here." in ref.abstract


def test_parse_pubmed_xml_list():
    refs = parse_pubmed_xml(STRUCTURED_ABSTRACT_XML)
    assert len(refs) == 1
