
# Dennemeyer Azure Functions App

This project is part of the Dennemeyer Exercise and provides a professional, serverless Azure Functions application for querying the WIPO Patent Drafting Manual using AI and Azure Cognitive Search.

## Overview

- **Technology:** Python 3.10, Azure Functions v4
- **Purpose:** Natural language querying of patent documents with smart citations
- **AI:** Azure OpenAI (GPT-4.1) integrated with Azure Cognitive Search
- **Authentication:** Managed Identity (Azure DefaultAzureCredential)
- **Storage:** Azure Blob Storage

## Features

1. **AI-Powered Document Query**
  - Endpoint: `/ask-ai` (HTTP Trigger)
  - Query the WIPO Patent Drafting Manual using natural language
  - Returns answers with numbered citations and direct links to source pages
  - Maintains chat history for context

2. **Secure & Scalable**
  - API keys and credentials stored securely
  - Function-level authentication for endpoints

## Quick Start

1. **Install Prerequisites**
  - Python 3.10+
  - Azure Functions Core Tools
  - Azure subscription with Functions, Blob Storage, Cognitive Search, and OpenAI

2. **Install Python Dependencies**
  ```bash
  pip install -r requirements.txt
  ```

3. **Configure Environment Variables**
  - Edit `local.settings.json` with your Azure resource details:
    - `FUNCTIONS_WORKER_RUNTIME=python`
    - `AzureWebJobsStorage=<connection string>`
    - `AI_FOUND_ENDPOINT=<OpenAI endpoint>`
    - `AI_FOUND_API_KEY=<OpenAI API key>`
    - `SEARCH_ENDPOINT=<Cognitive Search endpoint>`
    - `SEARCH_INDEX_NAME=<Search index name>`
    - `SEARCH_KEY=<Search API key>`

4. **Run Locally**
  ```bash
  func start
  ```

## API Usage

**POST /api/ask-ai**

Request:
```json
{
  "message": "What are the requirements for patentability?",
  "history": [
   { "role": "user", "content": "Previous question" },
   { "role": "assistant", "content": "Previous response" }
  ]
}
```

Response:
```json
{
  "answer": "A patent must meet three core legal requirements: novelty, inventive step, and industrial application [1].",
  "history": [ ... ],
  "references": [
   { "index": 1, "url": "https://...#page=12" }
  ]
}
```

## Project Structure

```
dennemeyer-function/
├── function_app.py        # Main Azure Functions app
├── requirements.txt       # Python dependencies
├── host.json              # Functions host config
├── local.settings.json    # Local environment config
├── system_prompt.md       # System prompt for AI
└── README.md              # Project documentation
```

## Deployment

Publish to Azure:
```bash
func azure functionapp publish <function-app-name>
```

## Troubleshooting

- Check Azure Function logs for errors
- Verify environment variables and Azure resource access
- Monitor Azure service health for dependencies

## References & Documentation

- [Azure Functions Python Guide](https://docs.microsoft.com/en-us/azure/azure-functions/functions-reference-python)
- [Azure Cognitive Search REST API](https://docs.microsoft.com/en-us/rest/api/searchservice/)
- [Azure OpenAI Service](https://docs.microsoft.com/en-us/azure/cognitive-services/openai/)
- [Azure Blob Storage Python SDK](https://docs.microsoft.com/en-us/azure/storage/blobs/storage-quickstart-blobs-python)

