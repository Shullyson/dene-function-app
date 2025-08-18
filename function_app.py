import logging
import os
import json
import requests
import azure.functions as func
import re
import traceback
from typing import List, Dict

logging.basicConfig(level=logging.INFO)
app = func.FunctionApp()

REQUIRED_ENV_VARS = [
    "AI_FOUND_ENDPOINT",
    "AI_FOUND_API_KEY",
    "SEARCH_ENDPOINT",
    "SEARCH_INDEX_NAME",
    "SEARCH_KEY"
]

# Hardcoded URL for the single document
HARDCODED_DOCUMENT_URL = "https://stdeneprojectweu01.blob.core.windows.net/deneproject/wipo-pub-867-23-en-wipo-patent-drafting-manual.pdf?sp=r&st=2025-08-17T14:53:29Z&se=2025-08-26T23:08:29Z&spr=https&sv=2024-11-04&sr=b&sig=p2punFdcvALjB4SjdUHFAGR5ieNYOHG2qt5NRHD5dBI%3D"

def load_system_prompt(path="system_prompt.md") -> str:
    try:
        if not os.path.isabs(path):
            path = os.path.join(os.path.dirname(__file__), path)
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logging.error(f"System prompt file not found at {path}")
        return "System prompt file not found."

def remove_orphan_citations(text: str, valid_numbers: set) -> str:
    return re.sub(r'\[(\d+)\]', lambda m: f"[{m.group(1)}]" if m.group(1) in valid_numbers else "", text)

