"""Detecção de respostas de texto repetidas (modelo preso dizendo a mesma coisa)."""

import difflib


class RepeatedResponseDetector:
    """
    Retorna True quando as últimas `threshold` respostas são praticamente iguais.

    Serve para o caso em que a tarefa depende do humano (ex.: senha de sudo) e o
    modelo repete "preciso de confirmação" até esgotar as iterações.
    """

    def __init__(self, threshold: int = 3, similarity: float = 0.9):
        self.threshold = threshold
        self.similarity = similarity
        self._recent: list[str] = []

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join((text or "").lower().split())[:600]

    def check(self, text: str) -> bool:
        current = self._normalize(text)

        self._recent.append(current)
        self._recent = self._recent[-self.threshold:]

        if len(self._recent) < self.threshold:
            return False

        return all(
            difflib.SequenceMatcher(None, current, previous).ratio() >= self.similarity
            for previous in self._recent[:-1]
        )

    def reset(self) -> None:
        self._recent.clear()
