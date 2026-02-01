"""
Parser Service - AST Analysis with Tree-sitter
===============================================

This module provides Abstract Syntax Tree (AST) parsing for source code files.
It uses Tree-sitter, the same parser used by GitHub code search, VS Code,
and many other professional tools.

Why Tree-sitter?
    - Language-agnostic: Same API for Python, JavaScript, TypeScript, Go, etc.
    - Incremental: Fast re-parsing for file changes (not used here, but available)
    - Error-resilient: Produces partial AST even for invalid syntax
    - Battle-tested: Used in production by GitHub, Neovim, Helix editor

What We Extract:
    - Classes: `class_definition` nodes -> Class names
    - Functions: `function_definition` nodes -> Function names  
    - Endpoints: `decorated_definition` nodes with route decorators -> API endpoints

Supported Languages (configured in _setup_parsers):
    - Python (.py)
    - JavaScript (.js)
    
Extensible to: TypeScript, Go, Java, Rust, etc. (just add the grammar)

Usage:
    parser = ParserService()
    tree = parser.parse("def hello(): pass", ".py")
    for type_, name, extra in parser.extract_structure(tree.root_node, content):
        print(f"{type_}: {name}")  # "Function: hello"
"""

from tree_sitter import Language, Parser
import tree_sitter_python
import tree_sitter_javascript
import tree_sitter_typescript
import tree_sitter_go
import tree_sitter_java
from typing import Dict, Generator, Tuple, Optional
from app.core.logger import logger


