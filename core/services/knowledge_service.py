from pathlib import Path


class KnowledgeService:
    """Business logic for policy and FAQ knowledge-base search."""

    def __init__(self, knowledge_base_path: Path | None = None):
        self.knowledge_base_path = knowledge_base_path or Path(__file__).resolve().parents[2] / "knowledge_base.txt"
        self.knowledge_base_content = ""
        if self.knowledge_base_path.exists():
            self.knowledge_base_content = self.knowledge_base_path.read_text(encoding="utf-8")

    def search_knowledge_base(self, query: str) -> str:
        if not self.knowledge_base_content:
            return "Knowledge base is not available at this time."

        query_lower = query.lower()
        lines = self.knowledge_base_content.split("\n")
        relevant_lines = []
        current_section = ""

        for line in lines:
            if line.startswith("---") and line.endswith("---"):
                current_section = line
            if any(keyword in line.lower() for keyword in query_lower.split()):
                if current_section and current_section not in relevant_lines:
                    relevant_lines.append(current_section)
                relevant_lines.append(line)

        if not relevant_lines:
            return f"No exact keyword match found for '{query}'. Here is the full knowledge base for reference:\n\n{self.knowledge_base_content}"

        return f"Relevant store policy information for '{query}':\n" + "\n".join(relevant_lines)


knowledge_service = KnowledgeService()