@app.function_name(name="HttpAskAI")
@app.route(route="ask-ai", auth_level=func.AuthLevel.FUNCTION)
def ask_ai(req: func.HttpRequest) -> func.HttpResponse:
    try:
        req_body = req.get_json()
        message = req_body.get("message")
        chat_history = req_body.get("history", [])

        if not message:
            return _error_response("Missing 'message' in request body", 400)

        # Check for missing environment variables
        missing = [key for key in REQUIRED_ENV_VARS if not os.getenv(key)]
        if missing:
            return _error_response(f"Missing environment variable(s): {missing}", 500)

        # Sanitize chat_history to remove 'id' fields
        sanitized_history = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in chat_history
            if isinstance(msg, dict) and "role" in msg and "content" in msg
        ]

        system_message = {
            "role": "system",
            "content": load_system_prompt()
        }

        messages = [system_message] + sanitized_history + [{"role": "user", "content": message}]

        # Greeting detection before AI call and fallback
        greetings = {"hello", "hi", "hey", "greetings"}
        if message and message.strip().lower() in greetings:
            return func.HttpResponse(
                json.dumps({
                    "answer": "Hello! How can I assist you with the WIPO Patent Drafting Manual or patent-related questions today?",
                    "history": sanitized_history + [
                        {"role": "user", "content": message},
                        {"role": "assistant", "content": "Hello! How can I assist you with the WIPO Patent Drafting Manual or patent-related questions today?"}
                    ],
                    "references": []
                }),
                status_code=200,
                mimetype="application/json"
            )

        ai_response = requests.post(
            os.environ["AI_FOUND_ENDPOINT"],
            headers={
                "api-key": os.environ["AI_FOUND_API_KEY"],
                "Content-Type": "application/json"
            },
            json={
                "messages": messages,
                "temperature": 0.2,
                "top_p": 1.0,
                "data_sources": [
                    {
                        "type": "azure_search",
                        "parameters": {
                            "endpoint": os.environ["SEARCH_ENDPOINT"],
                            "index_name": os.environ["SEARCH_INDEX_NAME"],
                            "semantic_configuration": "rag-dennemeyer-semantic-configuration",
                            "query_type": "semantic",
                            "fields_mapping": {},
                            "in_scope": True,
                            "filter": None,
                            "strictness": 3,
                            "top_n_documents": 5,
                            "authentication": {
                                "type": "api_key",
                                "key": os.environ["SEARCH_KEY"]
                            }
                        }
                    }
                ]
            }
        )

        if ai_response.status_code != 200:
            logging.error(f"AI service request failed with status {ai_response.status_code}: {ai_response.text}")
            return _error_response("AI service request failed", ai_response.status_code, extra={"message": ai_response.text})

        result = ai_response.json()
        assistant_reply = result["choices"][0]["message"]["content"]
        citations = result["choices"][0]["message"].get("context", {}).get("citations", [])

        # Fallback: check confidence score
        confidence = result["choices"][0]["message"].get("confidence", 1.0)
        if confidence < 0.5:
            return func.HttpResponse(
                json.dumps({
                    "answer": "I'm not confident in the answer. Please refine or rephrase your question for better results.",
                    "history": sanitized_history + [
                        {"role": "user", "content": message},
                        {"role": "assistant", "content": "I'm not confident in the answer. Please refine or rephrase your question for better results."}
                    ],
                    "references": []
                }),
                status_code=200,
                mimetype="application/json"
            )

        # Fallback: no citations/retrievals
        if not citations:
            return func.HttpResponse(
                json.dumps({
                    "answer": "No relevant information was found. Please contact sulaiman@test.com for further assistance.",
                    "history": sanitized_history + [
                        {"role": "user", "content": message},
                        {"role": "assistant", "content": "No relevant information was found. Please contact sulaiman@test.com for further assistance."}
                    ],
                    "references": []
                }),
                status_code=200,
                mimetype="application/json"
            )

        # Log citations for debugging
        logging.debug(f"Citations received: {json.dumps(citations, indent=2)}")

        # Deduplicate citations by document (prefer URL, fallback to title)
        unique_docs = []
        doc_key_map = {}  # Maps doc key to its assigned citation number

        def doc_key(doc):
            return (doc.get("url") or "").lower() or doc.get("title", "").lower() or "wipo-patent-drafting-manual"

        for doc in citations:
            key = doc_key(doc)
            if key and key not in doc_key_map:
                doc_key_map[key] = len(unique_docs) + 1  # Citation number starts at 1
                unique_docs.append(doc)

        # Replace citations in the answer text with unique numbers
        def replace_citations(text, citations):
            orig_to_unique = {}
            for idx, doc in enumerate(citations):
                key = doc_key(doc)
                if key in doc_key_map:
                    orig_to_unique[str(idx + 1)] = str(doc_key_map[key])
            def repl(m):
                orig = m.group(1)
                return f"[{orig_to_unique.get(orig, orig)}]"
            return re.sub(r'\[(\d+)\]', repl, text)

        assistant_reply = replace_citations(assistant_reply, citations)

        # Build references array with hardcoded URL and page numbers
        references = []
        for i, doc in enumerate(unique_docs):
            index = i + 1
            title = doc.get("title", "WIPO Patent Drafting Manual")
            # Try multiple field names for page number
            page = doc.get("page") or doc.get("pageNumber") or doc.get("chunk_id")
            url = HARDCODED_DOCUMENT_URL
            if page and isinstance(page, (int, str)) and str(page).isdigit():
                url = f"{HARDCODED_DOCUMENT_URL}#page={page}"
            else:
                logging.warning(f"No valid page number found for citation {index}: {json.dumps(doc, indent=2)}")
            references.append({
                "index": index,
                "title": title,
                "url": url
            })

        # Remove orphan citations after building references
        valid_citation_numbers = {str(ref["index"]) for ref in references}
        assistant_reply = remove_orphan_citations(assistant_reply, valid_citation_numbers)

        # Append reference links to the reply
        assistant_reply = _append_reference_links(assistant_reply, unique_docs)

        return func.HttpResponse(
            json.dumps({
                "answer": assistant_reply,
                "history": sanitized_history + [
                    {"role": "user", "content": message},
                    {"role": "assistant", "content": assistant_reply}
                ],
                "references": references
            }),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.exception("❌ Unhandled exception in ask_ai")
        return _error_response("Unhandled exception", 500, extra={
            "message": str(e),
            "trace": traceback.format_exc()
        })

def _generate_blob_url(doc: Dict) -> str:
    """
    Return the hardcoded document URL with an optional page number fragment.
    """
    page = doc.get("page") or doc.get("pageNumber") or doc.get("chunk_id")
    if page and isinstance(page, (int, str)) and str(page).isdigit():
        return f"{HARDCODED_DOCUMENT_URL}#page={page}"
    return HARDCODED_DOCUMENT_URL

def _append_reference_links(answer: str, docs: List[Dict]) -> str:
    if not docs or not isinstance(docs, list):
        return answer

    # Fix joined citations like [1][2] and [1][2][3]
    answer = re.sub(r'\[(\d+)\]\[(\d+)\]', r'[\1], [\2]', answer)
    answer = re.sub(r'(\[\d+\])(?=\[\d+\])', r'\1, ', answer)

    # Extract used reference numbers
    used_refs = set(re.findall(r'\[(\d+)\]', answer))

    references_section = ""
    for ref in sorted(used_refs, key=lambda x: int(x)):
        idx = int(ref) - 1
        if 0 <= idx < len(docs):
            doc = docs[idx]
            url = _generate_blob_url(doc)
            references_section += f"[{ref}]: {url}\n"
            logging.debug(f"🔗 Citation [{ref}] → {url}")
        else:
            references_section += f"[{ref}]: #\n"
            logging.warning(f"⚠️ Reference index [{ref}] out of bounds")

    return answer.strip() + "\n\n" + references_section.strip() + "\n"

def _error_response(message: str, status_code: int, extra: dict = None) -> func.HttpResponse:
    payload = {"error": message}
    if extra:
        payload.update(extra)
    return func.HttpResponse(
        json.dumps(payload),
        status_code=status_code,
        mimetype="application/json"
    )