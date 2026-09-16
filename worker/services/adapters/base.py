# worker/services/adapters/base.py
"""
Contrato común que debe cumplir cualquier fuente (StackOverflow, GitHub,
RSS, web, etc.). Ver INSTRUCCIONES_IA.md sección 3.1 y 3.4.
"""
from typing import Any, Dict, List, Protocol


class SourceAdapter(Protocol):
    name: str

    def check(self) -> Dict[str, Any]:
        """Diagnóstico de solo lectura: disponibilidad y motivo si no aplica."""
        ...

    def search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """
        Devuelve posts normalizados al esquema común:
        title, url, source, content, author, date, score, tags.
        """
        ...

    def read(self, url: str) -> Dict[str, Any]:
        """Lee el contenido de una URL puntual. No todas las fuentes lo soportan."""
        ...
