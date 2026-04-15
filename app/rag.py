from __future__ import annotations

import asyncio
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from app.file_ingest import chunk_text, list_supported_files, read_file_text
from app.vertex_client import VertexClient


@dataclass(frozen=True)
class Chunk:
    file_name: str
    text: str
    term_freq: Counter[str]
    doc_len: int


@dataclass(frozen=True)
class RetrievedChunk:
    file_name: str
    text: str
    score: float


@dataclass(frozen=True)
class IndexStats:
    files_count: int
    chunks_count: int
    rebuilt_at_utc: datetime | None


class KnowledgeBase:
    def __init__(
        self,
        attach_dir: Path,
        chunk_size: int,
        chunk_overlap: int,
        top_k_chunks: int,
    ) -> None:
        self.attach_dir = attach_dir
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.top_k_chunks = top_k_chunks
        self._chunks: list[Chunk] = []
        self._idf: dict[str, float] = {}
        self._files_count = 0
        self._rebuilt_at_utc: datetime | None = None
        self._lock = asyncio.Lock()

    async def rebuild(self) -> IndexStats:
        async with self._lock:
            chunks, idf, files_count = await asyncio.to_thread(self._build_sync)
            self._chunks = chunks
            self._idf = idf
            self._files_count = files_count
            self._rebuilt_at_utc = datetime.now(timezone.utc)
            return self.stats

    @property
    def stats(self) -> IndexStats:
        return IndexStats(
            files_count=self._files_count,
            chunks_count=len(self._chunks),
            rebuilt_at_utc=self._rebuilt_at_utc,
        )

    async def ask(self, question: str, vertex_client: VertexClient) -> str:
        question = question.strip()
        if not question:
            return "Напишите вопрос текстом."

        chunks = self.search(question, self.top_k_chunks)
        if not chunks:
            return (
                "Не нашел подходящих фрагментов в текущих файлах `attach`. "
                "Добавьте документы или уточните формулировку вопроса."
            )

        prompt = self._build_prompt(question, chunks)
        answer = await vertex_client.generate(prompt)
        return answer.strip()

    def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        tokens = _tokenize(query)
        if not tokens or not self._chunks:
            return []

        query_freq = Counter(tokens)
        avgdl = sum(chunk.doc_len for chunk in self._chunks) / max(len(self._chunks), 1)
        k1 = 1.5
        b = 0.75
        scored: list[RetrievedChunk] = []

        for chunk in self._chunks:
            score = 0.0
            for term, qf in query_freq.items():
                tf = chunk.term_freq.get(term, 0)
                if tf == 0:
                    continue
                idf = self._idf.get(term, 0.0)
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * (chunk.doc_len / max(avgdl, 1e-9)))
                score += idf * (numerator / max(denominator, 1e-9)) * (1.0 + 0.15 * (qf - 1))
            if score > 0:
                scored.append(RetrievedChunk(file_name=chunk.file_name, text=chunk.text, score=score))

        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:top_k]

    def _build_sync(self) -> tuple[list[Chunk], dict[str, float], int]:
        files = list_supported_files(self.attach_dir)
        chunks: list[Chunk] = []

        for file_path in files:
            text = read_file_text(file_path)
            if not text:
                continue
            for part in chunk_text(text=text, chunk_size=self.chunk_size, overlap=self.chunk_overlap):
                tokens = _tokenize(part)
                if not tokens:
                    continue
                chunks.append(
                    Chunk(
                        file_name=file_path.name,
                        text=part,
                        term_freq=Counter(tokens),
                        doc_len=len(tokens),
                    )
                )

        idf = _compute_idf(chunks)
        return chunks, idf, len(files)

    def _build_prompt(self, question: str, chunks: Iterable[RetrievedChunk]) -> str:
        context_parts = []
        for idx, chunk in enumerate(chunks, start=1):
            context_parts.append(
                f"[Фрагмент {idx}] Источник: {chunk.file_name}\n"
                f"{chunk.text}"
            )
        context = "\n\n".join(context_parts)

        return (
            "Ты ассистент для сотрудников отеля. Отвечай только по данным из контекста.\n"
            "Не придумывай факты. Если данных недостаточно, явно так и напиши.\n"
            "Ответ должен быть структурирован чётко, без лишней воды, опираясь на контекстные файлы\n"
            "Пиши на русском языке.\n"
            "Не добавляй блок 'Источники'.\n"
            "Не упоминай названия файлов.\n"
            "Используй ТОЛЬКО HTML-разметку с такими блоками: <b>, <i>, <code>, <u>.\n НЕ ИСПОЛЬЗУЙ ДРУГИЕ ТЕГИ РАЗМЕТКИ"
            "НЕ ИСПОЛЬЗУЙ "
            "Не используй Markdown.\n"
            "Структура ответа:\n"
            "1) <b>Пошаговые действия</b>\n"
            "2) <b>Исключения и риски</b>(если есть)\n"
            "3) <b>Что проверить дополнительно</b>(если есть)\n\n"
            f"Вопрос пользователя:\n{question}\n\n"
            f"Контекст из документов:\n{context}"
            "ТЕГ <li> и <ol> <br>- КАТЕГОРИЧЕСКИ ЗАПРЕЩЕН!!!"
        )


def _tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[0-9A-Za-zА-Яа-яЁё_]+", text.lower()) if len(t) > 1]


def _compute_idf(chunks: list[Chunk]) -> dict[str, float]:
    total_docs = len(chunks)
    if total_docs == 0:
        return {}

    doc_freq: Counter[str] = Counter()
    for chunk in chunks:
        for term in chunk.term_freq.keys():
            doc_freq[term] += 1

    idf: dict[str, float] = {}
    for term, freq in doc_freq.items():
        idf[term] = math.log(1 + (total_docs - freq + 0.5) / (freq + 0.5))
    return idf
