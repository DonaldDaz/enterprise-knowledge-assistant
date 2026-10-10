from app.rag import ExtractiveAnswer, HashEmbedding, sections_from_text


def test_markdown_headings_become_citation_sections():
    sections = sections_from_text("# One\n\nFirst sentence.\n\n# Two\n\nSecond sentence.", ".md")
    assert sections == [("One", "First sentence."), ("Two", "Second sentence.")]


def test_embedding_is_repeatable_and_normalized():
    provider = HashEmbedding()
    first = provider.embed("Travel expense reimbursement")
    assert first == provider.embed("Travel expense reimbursement")
    assert abs(sum(value * value for value in first) - 1) < 0.001


def test_answer_quotes_only_evidence():
    evidence = [{"document_id": "one", "title": "Travel Policy", "section": "Accommodation", "content": "The nightly hotel limit is 140 euros.", "similarity": 0.8}]
    answer, citations = ExtractiveAnswer().answer("What is the nightly hotel limit?", evidence)
    assert "140 euros" in answer
    assert citations[0]["quote"] == answer
    assert citations[0]["section"] == "Accommodation"


def test_abstains_if_evidence_does_not_support_question():
    evidence = [{"document_id": "one", "title": "Travel Policy", "section": "Accommodation", "content": "The nightly hotel limit is 140 euros.", "similarity": 0.8}]
    answer, citations = ExtractiveAnswer().answer("What color is the company logo?", evidence)
    assert citations == []
    assert answer.startswith("I can't answer")
