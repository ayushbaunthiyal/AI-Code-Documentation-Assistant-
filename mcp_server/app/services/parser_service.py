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
        # Python
        try:
            lang = Language(tree_sitter_python.language())
            py_parser = Parser(lang)  # New API: Pass Language to constructor
            parsers['.py'] = py_parser
            logger.info("Python parser initialized successfully")
        except Exception as e:
            logger.error("Failed to init Python parser", error=str(e))

        # JS
        try:
            lang = Language(tree_sitter_javascript.language())
            js_parser = Parser(lang)
            parsers['.js'] = js_parser
            logger.info("JavaScript parser initialized successfully")
        except Exception as e:
            logger.error("Failed to init JS parser", error=str(e))
        
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
        This is a generator that yields (type, name, extra_info).
        For endpoints, extra_info contains the route path.
        """
        for child in root_node.children:
            if child.type == 'class_definition':
                name_node = child.child_by_field_name('name')
                if name_node:
                     yield 'Class', content[name_node.start_byte:name_node.end_byte].decode("utf8"), None
            elif child.type == 'decorated_definition':
                # This is a function or class with decorators - check for FastAPI endpoints
                func_def = None
                decorators = []
                
                for sub in child.children:
                    if sub.type == 'decorator':
                        dec_text = content[sub.start_byte:sub.end_byte].decode("utf8")
                        decorators.append(dec_text)
                    elif sub.type == 'function_definition':
                        func_def = sub
                
                if func_def:
                    name_node = func_def.child_by_field_name('name')
                    if name_node:
                        func_name = content[name_node.start_byte:name_node.end_byte].decode("utf8")
                        
                        # Check if any decorator looks like a FastAPI endpoint
                        route_info = None
                        for dec in decorators:
                            if any(method in dec.lower() for method in ['.get(', '.post(', '.put(', '.delete(', '.patch(']):
                                route_info = dec
                                break
                        
                        if route_info:
                            yield 'Endpoint', func_name, route_info
                        else:
                            yield 'Function', func_name, None
                            
            elif child.type == 'function_definition':
                name_node = child.child_by_field_name('name')
                if name_node:
                    yield 'Function', content[name_node.start_byte:name_node.end_byte].decode("utf8"), None
