"""
Graph Service - Knowledge Graph Management
==========================================

This module is the core of the codebase ingestion pipeline. It handles:

1. Cloning Git repositories to temporary directories
2. Walking the file tree and processing each file
3. Parsing source files using Tree-sitter (via ParserService)
4. Storing extracted structure in Memgraph as a knowledge graph

Knowledge Graph Schema:
    Nodes:
        - :File {path, language}     - Each file in the repository
        - :Class {name}              - Python/JS class definitions
        - :Function {name}           - Standalone function definitions
        - :Endpoint {name, route}    - FastAPI/Express route handlers
    
    Relationships:
        - (Class/Function/Endpoint)-[:DEFINED_IN]->(File)
        
Example Graph:
    (:Class {name: "Book"}) -[:DEFINED_IN]-> (:File {path: "app/models.py"})
    (:Endpoint {name: "get_books", route: "@app.get('/books')"}) -[:DEFINED_IN]-> (:File {path: "app/main.py"})

Usage:
    graph_service = GraphService()
    result = graph_service.ingest_repository("https://github.com/user/repo")
    # "Ingestion Complete. Processed 42 files. Graph: 150 Nodes, 45 Edges."
"""

import git
import os
import tempfile
from gqlalchemy import Memgraph
from app.core.config import settings
from app.core.logger import logger
from app.services.parser_service import ParserService