class ParserService:
    """
    Handles code parsing using Tree-sitter grammars.
    
    This service is responsible for:
    1. Initializing language-specific parsers at startup
    2. Parsing source code into ASTs
    3. Walking ASTs to extract structural elements (Classes, Functions, Endpoints)
    
    Architecture:
        ParserService._parsers = {
            '.py': Parser(Python grammar),
            '.js': Parser(JavaScript grammar),
        }
        
    Singleton Pattern:
        Instantiated once in GraphService and reused for all files.
        Parsers are expensive to initialize, so we cache them.
    """
    
    def __init__(self):
        """
        Initialize the ParserService with language-specific parsers.
        
        This sets up parsers for all supported languages. Each parser
        is associated with a file extension for easy lookup.
        
        Initialization happens at server startup, so parser loading
        errors are caught early and logged.
        """
        self._parsers = self._setup_parsers()
        logger.info("ParserService initialized", languages=list(self._parsers.keys()))

    def _setup_parsers(self) -> Dict[str, Parser]:
        """
        Initialize Tree-sitter parsers for each supported language.
        
        Tree-sitter requires a Language object (compiled grammar) to be
        passed to the Parser constructor. Each language has its own
        pip-installable grammar package (e.g., tree-sitter-python).
        
        Returns:
            Dictionary mapping file extensions to Parser instances
            
        Note:
            The Tree-sitter API changed in recent versions. We now pass
            the Language directly to the Parser constructor instead of
            calling parser.set_language().
        """
        parsers = {}
        
        # =================================================================
        # Python Parser
        # =================================================================
        try:
            # Create Language object from the compiled grammar
            lang = Language(tree_sitter_python.language())
            # Create Parser with Language (new API in tree-sitter 0.21+)
            py_parser = Parser(lang)
            parsers['.py'] = py_parser
            logger.info("Python parser initialized successfully")
        except Exception as e:
            logger.error("Failed to init Python parser", error=str(e))

        # =================================================================
        # JavaScript Parser
        # =================================================================
        try:
            lang = Language(tree_sitter_javascript.language())
            js_parser = Parser(lang)
            parsers['.js'] = js_parser
            logger.info("JavaScript parser initialized successfully")
        except Exception as e:
            logger.error("Failed to init JS parser", error=str(e))
        
        # Additional parsers can be added here:
        # TypeScript: tree_sitter_typescript.language_typescript()
        # Go: tree_sitter_go.language()
        # Java: tree_sitter_java.language()
        
        return parsers

    def parse(self, content: str, ext: str):
        """
        Parse source code content into an AST.
        
        This method looks up the appropriate parser based on file extension
        and produces an Abstract Syntax Tree (AST) from the source code.
        
        Args:
            content: Source code as a string
            ext: File extension including dot (e.g., ".py", ".js")
            
        Returns:
            Tree-sitter Tree object with root_node, or None if unsupported
            
        Example:
            >>> tree = parser.parse("class Book: pass", ".py")
            >>> tree.root_node.type
            'module'
        """
        parser = self._parsers.get(ext)
        if not parser:
            # Unsupported file type (e.g., .md, .json, .yaml)
            return None
        # Tree-sitter requires bytes input, not string
        return parser.parse(bytes(content, "utf8"))

    def extract_structure(
        self, 
        root_node, 
        content: bytes
    ) -> Generator[Tuple[str, str, Optional[str]], None, None]:
        """
        Walk the AST and yield structural definitions.
        
        This is the core extraction logic. It walks the top-level children
        of the AST and identifies:
        
        1. Class definitions -> ('Class', 'ClassName', None)
        2. Function definitions -> ('Function', 'func_name', None)
        3. Decorated functions with route decorators -> ('Endpoint', 'handler', '@app.get("/path")')
        
        Args:
            root_node: Root node of the AST (tree.root_node)
            content: Source code as bytes (needed to extract node text)
            
        Yields:
            Tuples of (type, name, extra_info)
            - type: "Class", "Function", or "Endpoint"
            - name: The identifier name
            - extra_info: For endpoints, the decorator text; otherwise None
            
        AST Node Types (Python):
            - class_definition: `class Foo:`
            - function_definition: `def bar():`
            - decorated_definition: `@decorator\\ndef baz():`
            
        Example Output:
            ('Class', 'Book', None)
            ('Endpoint', 'get_books', '@app.get("/books")')
            ('Function', 'helper', None)
        """
        for child in root_node.children:
            
            # =============================================================
            # Class Definitions
            # =============================================================
            if child.type == 'class_definition':
                # Extract the class name from the 'name' field
                name_node = child.child_by_field_name('name')
                if name_node:
                    class_name = content[name_node.start_byte:name_node.end_byte].decode("utf8")
                    yield 'Class', class_name, None
                     
            # =============================================================
            # Decorated Definitions (may be FastAPI endpoints)
            # =============================================================
            elif child.type == 'decorated_definition':
                # A decorated_definition contains:
                # - One or more decorator nodes
                # - The actual function_definition
                func_def = None
                decorators = []
                
                for sub in child.children:
                    if sub.type == 'decorator':
                        # Extract full decorator text: "@app.get('/books')"
                        dec_text = content[sub.start_byte:sub.end_byte].decode("utf8")
                        decorators.append(dec_text)
                    elif sub.type == 'function_definition':
                        func_def = sub
                
                if func_def:
                    name_node = func_def.child_by_field_name('name')
                    if name_node:
                        func_name = content[name_node.start_byte:name_node.end_byte].decode("utf8")
                        
                        # Check if any decorator looks like a FastAPI/Flask endpoint
                        # Common patterns: @app.get, @router.post, @blueprint.put
                        route_info = None
                        for dec in decorators:
                            http_methods = ['.get(', '.post(', '.put(', '.delete(', '.patch(']
                            if any(method in dec.lower() for method in http_methods):
                                route_info = dec
                                break
                        
                        if route_info:
                            # This is an API endpoint
                            yield 'Endpoint', func_name, route_info
                        else:
                            # Just a decorated function (e.g., @staticmethod)
                            yield 'Function', func_name, None
                            
            # =============================================================
            # Standalone Function Definitions (no decorators)
            # =============================================================
            elif child.type == 'function_definition':
                name_node = child.child_by_field_name('name')
                if name_node:
                    func_name = content[name_node.start_byte:name_node.end_byte].decode("utf8")
                    yield 'Function', func_name, None
