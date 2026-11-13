# Samsung PRISM — Live Demonstration Runbook

## 1. Objective

Demonstrate the existing Unified Local Engineering Agent through a short, reproducible CLI session covering code comprehension, static binary investigation, persistent memory and cross-session retrieval.

This is a runbook, not evidence that a demonstration has already been performed. Record the actual outputs, session IDs and screenshots during the live run.

## 2. Environment preparation

Use a clean checkout of the repository and a supported Python 3.11 environment.

From Windows PowerShell:

```powershell
git clone https://github.com/VidhiSidana/Autonomous-Agentic-for-github-delivery-and-strategic-assessment.git
cd Autonomous-Agentic-for-github-delivery-and-strategic-assessment

python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

Copy-Item .env.example .env
```

Install/start Ollama separately, then pull the configured model:

```powershell
ollama pull qwen2.5:1.5b
ollama list
```

Review `.env` and set `BINARY_ALLOWED_DIRS` to a dedicated folder containing only authorised test samples. Do not use a production binary or a file you are not authorised to inspect.

Check that the configured MCP dependencies are available. The repository configuration includes the Python fallback and binary servers, the code graph server, and an REA server launched through `npx`. The code graph executable and REA prerequisites may require separate installation; confirm their availability before the presentation.

## 3. Start the agent

```powershell
python agent/main.py
```

At startup, record:
- The displayed model and its availability status.
- The generated session ID.
- The repository revision used for the demonstration.

## 4. Demonstration sequence

Use the following sequence. Exact wording can be adapted to the repository being analysed.

### Demo A — Code comprehension

Example query:

```text
Find functions in this codebase.
```

Then:

```text
Who calls process_query?
```

Show the returned function/symbol evidence and file references. If a code graph index is unavailable, explain that the configured AST fallback is being used rather than implying graph results.

### Demo B — Static binary investigation

Choose a harmless, authorised PE sample placed inside the configured allowlist directory. Ask:

```text
Analyze binary <absolute-path-to-authorised-sample.exe> and identify its architecture.
```

If supported by the sample, follow with a section or import-table query.

Explain that the implementation performs static inspection (for example, PE parsing and disassembly) and does not execute the target binary. Show a policy denial for a deliberately out-of-allowlist path only if the test is safe and approved.

### Demo C — Persistent engineering memory

Use a verifiable finding from the repository or a deliberately labelled demonstration fact. Example:

```text
Remember this finding: The project uses SQLite for persistent engineering memory. This is verified.
```

Do not label a claim VERIFIED unless its evidence has actually been checked. If the agent proposes a finding, show the pending queue:

```text
/pending
```

Where the workflow returns a pending finding, use its actual ID:

```text
/confirm <id>
```

Only confirm a fact after reviewing its evidence. Alternatively, demonstrate `/reject <id> <reason>` for an unsupported proposal.

### Demo D — Cross-session retrieval

1. Exit the first CLI session using `exit`.
2. Start the CLI again:

```powershell
python agent/main.py
```

3. Ask a memory query that targets the exact finding saved in Demo C:

```text
Search memory for the SQLite engineering-memory finding from the previous session.
```

4. Show the retrieved finding and its verification status/provenance when returned.

Record both session IDs and the actual retrieval result. This is the most important demonstration of persistent engineering memory.

## 5. Evidence to capture

- [ ] Startup banner with model availability and first session ID.
- [ ] Code-analysis answer with file/symbol evidence.
- [ ] Binary-analysis answer using the authorised sample path.
- [ ] Pending/confirmed/rejected finding state, where applicable.
- [ ] First session exit.
- [ ] Second startup with a different session ID.
- [ ] Retrieved prior-session finding.
- [ ] Clean shutdown message.
- [ ] Repository commit SHA and date of the demonstration.

## 6. Troubleshooting notes

- **Ollama offline:** Start the Ollama service and verify the model with `ollama list`.
- **Model missing:** Pull the exact model configured in `.env`.
- **Code graph unavailable:** Verify the `codebase-memory-mcp` executable and index; explain when AST fallback is used.
- **REA unavailable:** Check Node.js and REA/Ghidra prerequisites. Report fallback or prerequisite-blocked status accurately.
- **Binary request denied:** Confirm the sample is inside the configured `BINARY_ALLOWED_DIRS`; do not weaken the allowlist to make a demo pass.
- **Slow inference:** Allow for local model latency and avoid changing timeout settings without documenting the change.

## 7. Demonstration record

Complete this section only after the live demonstration:

| Field | Actual value |
|---|---|
| Date/time and timezone | To be recorded |
| Git commit SHA | To be recorded |
| OS and Python version | To be recorded |
| Ollama model tag | To be recorded |
| Session 1 ID | To be recorded |
| Session 2 ID | To be recorded |
| Binary sample identifier | To be recorded (do not include restricted samples) |
| Demo outcome | To be recorded |
| Evidence location | To be recorded |

**Do not mark this demonstration complete until the evidence above has been captured.**
