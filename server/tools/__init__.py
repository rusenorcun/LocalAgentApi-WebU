"""Genel arac cercevesi (tool registry) — Ollama function calling.

Her arac bir ToolSpec'tir: ad + aciklama + JSON Schema parametreleri + async run.
run(args: dict) -> str | {"text": str, "sources": list}
  - str: dogrudan modele verilecek arac sonucu metni.
  - dict: {"text": modele giden metin, "sources": [{title,url?,snippet?}]} (UI kaynaklari).

Yeni arac eklemek: bir modul yazip register_tool(ToolSpec(...)) cagir ve asagidaki
import listesine ekle. Pipeline (run_agent_turn) degismez.
"""
from typing import Awaitable, Callable, Union


class ToolSpec:
    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        run: Callable[[dict], Awaitable[Union[str, dict]]],
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.run = run


REGISTRY: dict[str, "ToolSpec"] = {}


def register_tool(spec: "ToolSpec") -> None:
    REGISTRY[spec.name] = spec


def ollama_tools_payload(names=None) -> list[dict]:
    """Ollama /api/chat 'tools' formatini uretir. names verilirse yalniz onlar."""
    specs = list(REGISTRY.values())
    if names is not None:
        specs = [REGISTRY[n] for n in names if n in REGISTRY]
    return [
        {
            "type": "function",
            "function": {
                "name": s.name,
                "description": s.description,
                "parameters": s.parameters,
            },
        }
        for s in specs
    ]


# Araclari kaydet — import edilince REGISTRY dolar.
from . import web_search_tool  # noqa: E402,F401
from . import calculator_tool  # noqa: E402,F401
from . import python_tool      # noqa: E402,F401
