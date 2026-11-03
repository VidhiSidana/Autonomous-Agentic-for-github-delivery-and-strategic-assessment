
class AgentPlanner:

    def plan(self, user_input):

        query = user_input.lower()

        # Code analysis requests
        if any(word in query for word in [
            "function",
            "code",
            "caller",
            "callers",
            "source code",
            "module"
        ]):
            return "code_analysis"

        # Binary analysis requests
        elif any(word in query for word in [
            "binary",
            "executable",
            "decompile",
            "assembly",
            "disassembly"
        ]):
            return "binary_analysis"

        # Memory requests
        elif any(word in query for word in [
            "remember",
            "save finding",
            "retrieve",
            "recall",
            "memory"
        ]):
            return "memory"

        # General requests
        else:
            return "general"


if __name__ == "__main__":

    planner = AgentPlanner()

    test_queries = [
        "Find the callers of main function",
        "Inspect this binary executable",
        "Remember this engineering finding",
        "Explain what MCP means"
    ]

    for query in test_queries:

        category = planner.plan(query)

        print(f"Query: {query}")
        print(f"Category: {category}")
        print("-" * 40)
