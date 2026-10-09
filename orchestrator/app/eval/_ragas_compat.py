"""Compatibility shim: ragas 0.4.3 unconditionally imports
`langchain_community.chat_models.vertexai.ChatVertexAI`, a module that was removed
from langchain-community in the version this project otherwise depends on (0.4.2).
Ragas only uses it for an internal isinstance() check to special-case VertexAI
models — since HiveFix never uses VertexAI, a harmless stub class that nothing will
ever match satisfies the import without pulling in Google's SDK or downgrading
langchain-community (which the rest of the app's langchain 1.x stack needs >=0.4 of).

Must be imported before `ragas` anywhere in this process.
"""

import sys
import types


def apply() -> None:
    module_name = "langchain_community.chat_models.vertexai"
    if module_name in sys.modules:
        return

    shim = types.ModuleType(module_name)

    class ChatVertexAI:  # noqa: N801 — matching the real class name ragas imports
        pass

    shim.ChatVertexAI = ChatVertexAI
    sys.modules[module_name] = shim
