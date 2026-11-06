# Samsung PRISM — Unified Local-LLM Engineering Agent

A local AI-powered engineering assistant for **source-code comprehension, binary investigation, and persistent engineering memory**.

The project combines a locally hosted Large Language Model (LLM), Model Context Protocol (MCP) tools, code and binary analysis capabilities, and SQLite-based memory to support evidence-backed engineering investigations.

---

## Overview

The Unified Engineering Agent is designed to help developers understand unfamiliar codebases, investigate binary files, and retain useful engineering findings across sessions.

Unlike cloud-based AI assistants, this project uses a locally hosted LLM through Ollama, supporting offline-oriented workflows and local control over project data.

### Key Features

- **Local LLM integration:** Uses Ollama to run language models locally.
- **Code comprehension:** Analyzes source files, functions, imports, and relationships.
- **Binary investigation:** Supports static analysis of Windows PE files and DLLs.
- **MCP integration:** Connects the agent with specialized engineering tools.
- **Persistent engineering memory:** Stores and retrieves findings using SQLite.
- **Evidence-backed responses:** Provides relevant file paths, function names, and line references when available.
- **Benchmarking and testing:** Includes automated tests and evaluation utilities.

---

## Architecture

```text
                         User
                          |
                          v
                 Engineering Agent
                          |
                          v
                    Orchestrator
                          |
             +------------+------------+
             |            |            |
             v            v            v
          Local LLM    MCP Tools    Engineering
          (Ollama)                    Memory
             |            |            |
             v            v            v
         Reasoning    Code and       SQLite
         and Planning Binary         Storage
                      Analysis
             |
             v
       Evidence Aggregation
             |
             v
      Engineering Response
```

### Architecture Components

| Component | Responsibility |
|---|---|
| Engineering Agent | Accepts user queries and coordinates processing |
| Orchestrator | Manages task execution and tool interactions |
| Local LLM | Supports reasoning, planning, and response generation |
| MCP Client | Communicates with engineering analysis tools |
| Code Analysis | Examines source code and relationships |
| Binary Analysis | Investigates supported binary files |
| Engineering Memory | Stores and retrieves persistent findings |
| Evidence Aggregation | Organizes tool results into structured evidence |

---

## Technology Stack

| Technology | Purpose |
|---|---|
| Python | Core agent implementation |
| Ollama | Local LLM execution |
| Qwen 2.5 1.5B | Default local model |
| Model Context Protocol (MCP) | Tool integration |
| SQLite | Persistent engineering memory |
| `pefile` | Windows PE file analysis |
| Capstone | Disassembly support |
| `unittest` | Automated testing |
| Git and GitHub | Version control and collaboration |

---

## Project Structure

```text
Autonomous-Agentic-for-github-delivery-and-strategic-assessment/
│
├── agent/
│   ├── main.py
│   ├── llm.py
│   ├── planner.py
│   ├── mcp_client.py
│   └── orchestrator.py
│
├── code_analysis/
│
├── binary_analysis/
│
├── mcp_server/
│
├── memory/
│   ├── memory.py
│   └── session_manager.py
│
├── benchmarks/
│   └── benchmark_runner.py
│
├── tests/
│
├── docs/
│
├── requirements.txt
├── README.md
└── .gitignore
```

*Note: Directory contents may evolve as development progresses.*

---

## Getting Started

### Prerequisites

Install the following before running the project:

- Python 3.11 or compatible version
- Git
- Ollama
- A supported local LLM

### 1. Clone the Repository

```powershell
git clone https://github.com/VidhiSidana/Autonomous-Agentic-for-github-delivery-and-strategic-assessment.git
```

Navigate to the project directory:

```powershell
cd Autonomous-Agentic-for-github-delivery-and-strategic-assessment
```

### 2. Create a Virtual Environment

```powershell
python -m venv .venv
```

Activate it:

