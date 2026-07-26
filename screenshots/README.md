# Screenshots

Two images here are real, captured directly from this repo's code with no
Azure involved:

| File | What it shows |
|---|---|
| `web-ui-landing.png` | `app/api.py`'s `GET /` page, as actually rendered — empty state |
| `web-ui-filled.png` | Same page with a question typed in, before submitting |

Both are honest artifacts: a headless browser hitting the real FastAPI app
running locally. Neither shows a generated answer, because that requires a
live Azure AI Search + Azure OpenAI + Content Safety deployment, which this
sandbox doesn't have access to (see the main README's "Can I run this
myself?" section).

## Suggested screenshots to add

The list below is a checklist for whoever has the real Azure deployment (see
`README.md` → "Deployment Evidence") to fill in. Each row is real evidence a
reviewer can't get from the code alone — pair it with the README section it
backs up. Suggested naming: `NN-short-name.png`, added roughly in the order
below so they read top-to-bottom as one story.

### Deploy — proves the infra actually stands up

| # | Filename | Capture | Backs up |
|---|---|---|---|
| 1 | `01-deploy-whatif.png` | Terminal output of `az deployment group what-if` (Step 1) | README → Deploy |
| 2 | `02-deploy-succeeded.png` | Terminal or Azure Portal showing both deployments (`deploy-rag-poc` + the model-deployments one) as `Succeeded` | README → Deploy, Deployment Evidence |
| 3 | `03-resource-group.png` | Azure Portal resource group view: all three services (`ragcs-poc-search`, `ragcs-poc-aoai`, `ragcs-poc-safety`) present | Deployment Evidence table |
| 4 | `04-private-endpoints.png` | Azure Portal networking blade on any one service — `Public network access: Disabled`, private endpoint listed | Deployment Evidence, Zero Trust claim |
| 5 | `05-rbac-role-assignments.png` | Azure Portal IAM blade showing the `Search Index Data Contributor` / `Cognitive Services OpenAI User` / `Cognitive Services User` role assignments — proves "no API keys" isn't just a README claim | Running the RAG pipeline |

### CI/CD — proves the pipeline is real, not aspirational

| # | Filename | Capture | Backs up |
|---|---|---|---|
| 6 | `06-actions-green.png` | GitHub Actions tab: `deploy.yml`, `python-ci.yml`, `security-scan.yml` all green on a recent run | README badges |
| 7 | `07-security-scan-findings.png` | Security tab / PSRule + Checkov results (clean, or with findings triaged) | Security scanning section |

### The app itself — proves it actually answers questions

| # | Filename | Capture | Backs up |
|---|---|---|---|
| 8 | `08-cli-grounded-answer.png` | Terminal: `python app/query.py "How do I report an outage?"` with a real generated answer | README "Example output" |
| 9 | `09-web-ui-answer.png` | Browser: the web UI after asking a question, showing a real generated answer (the real counterpart to `web-ui-filled.png` here) | Running the web API |
| 10 | `10-content-safety-refusal.png` | CLI or web UI output when a flagged question/answer triggers the refusal message | Content Safety section |
| 11 | `11-out-of-scope-question.png` | A question outside the knowledge base, showing the model decline instead of hallucinate | README "grounding" example |

### Testing — proves the safety net actually runs

| # | Filename | Capture | Backs up |
|---|---|---|---|
| 12 | `12-pytest-passing.png` | Terminal: `pytest` output, all tests green | Testing section |
| 13 | `13-ruff-clean.png` | Terminal: `ruff check app tests`, no findings | Testing section |

Not every row needs its own screenshot if one image can honestly cover two
(e.g. a single Portal screenshot showing both `Succeeded` deployments). The
point isn't hitting 13 files — it's that every claim the README makes about
what's actually deployed and working has a real image backing it, not just
prose.
