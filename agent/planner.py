
class AgentPlanner:

    def plan(self, user_input):

        query = user_input.lower()

        # Memory-related queries
        memory_keywords = [
            "remember",
            "save finding",
            "retrieve",
            "recall",
            "memory",
            "search finding"
        ]

        if any(word in query for word in memory_keywords):
            return "memory"

        # Binary analysis queries
        binary_keywords = [
            "binary",
            "executable",
            "disassembly",
            "disassemble",
            "decompile",
            "assembly",
            "reverse engineering"
        ]

        if any(word in query for word in binary_keywords):
            return "binary_analysis"

        # Code analysis queries
        code_keywords = [
            "source code",
            "code analysis",
            "find function",
            "function",
            "functions",
            "caller",
            "callers",
            "calls",
            "who calls",
            "call ",
            "module",
            "modules",
            "python file",
            "codebase"
        ]

        if any(word in query for word in code_keywords):
            return "code_analysis"

        return "general"

