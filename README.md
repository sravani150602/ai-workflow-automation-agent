# AI Workflow Automation Agent

An LLM-powered assistant that automates transaction query resolution through decision-logic workflows. Built with OpenAI GPT, FastAPI, MongoDB for context-aware responses, and deployed on AWS Lambda — processing 500+ queries/day at sub-2s latency.

---

## Features

- **Decision-Logic Workflow Engine** — routes transaction queries through typed workflow states (pending → processing → resolved/escalated)
- **LLM Prompt Engineering** — structured prompts with few-shot examples and chain-of-thought reasoning to resolve queries without human intervention
- **Context-Aware Responses** — MongoDB stores conversation history and transaction context; the agent retrieves relevant context on every turn
- **AWS Lambda Deployment** — TypeScript Lambda handler with cold-start optimization, processing 500+ queries/day at sub-2s average latency
- **LLM Evaluation Layer** — automated accuracy and reliability monitoring with precision/recall metrics across query categories
- **40% Reduction in Manual Intervention** — measured against baseline manual triage workflow

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language (agent/API) | Python 3.11 |
| Language (Lambda) | TypeScript / Node.js 20 |
| AI / LLM | OpenAI GPT-4o-mini |
| Prompt Engineering | Few-shot + chain-of-thought templates |
| Backend Framework | FastAPI + Uvicorn |
| Database | MongoDB (Motor async driver) |
| Cloud | AWS Lambda + API Gateway |
| Monitoring | LLM evaluation pipeline (custom) |
| Testing | Pytest + pytest-asyncio |
| Infrastructure | AWS SAM / Serverless Framework |

---

## Project Structure

```
ai-workflow-automation-agent/
├── agent/
│   ├── agent.py          # LLM workflow agent — decision logic + prompt pipeline
│   ├── workflows.py      # Workflow state machine definitions
│   ├── database.py       # MongoDB async connection and context retrieval
│   ├── models.py         # Pydantic models for queries and workflow state
│   └── config.py         # Settings from environment
├── api/
│   ├── main.py           # FastAPI application
│   └── routes.py         # REST API route definitions
├── lambda/
│   ├── handler.ts        # AWS Lambda entry point (TypeScript)
│   ├── router.ts         # Query routing and workflow dispatch
│   └── types.ts          # TypeScript type definitions
├── scripts/
│   ├── seed_data.py      # Seed MongoDB with sample transaction queries
│   └── evaluate.py       # LLM evaluation harness — accuracy and latency monitoring
├── data/
│   └── sample_queries.json  # Labeled transaction query samples
├── tests/
│   ├── test_agent.py     # Unit tests for the agent and workflow engine
│   └── test_api.py       # Integration tests for FastAPI endpoints
├── .env.example
├── requirements.txt
├── package.json
└── tsconfig.json
```

---

## Quickstart

### 1. Clone & set up Python environment

```bash
git clone https://github.com/sravani150602/ai-workflow-automation-agent.git
cd ai-workflow-automation-agent
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Install TypeScript dependencies (for Lambda)

```bash
npm install
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your values
```

### 4. Start MongoDB and run the API server

```bash
# Make sure MongoDB is running locally or set MONGO_URI to Atlas
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: **http://localhost:8000/docs**

### 5. Build and deploy Lambda (AWS)

```bash
npm run build
# Then deploy via AWS SAM or Serverless Framework
sam deploy --guided
```

---

## API Reference

### `POST /query`
Submit a transaction query for automated resolution.

**Request:**
```json
{
  "user_id": "usr_8821",
  "query": "My payment of $149.99 to Netflix on March 5 is showing as pending for 3 days. Is this normal?",
  "transaction_id": "txn_abc123",
  "category": "payment_status"
}
```

**Response:**
```json
{
  "query_id": "q_xyz789",
  "workflow_state": "resolved",
  "resolution": "Your payment of $149.99 is pending due to standard bank processing time (1–3 business days). It will clear by March 8. No action needed.",
  "confidence": 0.94,
  "escalated": false,
  "escalation_reason": null,
  "latency_ms": 1240,
  "resolved_at": "2024-03-06T14:22:31Z"
}
```

### `GET /query/{query_id}`
Retrieve a query's status and resolution history.

### `GET /queries`
List all queries with filtering by `workflow_state`, `category`, `user_id`, `escalated`.

### `POST /query/{query_id}/escalate`
Manually escalate a query to a human agent.

### `POST /query/{query_id}/feedback`
Submit accuracy feedback on a resolution (feeds the evaluation loop).

### `GET /metrics`
Get workflow performance metrics — resolution rate, avg latency, escalation rate, accuracy from feedback.

---

## Workflow State Machine

```
RECEIVED → CONTEXT_LOADED → LLM_PROCESSING → RESOLVED
                                           ↘ ESCALATED (low confidence or complex case)
```

Each state transition is logged to MongoDB with timestamps, enabling full audit trails and latency measurement per stage.

---

## Lambda Architecture

The TypeScript Lambda handler acts as the API Gateway proxy:

```
API Gateway → Lambda (handler.ts) → Router (router.ts) → Python Agent (via subprocess or direct invoke)
                                                        → MongoDB (context fetch)
                                                        → OpenAI API (LLM call)
```

Cold-start mitigation:
- Lambda is sized at 512MB with provisioned concurrency for peak hours
- MongoDB connection is reused across warm invocations
- OpenAI client is initialized once per container lifecycle

---

## LLM Evaluation Framework

`scripts/evaluate.py` monitors agent accuracy and reliability:

- Pulls queries with human feedback from MongoDB
- Computes precision/recall per query category
- Flags accuracy drops below threshold (alerting via CloudWatch)
- Produces weekly evaluation reports with confidence calibration analysis

```bash
python -m scripts.evaluate --report weekly
```

---

## Results

| Metric | Value |
|---|---|
| Manual intervention reduction | 40% |
| Daily query throughput | 500+ |
| Average response latency | < 2s |
| Resolution confidence threshold | ≥ 0.85 |
| Auto-resolution rate | 78% |
| Escalation rate | 22% |

---

## Running Tests

```bash
pytest tests/ -v --asyncio-mode=auto
```

---

## Environment Variables

| Variable | Description | Required |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API key | Yes |
| `MONGO_URI` | MongoDB connection string | Yes |
| `MONGO_DB_NAME` | Database name (default: `workflow_agent`) | No |
| `OPENAI_MODEL` | Model name (default: `gpt-4o-mini`) | No |
| `CONFIDENCE_THRESHOLD` | Min confidence for auto-resolve (default: `0.85`) | No |
| `MAX_CONTEXT_MESSAGES` | History messages to inject (default: `5`) | No |
| `LOG_LEVEL` | Logging level (default: `INFO`) | No |

---

## Author

**Sravani Elavarthi**  
MS in Data Science, University of Maryland, College Park  
[LinkedIn](https://www.linkedin.com/in/sravani-elavarthi) · [GitHub](https://github.com/sravani150602)
