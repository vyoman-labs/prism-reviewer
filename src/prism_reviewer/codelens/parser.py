import os
from typing import Dict, Any, List, Optional
from tree_sitter import Language, Parser

from ..core.logger import get_logger

logger = get_logger("prism_reviewer.codelens.parser")


class UniversalASTAnalyzer:
    """
    Analyzes code files to construct a structural AST skeleton containing classes,
    functions, methods, interfaces, and other core abstractions.
    """

    def __init__(self):
        self._parsers: Dict[str, Parser] = {}
        self._init_languages()

    def _init_languages(self):
        """Initializes and caches the language syntax compilers."""
        # Map extension -> lambda that returns the tree-sitter Language object
        self._lang_initializers = {}

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

    def _get_parser_for_extension(self, ext: str) -> Optional[Parser]:
        """Gets or creates a tree-sitter Parser for the given extension."""
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

    def _find_first_identifier(self, n) -> Optional[str]:
        """Recursively finds the first identifier text in a node's tree."""
        if n.type in ("identifier", "field_identifier", "type_identifier", "property_identifier", "destructor_name"):
            return n.text.decode("utf-8", errors="ignore")
        for child in n.children:
            res = self._find_first_identifier(child)
            if res:
                return res
        return None

    def _extract_name(self, node, source_bytes: bytes) -> str:
        """Extracts the identifier name for target abstraction nodes."""
        # 1. Child by field 'name'
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            return name_node.text.decode("utf-8", errors="ignore")

        # 2. Declarator handling (e.g. C++ functions)
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

    def _walk_tree(self, node, source_bytes: bytes) -> List[Dict[str, Any]]:
        """Recursively traverses the tree to find core code abstractions."""
        results = []

        # Target AST node types across supported languages
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
            "class_declaration",
            "interface_declaration",
            "method_declaration",
            "constructor_declaration",
            # C++
            "class_specifier",
            "struct_specifier",
            "namespace_definition",
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

    def get_ast_skeleton(self, file_path: str) -> Dict[str, Any]:
        """
        Reads a file from the workspace, parses it, and walks the tree to extract symbols.
        Falls back to plain-text structure if extension is unsupported.
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
            logger.info(f"Unsupported extension '{ext}'. Falling back to plain-text description.")
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
