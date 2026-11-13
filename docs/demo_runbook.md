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

## 5. Evidence captured and still required

### Captured during the 2026-11-13 live binary-memory demonstration

- [x] Startup banner showed Ollama model `qwen2.5:1.5b` online.
- [x] New CLI session ID: `session_e20c754f`.
- [x] Retrieved a verified finding from prior persistent memory without re-running binary analysis.
- [x] Retrieved memory record ID: `8`; category: `binary_finding`; status: `VERIFIED`.
- [x] Exact retrieved values: machine `0x8664`; architecture `IMAGE_FILE_MACHINE_AMD64 (x64 64-bit)`; entry point RVA `0x1000`; image base `0x140000000`; section count `1`; section name `.text`.
- [x] Prior source record was saved in session `session_093de75f`; retrieval occurred in distinct session `session_e20c754f`.
- [x] Focused regression command `python -m unittest tests.test_binary_memory_retrieval -v` passed 2 tests.

### Still to capture for the full presentation run

- [ ] Screenshots or recording of startup and retrieval transcript.
- [ ] Code-comprehension demonstration output and evidence.
- [ ] Live binary-analysis output from the demo sequence (the memory retrieval above is a separate validation).
- [ ] Clean shutdown transcript.
- [ ] Exact Git commit SHA used for the recorded demonstration.

## 6. Troubleshooting notes

- **Ollama offline:** Start the Ollama service and verify the model with `ollama list`.
- **Model missing:** Pull the exact model configured in `.env`.
- **Code graph unavailable:** Verify the `codebase-memory-mcp` executable and index; explain when AST fallback is used.
- **REA unavailable:** Check Node.js and REA/Ghidra prerequisites. Report fallback or prerequisite-blocked status accurately.
- **Binary request denied:** Confirm the sample is inside the configured `BINARY_ALLOWED_DIRS`; do not weaken the allowlist to make a demo pass.
- **Slow inference:** Allow for local model latency and avoid changing timeout settings without documenting the change.

## 7. Demonstration record

### Completed focused cross-session binary-memory validation

| Field | Actual value |
|---|---|
| Date | 2026-11-13 |
| Repository branch | `main` |
| Repository commit at validation start | `2fa32db5` (short SHA observed on GitHub before this documentation update) |
| OS / shell | Windows, PowerShell |
| Python version | 3.11.9 |
| Ollama model tag | `qwen2.5:1.5b` |
| Source memory session | `session_093de75f` |
| Retrieval session | `session_e20c754f` |
| Binary sample identifier | `sample_authorized.exe` |
| Source memory record | `8` (`binary_finding`, `VERIFIED`) |
| Demo outcome | Passed; all seven requested fields matched the stored record |
| Evidence location | CLI transcript in the project validation conversation; no screenshot/recording file captured yet |

The source finding was saved at `2026-11-13T09:37:53.248953+00:00` UTC. This is the memory-record creation timestamp, not a claimed timestamp for the later retrieval session.

**Scope note:** This records the successful focused cross-session binary-memory check. It does not claim that every code, binary, confirmation-flow and clean-install presentation scenario has been recorded.
