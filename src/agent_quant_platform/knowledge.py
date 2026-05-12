from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class KnowledgeNote:
    note_id: str
    title: str
    content: str
    symbols: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    source: str = "local"

    def matches(self, symbol: str, query: str = "", tags: list[str] | None = None) -> bool:
        symbol_upper = symbol.upper()
        query_text = query.lower().strip()
        requested_tags = {tag.lower() for tag in (tags or [])}
        note_symbols = {item.upper() for item in self.symbols}
        note_tags = {tag.lower() for tag in self.tags}
        text_blob = f"{self.title} {self.content}".lower()

        symbol_match = not note_symbols or symbol_upper in note_symbols
        query_match = not query_text or query_text in text_blob
        tag_match = not requested_tags or not requested_tags.isdisjoint(note_tags)
        return symbol_match and query_match and tag_match


class InMemoryKnowledgeBase:
    def __init__(self, notes: list[KnowledgeNote] | None = None) -> None:
        self.notes = notes or []

    def search(
        self,
        symbol: str,
        query: str = "",
        limit: int = 3,
        tags: list[str] | None = None,
    ) -> list[KnowledgeNote]:
        matches = [note for note in self.notes if note.matches(symbol=symbol, query=query, tags=tags)]
        return matches[:limit]


def default_market_knowledge_base() -> InMemoryKnowledgeBase:
    return InMemoryKnowledgeBase(
        notes=[
            KnowledgeNote(
                note_id="btc-trend-following",
                title="BTC spot trend strategies perform better when momentum and MACD align.",
                content=(
                    "In spot-only mode, long exposure should be concentrated in aligned trend regimes and "
                    "de-risked quickly when volatility expands or trend confirmation weakens."
                ),
                symbols=["BTCUSDT"],
                tags=["trend", "risk", "spot"],
            ),
            KnowledgeNote(
                note_id="spot-no-short",
                title="Spot execution cannot express directional short exposure.",
                content=(
                    "When downside evidence is strong, the correct spot response is often inventory reduction "
                    "or flat positioning instead of opening a new short."
                ),
                symbols=["BTCUSDT", "ETHUSDT"],
                tags=["execution", "spot", "inventory"],
            ),
            KnowledgeNote(
                note_id="volatility-breaker",
                title="High realized volatility should tighten or halt risk-taking.",
                content=(
                    "When short-horizon realized volatility is materially above baseline, preserve capital and "
                    "require stronger confirmation before adding exposure."
                ),
                symbols=[],
                tags=["volatility", "risk"],
            ),
        ]
    )
