class SituationSummariser:
    MAX_TOKENS = 400

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    def summarise(self, text: str) -> str:
        words = text.split()
        if len(words) <= self.MAX_TOKENS:
            return text
        truncated = " ".join(words[: self.MAX_TOKENS])
        if self.llm_client:
            response = self.llm_client.analyze(
                f"Summarize in {self.MAX_TOKENS} words: {truncated}"
            )
            return response.text
        return truncated + "..."