class GraphService:
    """
    Service for Graph Database interactions (Ingestion & Querying).
    
    This is the primary service class that coordinates:
    - Repository cloning (Git)
    - File system traversal
    - AST parsing delegation (ParserService)
    - Graph database writes (Memgraph via gqlalchemy)
    
    Design Decisions:
    - Single-repo mode: Database is cleared before each ingestion
    - Fail-safe file processing: One file failure doesn't stop the batch
    - Always create File nodes: Even if AST parsing fails
    """
    
    def __init__(self):
        """
        Initialize the GraphService with Memgraph connection and ParserService.
        
        The Memgraph connection is established using credentials from settings.
        This happens at server startup, so connection errors fail fast.
        """
        # Connect to Memgraph using gqlalchemy ORM
        # gqlalchemy provides a Pythonic interface to Cypher queries
        self.memgraph = Memgraph(
            host=settings.MEMGRAPH_HOST, 
            port=settings.MEMGRAPH_PORT,
            username=settings.MEMGRAPH_USER,
            password=settings.MEMGRAPH_PASSWORD
        )
        
        # Initialize the AST parser for Python/JavaScript
        self.parser_service = ParserService()
    
    def check_connection(self) -> bool:
        """
        Verify that Memgraph is reachable.
        
        Used for health checks and debugging connection issues.
        
        Returns:
            True if connection is healthy, False otherwise
        """
        try:
            # Simple query to check connection
            self.memgraph.execute("RETURN 1")
            return True
        except Exception as e:
            logger.error("Memgraph connection failed", error=str(e))
            return False

    def ingest_repository(self, source: str) -> str:
        """
        Main ingestion entry point - clones and processes a repository.
        
        This is the top-level method called by the MCP tool. It orchestrates
        the entire ingestion pipeline:
        
        Pipeline Steps:
            1. Clone repository (if URL) or validate local path
            2. Clear existing database (single-repo mode)
            3. Create indexes for query performance
            4. Walk all files, excluding .git directory
            5. Process each file (create File node, parse if supported)
            6. Return statistics
        
        Args:
            source: Git URL (https://github.com/...) or local filesystem path
            
        Returns:
            Success message with statistics, or error message
            
        Example:
            >>> ingest_repository("https://github.com/user/fastapi-app")
            "Ingestion Complete. Processed 42 files. Graph: 150 Nodes, 45 Edges."
        """
        logger.info("Starting ingestion", source=source)
        
        try:
            # Step 1: Determine if source is URL or local path
            if source.startswith("http"):
                # Clone to temp directory (auto-cleaned by OS eventually)
                repo_path = self._clone_repo(source)
            else:
                # Use local path directly
                repo_path = source
            
            # Validate path exists
            if not os.path.exists(repo_path):
                return f"Error: Path {repo_path} does not exist."

            # Step 2: Clear database for single-repo mode
            # This ensures we only have one codebase in the graph at a time
            self._clear_database()
            
            # Step 3: Create indexes for faster queries
            self._create_indexes()

            # Step 4: Walk file tree and process each file
            count = 0
            for root, _, files in os.walk(repo_path):
                # Skip .git directory (not part of source code)
                if ".git" in root: 
                    continue
                for file in files:
                    self._process_file(os.path.join(root, file), repo_path)
                    count += 1
            
            logger.info("Ingestion complete", files_processed=count)
            
            # Step 5: Get final statistics for user feedback
            node_count = list(self.memgraph.execute_and_fetch(
                "MATCH (n) RETURN count(n) as c"
            ))[0]['c']
            edge_count = list(self.memgraph.execute_and_fetch(
                "MATCH ()-[r]->() RETURN count(r) as c"
            ))[0]['c']
            
            return f"Ingestion Complete. Processed {count} files. Graph: {node_count} Nodes, {edge_count} Edges."
            
        except Exception as e:
            import traceback
            # Log full traceback for debugging
            logger.exception("Ingestion failed")
            return f"Error: {str(e)}"

    def _clone_repo(self, url: str) -> str:
        """
        Clone a Git repository to a temporary directory.
        
        Uses GitPython to perform the clone. The temp directory is created
        using Python's tempfile module, which places it in the OS temp location.
        
        Note: These temp directories are NOT automatically cleaned up.
        In production, you'd want a cleanup job or use S3 with lifecycle policies.
        
        Args:
            url: Git clone URL (HTTPS format)
            
        Returns:
            Path to the cloned repository
        """
        temp_dir = tempfile.mkdtemp()
        logger.info("Cloning repo", url=url, target=temp_dir)
        git.Repo.clone_from(url, temp_dir)
        return temp_dir

    def _clear_database(self):
        """
        Clear all nodes and relationships from the database.
        
        This implements "single-repo mode" - each ingestion starts fresh.
        DETACH DELETE removes both nodes and their relationships.
        
        Why single-repo mode?
        - Prevents context confusion for the LLM agent
        - Simplifies queries (no need to filter by repo)
        - Matches user mental model ("this repo")
        """
        self.memgraph.execute("MATCH (n) DETACH DELETE n")

    def _create_indexes(self):
        """
        Create database indexes for common query patterns.
        
        Indexes dramatically speed up:
        - MATCH (f:File {path: '...'}) - File lookups
        - MATCH (c:Class {name: '...'}) - Class lookups
        
        Without indexes, these queries scan all nodes (O(n)).
        With indexes, they're O(log n) or O(1).
        """
        self.memgraph.execute("CREATE INDEX ON :File(path);")
        self.memgraph.execute("CREATE INDEX ON :Class(name);")

    def _process_file(self, file_path: str, root_path: str):
        """
        Process a single file: create File node and parse structure.
        
        This method handles one file in the repository:
        1. Read file content
        2. Create a :File node in the graph (always)
        3. If parseable (Python/JS), extract Classes/Functions/Endpoints
        4. Create nodes for each extracted element with DEFINED_IN relationships
        
        Error Handling:
        - File read errors are caught and logged
        - Parsing failures don't stop the file from being added
        - Each file is processed independently
        
        Args:
            file_path: Absolute path to the file
            root_path: Root of the repository (for relative path calculation)
        """
        # Get file extension for language detection
        ext = os.path.splitext(file_path)[1]
        
        # Calculate relative path for cleaner storage
        # e.g., "/tmp/repo123/app/main.py" -> "app/main.py"
        rel_path = os.path.relpath(file_path, root_path)

        try:
            # Read file content (ignore encoding errors for binary files)
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content_str = f.read()
            
            # Create File Node (ALWAYS, even if parsing fails)
            # This ensures all files appear in the graph, not just parseable ones
            logger.debug("Creating File node", path=rel_path, ext=ext)
            query = "MERGE (f:File {path: $path}) SET f.language = $lang"
            self.memgraph.execute(query, {"path": rel_path, "lang": ext})

            # Parse file using Tree-sitter (only for supported extensions)
            tree = self.parser_service.parse(content_str, ext)
            if tree:
                logger.debug("Parsed file successfully", path=rel_path)
                
                # Extract structure and create nodes
                for type_, name, extra_info in self.parser_service.extract_structure(
                    tree.root_node, 
                    bytes(content_str, "utf8")
                ):
                    self._create_node(type_, name, rel_path, extra_info)
            else:
                # No parser for this extension (e.g., .md, .json, .yaml)
                logger.debug("No parser for extension or parse failed", path=rel_path, ext=ext)

        except Exception as e:
            # Log warning but continue processing other files
            logger.warning("Failed to process file", file=rel_path, error=str(e))

    def _create_node(self, type_: str, name: str, file_path: str, extra_info: str = None):
        """
        Create a code element node and link it to its file.
        
        This creates nodes like :Class, :Function, or :Endpoint and
        connects them to the :File node they're defined in.
        
        Args:
            type_: Node label ("Class", "Function", "Endpoint")
            name: Element name (e.g., "Book", "get_users")
            file_path: Relative path to the containing file
            extra_info: Optional metadata (route decorator for Endpoints)
            
        Graph Pattern Created:
            (n:Class {name: "Book"}) -[:DEFINED_IN]-> (f:File {path: "app/models.py"})
        """
        # Escape single quotes to prevent Cypher injection
        safe_name = name.replace("'", "\\'")
        safe_extra = extra_info.replace("'", "\\'") if extra_info else None
        
        if type_ == 'Endpoint' and safe_extra:
            # Store endpoints with their route decorator for API discovery
            # e.g., route = "@app.get('/books/{book_id}')"
            query = f"""
            MATCH (f:File {{path: '{file_path}'}})
            MERGE (n:Endpoint {{name: '{safe_name}', route: '{safe_extra}'}})
            MERGE (n)-[:DEFINED_IN]->(f)
            """
        else:
            # Standard node creation for Classes and Functions
            query = f"""
            MATCH (f:File {{path: '{file_path}'}})
            MERGE (n:{type_} {{name: '{safe_name}'}})
            MERGE (n)-[:DEFINED_IN]->(f)
            """
        self.memgraph.execute(query)

    def execute_cypher(self, query: str):
        """
        Execute a raw Cypher query and return results.
        
        This method is exposed via the MCP cypher_query tool,
        allowing the LangGraph agent to directly query the knowledge graph.
        
        Common queries used by the agent:
            - MATCH (f:File) RETURN f.path           -> List all files
            - MATCH (c:Class) RETURN c.name          -> List all classes
            - MATCH (e:Endpoint) RETURN e.name, e.route  -> List API endpoints
            
        Args:
            query: Valid Cypher query string
            
        Returns:
            List of result dicts
            
        Example:
            >>> execute_cypher("MATCH (c:Class) RETURN c.name LIMIT 5")
            [{'c.name': 'Book'}, {'c.name': 'User'}]
        """
        logger.debug("Executing Cypher", query=query)
        return list(self.memgraph.execute_and_fetch(query))