```powershell
.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Install and Start Ollama

Download Ollama from:

https://ollama.com/

Pull the configured model:

```powershell
ollama pull qwen2.5:1.5b
```

Verify the installation:

```powershell
ollama --version
```

Ensure Ollama is running before starting the agent.

### 5. Run the Agent

```powershell
python agent/main.py
```

Follow the prompts to interact with the engineering assistant.

---

## Example Use Cases

### Source-Code Investigation

Ask questions about functions, modules, or code relationships.

Example:

```text
Who calls process_query?
```

The agent can use code-analysis tools to identify relevant function references and provide supporting source information.

### Binary Investigation

Investigate supported binary files to examine executable structure and related information.

The available analysis depends on the file format and the implemented binary-analysis tools.

### Persistent Engineering Memory

Save and retrieve useful findings across engineering sessions.

Example workflow:

```text
Investigate a function
        |
        v
Save the finding
        |
        v
Retrieve it in a later session
```

Persistent memory is intended to reduce repeated investigation and preserve useful engineering knowledge.

---

## Testing

The project includes automated tests for agent functionality, MCP interactions, memory, policy enforcement, and benchmark utilities.

Run the complete test suite:

```powershell
python -m unittest discover -s tests -v
```

### Latest Recorded Test Results

| Metric | Result |
|---|---:|
| Total tests | 60 |
| Passed | 58 |
| Skipped | 2 |
| Failed | 0 |
| Errors | 0 |

The two skipped tests involve optional benchmark integration and a Windows symlink test requiring additional permissions or Developer Mode.

**Note:** These results represent the latest recorded test run and may change as development continues.

---

## Benchmarking and Model Evaluation

The project includes benchmark utilities for evaluating agent performance and local LLM behavior.

Previously recorded model evaluation:

| Model | Tool-Call Accuracy | Valid JSON | Synthesis Score |
|---|---:|---:|---:|
| Qwen 2.5 1.5B | 78.6% | 100% | 33.3% |
| Phi 3.5 | 64.3% | 100% | 66.7% |
| Llama 3.1 8B | 78.6% | 100% | 66.7% |
| Mistral Nemo 12B | Not tested | Not tested | Not tested |

These results are preliminary and depend on the evaluation dataset, prompts, and benchmark implementation. They should not be interpreted as general model rankings.

---

## Development Progress

### Milestone 1 — Core Agent Foundation

The initial foundation includes:

- Local LLM integration
- Agent planning and orchestration
- MCP tool communication
- Source-code analysis foundation
- Persistent engineering memory
- Initial testing infrastructure

### Milestone 2 — Reliability and Engineering Capabilities

Current development focuses on:

- Improving orchestration reliability
- Strengthening evidence aggregation
- Expanding memory functionality
- Improving MCP error handling
- Benchmarking and test coverage
- Refining engineering workflows

**Milestone 2 is still under development.** Features and completion status may change as testing and implementation continue.

---

## Security and Privacy

The project is designed around local execution and engineering-focused analysis.

Important considerations:

- The LLM runs locally through Ollama.
- Engineering memory is stored locally using SQLite.
- Binary analysis should be performed on files you are authorized to investigate.
- Untrusted source code and binaries should be analyzed in an isolated environment.
- Local execution does not automatically guarantee complete security or privacy; review dependencies, permissions, and tool behavior before use.

---

## Current Limitations

- Local model performance depends on available hardware and model size.
- Small models may struggle with complex reasoning and multi-step tool workflows.
- Binary analysis capabilities depend on supported formats and implemented tools.
- MCP session cleanup and asynchronous behavior continue to require refinement.
- Some optional integration tests may be skipped depending on the environment.
- Evidence quality depends on the accuracy and completeness of analysis tools.

---

## Future Scope

Potential improvements include:

- More advanced source-code dependency analysis
- Expanded binary-analysis capabilities
- Improved evidence verification
- More reliable multi-step orchestration
- Enhanced persistent engineering memory
- Additional local LLM evaluation
- Security policies and audit logging
- Improved user interface and developer experience

## Project Repository

[Autonomous Agentic for GitHub Delivery and Strategic Assessment](https://github.com/VidhiSidana/Autonomous-Agentic-for-github-delivery-and-strategic-assessment)

*Developed as part of the Samsung PRISM engineering project.*
- Vidhi Sidana — GitHub: @VidhiSidana
- Chintan Sood — GitHub: @chintansood