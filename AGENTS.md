# Agentic Extensions for elib

## Vision
Extend elib to support agentic workflows for paper management: summarization, relevance finding, literature synthesis, etc.

## Current Hooks
- Existing models/services for documents, references, NCBI integration.
- Search and ingestion pipelines as foundations for RAG.

## Planned Features
1. RAG pipelines for querying papers.
2. LLM agents for tasks like "summarize this paper" or "find related references".
3. Tool calling integration (DB query, PDF extraction, web lookup).
4. Memory/persistence for conversations.

## Tech Choices
- LlamaIndex or LangGraph for orchestration.
- Local LLMs (Ollama, llama.cpp) or API (Groq, OpenAI).
- Vector store integration (Chroma).

## Implementation Phases
See prioritized plan in main response.

## Guidelines
- Keep local-first, privacy-focused.
- Modular: agents as optional layer.
