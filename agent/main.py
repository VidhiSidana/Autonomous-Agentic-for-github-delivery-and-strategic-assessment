
import sys
import asyncio
import re
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from llm import LocalLLM
from planner import AgentPlanner
from memory.memory import EngineeringMemory
from mcp_client import call_mcp_tool


class UnifiedEngineeringAgent:

    def __init__(self):
        self.llm = LocalLLM()
        self.planner = AgentPlanner()
        self.memory = EngineeringMemory()

    def process_query(self, user_input):

        category = self.planner.plan(user_input)

        print(f"\n[Agent] Selected category: {category}")

        query = user_input.lower()

        # =====================================
        # MCP TEST SERVER
        # =====================================

        if any(word in query for word in [
            "mcp test",
            "test server",
            "project info"
        ]):

            result = asyncio.run(
                call_mcp_tool(
                    "get_project_info",
                    {},
                    server="test"
                )
            )

            return f"MCP Server Result:\n{result}"

        # =====================================
        # MCP ADDITION TOOL
        # =====================================

        if "add numbers" in query:

            try:
                a = int(input("Enter first number: "))
                b = int(input("Enter second number: "))

                result = asyncio.run(
                    call_mcp_tool(
                        "add_numbers",
                        {"a": a, "b": b},
                        server="test"
                    )
                )

                return f"MCP Addition Result:\n{result}"

            except ValueError:
                return "Please enter valid integer numbers."

        # =====================================
        # ENGINEERING MEMORY
        # =====================================

        if category == "memory":

            if any(word in query for word in [
                "remember",
                "save finding"
            ]):

                title = input("Enter finding title: ")
                content = input("Enter finding details: ")

                return self.memory.save_finding(
                    title,
                    content
                )

            elif "search" in query:

                keyword = input("Enter keyword to search: ")

                findings = self.memory.search_findings(
                    keyword
                )

                if not findings:
                    return f"No findings found for '{keyword}'."

                response = f"\nSearch Results for '{keyword}':\n"

                for finding in findings:
                    response += (
                        f"\nID: {finding[0]}"
                        f"\nTitle: {finding[1]}"
                        f"\nContent: {finding[2]}"
                        f"\nCreated At: {finding[3]}\n"
                    )

                return response

            elif any(word in query for word in [
                "retrieve",
                "recall",
                "show memory",
                "list memory"
            ]):

                findings = self.memory.retrieve_findings()

                if not findings:
                    return "No engineering findings stored yet."

                response = "\nStored Engineering Findings:\n"

                for finding in findings:
                    response += (
                        f"\nID: {finding[0]}"
                        f"\nTitle: {finding[1]}"
                        f"\nContent: {finding[2]}"
                        f"\nCreated At: {finding[3]}\n"
                    )

                return response

            else:
                return "Memory command not recognized."

        # =====================================
        # CODE ANALYSIS MCP SERVER
        # =====================================

        if category == "code_analysis":

            project_root = Path(__file__).resolve().parent.parent

            # ---------------------------------
            # C2: Caller Detection
            # ---------------------------------

            if any(word in query for word in [
                "caller",
                "calls",
                "who calls"
            ]):

                function_name = input(
                    "Enter function name to search: "
                ).strip()

                if not function_name:
                    return "Function name cannot be empty."

                result = asyncio.run(
                    call_mcp_tool(
                        "find_callers",
                        {
                            "directory": str(project_root),
                            "function_name": function_name
                        },
                        server="code"
                    )
                )

                if result.is_error:
                    return "Caller analysis failed."

                return (
                    "Caller Analysis Results:\n\n"
                    + result.structured_content["result"]
                )

            # ---------------------------------
            # C3: Module Relationship Analysis
            # ---------------------------------

            if any(word in query for word in [
                "module",
                "modules",
                "import",
                "imports",
                "depend",
                "dependency",
                "dependencies"
            ]):

                filename = input(
                    "Enter Python filename (e.g. agent/main.py): "
                ).strip()

                if not filename:
                    return "Filename cannot be empty."

                result = asyncio.run(
                    call_mcp_tool(
                        "find_module_relationships",
                        {
                            "directory": str(project_root),
                            "filename": filename
                        },
                        server="code"
                    )
                )

                if result.is_error:
                    return "Module analysis failed."

                return (
                    "Module Relationship Results:\n\n"
                    + result.structured_content["result"]
                )

            # ---------------------------------
            # C1: Function Detection
            # ---------------------------------

            result = asyncio.run(
                call_mcp_tool(
                    "find_functions",
                    {
                        "directory": str(project_root)
                    },
                    server="code"
                )
            )

            if result.is_error:
                return "Code analysis failed."

            return (
                "Code Analysis Results:\n\n"
                + result.structured_content["result"]
            )

        # =====================================
        # BINARY ANALYSIS MCP SERVER
        # =====================================

        if category == "binary_analysis":

            binary_path = input(
                "Enter binary file path: "
            ).strip().strip('"')

            if not binary_path:
                return "Binary file path cannot be empty."

            # ---------------------------------
            # B2: Binary Disassembly
            # ---------------------------------

            if any(word in query for word in [
                "disassemble",
                "disassembly",
                "assembly",
                "instructions",
                "instruction"
            ]):

                result = asyncio.run(
                    call_mcp_tool(
                        "disassemble_binary",
                        {
                            "binary_path": binary_path,
                            "max_instructions": 50
                        },
                        server="binary"
                    )
                )

            # ---------------------------------
            # B1: Binary Function Discovery
            # ---------------------------------

            elif any(word in query for word in [
                "binary function",
                "binary functions",
                "exported function",
                "exported functions",
                "list functions"
            ]):

                result = asyncio.run(
                    call_mcp_tool(
                        "find_binary_functions",
                        {
                            "binary_path": binary_path
                        },
                        server="binary"
                    )
                )

            # ---------------------------------
            # Binary Information
            # ---------------------------------

            else:

                result = asyncio.run(
                    call_mcp_tool(
                        "analyze_binary",
                        {
                            "binary_path": binary_path
                        },
                        server="binary"
                    )
                )

            if result.is_error:
                return "Binary analysis failed."

            return (
                "Binary Analysis Results:\n\n"
                + result.structured_content["result"]
            )


        # =====================================
        # GENERAL LLM RESPONSE
        # =====================================

        prompt = f"""
You are a Unified Engineering Agent.

Your query category is: {category}

User query: {user_input}

Answer clearly and accurately.

Do not claim to have analyzed code or binaries
unless actual analysis tools have been used.
"""

        return self.llm.generate_response(prompt)


# =====================================
# MAIN PROGRAM
# =====================================

if __name__ == "__main__":

    agent = UnifiedEngineeringAgent()

    print("====================================")
    print(" Unified Engineering Agent")
    print("====================================")

    print("Type 'exit' to stop.\n")

    while True:

        user_input = input("You: ")

        if user_input.lower() == "exit":
            print("Agent stopped.")
            break

        response = agent.process_query(user_input)

        print("\nAgent:", response)

        print("-" * 50)
