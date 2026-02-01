from tree_sitter import Language, Parser
import tree_sitter_python
import tree_sitter_javascript
import tree_sitter_typescript
import tree_sitter_go
import tree_sitter_java
from typing import Dict
from app.core.logger import logger

class ParserService:
    """
    Handles code parsing using Tree-sitter.
    Singleton pattern compliant.
    """
    def __init__(self):
        self._parsers = self._setup_parsers()
        logger.info("ParserService initialized", languages=list(self._parsers.keys()))

    def _setup_parsers(self) -> Dict[str, Parser]:
        parsers = {}
        try:
            # Python
            try:
                py_parser = Parser()
                py_parser.set_language(Language(tree_sitter_python.language()))
                parsers['.py'] = py_parser
            except Exception as e:
                logger.error("Failed to init Python parser", error=str(e))

            # JS/TS
            try:
                js_parser = Parser()
                js_parser.set_language(Language(tree_sitter_javascript.language()))
                parsers['.js'] = js_parser
            except Exception as e:
                logger.error("Failed to init JS parser", error=str(e))
            
            # More can be added...
        except Exception as e:
            logger.error("Failed to initialize parsers", error=str(e))
        return parsers

    def parse(self, content: str, ext: str):
        """
        Parses content if a parser exists for the extension.
        Returns the tree or None.
        """
        parser = self._parsers.get(ext)
        if not parser:
            return None
        return parser.parse(bytes(content, "utf8"))

    def extract_structure(self, root_node, content: bytes):
        """
        Walks the AST and returns found definitions.
        This is a generator that yields (type, name).
        """
        for child in root_node.children:
            if child.type == 'class_definition':
                name_node = child.child_by_field_name('name')
                if name_node:
                     yield 'Class', content[name_node.start_byte:name_node.end_byte].decode("utf8")
            elif child.type == 'function_definition':
                name_node = child.child_by_field_name('name')
                if name_node:
                    yield 'Function', content[name_node.start_byte:name_node.end_byte].decode("utf8")
