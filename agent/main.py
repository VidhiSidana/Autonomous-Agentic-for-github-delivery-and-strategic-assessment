
import sys
from pathlib import Path

# Allow importing the memory module from the project folder
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from llm import LocalLLM
from planner import AgentPlanner
from memory.memory import EngineeringMemory


class UnifiedEngineeringAgent:

    def __init__(self):
        self.llm = LocalLLM()
        self.planner = AgentPlanner()
        self.memory = EngineeringMemory()

   
    def process_query(self, user_input):

        category = self.planner.plan(user_input)

        print(f"\n[Agent] Selected category: {category}")

        # Handle memory operations
        if category == "memory":

            query = user_input.lower()

            # Save a finding
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

            # Search memory
            elif "search" in query:

                keyword = input("Enter keyword to search: ")

                findings = self.memory.search_findings(keyword)

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

            # Retrieve all findings
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

        # Handle general questions using local LLM
        prompt = f"""
You are a Unified Engineering Agent.

Your query category is: {category}

User query: {user_input}

Answer clearly and accurately.
Do not claim to have analyzed code or binaries
unless actual analysis tools have been used.
"""

        return self.llm.generate_response(prompt)


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
