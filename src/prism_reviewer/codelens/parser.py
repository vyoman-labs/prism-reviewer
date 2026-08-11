"""
prism_reviewer.codelens.parser
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Analyzes source files to extract AST-level structural skeletons (classes,
functions, methods, interfaces, namespaces, type definitions) using
tree-sitter grammars.

Supported languages (when the corresponding grammar package is installed):
    Python, Java, TypeScript / TSX, JavaScript / JSX, C, C++, Go.

If tree-sitter or an individual grammar package is not available the module
degrades gracefully: files with unsupported extensions produce a ``plain-text``
skeleton containing a single whole-file symbol.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..core.logger import get_logger

logger = get_logger("prism_reviewer.codelens.parser")

# ---------------------------------------------------------------------------
# Conditional tree-sitter import — the module remains importable even when the
# ``tree-sitter`` package is absent (pure plain-text fallback mode).
# ---------------------------------------------------------------------------
_TREE_SITTER_AVAILABLE: bool = False
try:
    from tree_sitter import Language, Parser
    _TREE_SITTER_AVAILABLE = True
except ImportError:
    logger.warning(
        "tree-sitter is not installed. "
        "AST analysis will fall back to plain-text mode for all files."
    )

if TYPE_CHECKING:
    from tree_sitter import Language, Parser


class UniversalASTAnalyzer:
    """
    Analyzes code files to construct a structural AST skeleton containing classes,
    functions, methods, interfaces, and other core abstractions.
    """

    def __init__(self) -> None:
        self._parsers: Dict[str, Parser] = {}
        self._lang_initializers: Dict[str, Any] = {}
        self._init_languages()

    # ------------------------------------------------------------------
    # Language grammar loading
    # ------------------------------------------------------------------

    def _init_languages(self) -> None:
        """Initializes and caches the language syntax compilers.

        Each grammar is loaded inside its own ``try/except ImportError`` block
        so that missing packages produce a warning instead of crashing the
        whole analyzer.  When the core ``tree-sitter`` runtime is absent the
        method returns immediately.
        """
        if not _TREE_SITTER_AVAILABLE:
            logger.debug(
                "Skipping AST grammar loading — tree-sitter runtime not available."
            )
            return

        # Load Python
        try:
            import tree_sitter_python
            self._lang_initializers[".py"] = lambda: Language(tree_sitter_python.language())
        except ImportError as e:
            logger.warning(f"Could not import tree-sitter-python: {e}")

        # Load TypeScript / TSX
        try:
            import tree_sitter_typescript
            self._lang_initializers[".ts"] = lambda: Language(tree_sitter_typescript.language_typescript())
            self._lang_initializers[".tsx"] = lambda: Language(tree_sitter_typescript.language_tsx())
        except ImportError as e:
            logger.warning(f"Could not import tree-sitter-typescript: {e}")

        # Load JavaScript / JSX
        try:
            import tree_sitter_javascript
            js_lang = lambda: Language(tree_sitter_javascript.language())
            self._lang_initializers[".js"] = js_lang
            self._lang_initializers[".jsx"] = js_lang
        except ImportError as e:
            logger.warning(f"Could not import tree-sitter-javascript: {e}")

        # Load Java
        try:
            import tree_sitter_java
            self._lang_initializers[".java"] = lambda: Language(tree_sitter_java.language())
        except ImportError as e:
            logger.warning(f"Could not import tree-sitter-java: {e}")

        # Load C
        try:
            import tree_sitter_c
            self._lang_initializers[".c"] = lambda: Language(tree_sitter_c.language())
        except ImportError as e:
            logger.warning(f"Could not import tree-sitter-c: {e}")

        # Load C++
        try:
            import tree_sitter_cpp
            cpp_lang = lambda: Language(tree_sitter_cpp.language())
            self._lang_initializers[".cpp"] = cpp_lang
            self._lang_initializers[".cc"] = cpp_lang
            self._lang_initializers[".cxx"] = cpp_lang
            self._lang_initializers[".h"] = cpp_lang
            self._lang_initializers[".hpp"] = cpp_lang
        except ImportError as e:
            logger.warning(f"Could not import tree-sitter-cpp: {e}")

        # Load Go
        try:
            import tree_sitter_go
            self._lang_initializers[".go"] = lambda: Language(tree_sitter_go.language())
        except ImportError as e:
            logger.warning(f"Could not import tree-sitter-go: {e}")

        # Load Rust
        try:
            import tree_sitter_rust
            self._lang_initializers[".rs"] = lambda: Language(tree_sitter_rust.language())
        except ImportError as e:
            logger.warning(f"Could not import tree-sitter-rust: {e}")

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def supported_languages(self) -> List[str]:
        """Returns the sorted list of file extensions for which AST parsing is available.

        Returns:
            A sorted list of dot-prefixed extension strings
            (e.g. ``[".c", ".cc", ".cpp", ".go", ".h", ".hpp", ...]``).
        """
        return sorted(self._lang_initializers.keys())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_parser_for_extension(self, ext: str) -> Optional[Parser]:
        """Gets or creates a tree-sitter Parser for the given extension.

        Args:
            ext: Dot-prefixed file extension (e.g. ``".py"``).

        Returns:
            A ``Parser`` instance, or ``None`` if the extension is unsupported.
        """
        if ext not in self._lang_initializers:
            return None

        if ext not in self._parsers:
            try:
                lang = self._lang_initializers[ext]()
                self._parsers[ext] = Parser(lang)
            except Exception as e:
                logger.error(f"Failed to create parser for extension {ext}: {e}")
                return None

        return self._parsers[ext]

    def _find_first_identifier(self, n: Any) -> Optional[str]:
        """Recursively finds the first identifier text in a node's tree.

        Args:
            n: A tree-sitter ``Node``.

        Returns:
            The text of the first identifier-like child, or ``None``.
        """
        if n.type in ("identifier", "field_identifier", "type_identifier", "property_identifier", "destructor_name"):
            return n.text.decode("utf-8", errors="ignore")
        for child in n.children:
            res = self._find_first_identifier(child)
            if res:
                return res
        return None

    def _extract_name(self, node: Any, source_bytes: bytes) -> str:
        """Extracts the identifier name for target abstraction nodes.

        Applies several heuristics in priority order:

        1. ``child_by_field_name("name")`` — works for most language grammars.
        2. ``child_by_field_name("declarator")`` — C/C++ function definitions.
        3. Parent-level lookup for JS/TS arrow functions assigned to variables.
        4. Fallback scan for common identifier child nodes.

        Args:
            node:         A tree-sitter ``Node`` representing a target abstraction.
            source_bytes: Raw source file bytes (for decoding identifiers).

        Returns:
            The extracted name, or ``"<anonymous>"`` if no name could be found.
        """
        # 1. Child by field 'name'
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            return name_node.text.decode("utf-8", errors="ignore")

        # 2. Declarator handling (e.g. C/C++ functions)
        decl_node = node.child_by_field_name("declarator")
        if decl_node is not None:
            ident = self._find_first_identifier(decl_node)
            if ident:
                return ident

        # 3. For JS/TS Arrow Functions, look up the parent variable declarator or property key
        if node.type == "arrow_function":
            parent = node.parent
            if parent is not None:
                if parent.type == "variable_declarator":
                    id_node = parent.child_by_field_name("name")
                    if id_node is not None:
                        return id_node.text.decode("utf-8", errors="ignore")
                elif parent.type == "pair":
                    key_node = parent.child_by_field_name("key")
                    if key_node is not None:
                        return key_node.text.decode("utf-8", errors="ignore")

        # 4. Fallback search for common identifier nodes
        for child in node.children:
            if child.type in ("identifier", "type_identifier", "property_identifier", "field_identifier"):
                return child.text.decode("utf-8", errors="ignore")

        return "<anonymous>"

    def _walk_tree(self, node: Any, source_bytes: bytes) -> List[Dict[str, Any]]:
        """Recursively traverses the tree to find core code abstractions.

        Args:
            node:         A tree-sitter ``Node`` to walk.
            source_bytes: Raw source file bytes.

        Returns:
            A list of symbol dicts with ``name``, ``type``, ``start_line``, ``end_line``.
        """
        results: List[Dict[str, Any]] = []

        # Target AST node types across supported languages.
        # Notes:
        # - ``function_definition`` is shared by Python, C, and C++.
        # - ``function_declaration`` is shared by JS/TS and Go.
        # - ``class_declaration`` is shared by JS/TS and Java.
        # - ``method_declaration`` is shared by Java and Go.
        # - ``struct_specifier`` is shared by C and C++.
        target_types = {
            # Python
            "class_definition",
            "function_definition",
            # JS / TS
            "class_declaration",
            "class",
            "function_declaration",
            "method_definition",
            "interface_declaration",
            "arrow_function",
            # Java
            "method_declaration",
            "constructor_declaration",
            # C / C++
            "class_specifier",
            "struct_specifier",
            "namespace_definition",
            # Go
            "type_spec",
            # Rust
            "function_item",
            "struct_item",
            "enum_item",
            "impl_item",
            "trait_item",
            "mod_item",
        }

        # Check if node matches target types
        if node.type in target_types or node.type == "function_definition":
            # Extract boundaries. Convert to 1-indexed.
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            name = self._extract_name(node, source_bytes)

            results.append({
                "name": name,
                "type": node.type,
                "start_line": start_line,
                "end_line": end_line,
            })

        # Recurse children
        for child in node.children:
            results.extend(self._walk_tree(child, source_bytes))

        return results

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def get_ast_skeleton(self, file_path: str) -> Dict[str, Any]:
        """
        Reads a file from the workspace, parses it, and walks the tree to extract symbols.
        Falls back to plain-text structure if extension is unsupported.

        Args:
            file_path: Absolute path to the source file.

        Returns:
            A dict with keys ``file_path``, ``mode`` (``"ast"`` or ``"plain-text"``),
            and ``symbols`` (list of symbol dicts).

        Raises:
            FileNotFoundError: If *file_path* does not exist.
            RuntimeError: If AST parsing fails on a supported file type.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        _, ext = os.path.splitext(file_path)
        ext = ext.lower()

        try:
            with open(file_path, "rb") as f:
                source_bytes = f.read()
        except Exception as e:
            logger.error(f"Failed to read file {file_path}: {e}")
            raise

        parser = self._get_parser_for_extension(ext)
        if parser is None:
            # Fallback to plain-text reading blocks if unknown/unsupported extension
            logger.debug(f"Unsupported extension '{ext}'. Falling back to plain-text description.")
            try:
                text_content = source_bytes.decode("utf-8", errors="ignore")
                lines = text_content.splitlines()
                return {
                    "file_path": file_path,
                    "mode": "plain-text",
                    "symbols": [
                        {
                            "name": os.path.basename(file_path),
                            "type": "file",
                            "start_line": 1,
                            "end_line": max(1, len(lines)),
                        }
                    ]
                }
            except Exception as e:
                logger.error(f"Failed to process plain-text fallback for {file_path}: {e}")
                raise

        # Parse source code
        try:
            tree = parser.parse(source_bytes)
            symbols = self._walk_tree(tree.root_node, source_bytes)
            return {
                "file_path": file_path,
                "mode": "ast",
                "symbols": symbols,
            }
        except Exception as e:
            logger.error(f"Error parsing file {file_path}: {e}")
            raise RuntimeError(f"AST parsing failed: {e}") from e
