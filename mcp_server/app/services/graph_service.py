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
    """
    def __init__(self):
        self.memgraph = Memgraph(
            host=settings.MEMGRAPH_HOST, 
            port=settings.MEMGRAPH_PORT,
            username=settings.MEMGRAPH_USER,
            password=settings.MEMGRAPH_PASSWORD
        )
        self.parser_service = ParserService()
    
    def check_connection(self):
        try:
            # Simple query to check connection
            self.memgraph.execute("RETURN 1")
            return True
        except Exception as e:
            logger.error("Memgraph connection failed", error=str(e))
            return False

    def ingest_repository(self, source: str) -> str:
        """
        Clones and ingests a repository.
        """
        logger.info("Starting ingestion", source=source)
        
        try:
            if source.startswith("http"):
                repo_path = self._clone_repo(source)
            else:
                repo_path = source
            
            if not os.path.exists(repo_path):
                return f"Error: Path {repo_path} does not exist."

            self._clear_database()
            self._create_indexes()

            count = 0
            for root, _, files in os.walk(repo_path):
                if ".git" in root: continue
                for file in files:
                    self._process_file(os.path.join(root, file), repo_path)
                    count += 1
            
            logger.info("Ingestion complete", files_processed=count)
            
            # Get Verification Stats
            node_count = list(self.memgraph.execute_and_fetch("MATCH (n) RETURN count(n) as c"))[0]['c']
            edge_count = list(self.memgraph.execute_and_fetch("MATCH ()-[r]->() RETURN count(r) as c"))[0]['c']
            
            return f"Ingestion Complete. Processed {count} files. Graph: {node_count} Nodes, {edge_count} Edges."
            
        except Exception as e:
            import traceback
            logger.exception("Ingestion failed")  # Log full traceback
            return f"Error: {str(e)}"

    def _clone_repo(self, url: str) -> str:
        temp_dir = tempfile.mkdtemp()
        logger.info("Cloning repo", url=url, target=temp_dir)
        git.Repo.clone_from(url, temp_dir)
        return temp_dir

    def _clear_database(self):
        self.memgraph.execute("MATCH (n) DETACH DELETE n")

    def _create_indexes(self):
        self.memgraph.execute("CREATE INDEX ON :File(path);")
        self.memgraph.execute("CREATE INDEX ON :Class(name);")

    def _process_file(self, file_path: str, root_path: str):
        ext = os.path.splitext(file_path)[1]
        rel_path = os.path.relpath(file_path, root_path)

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content_str = f.read()
            
            # Create File Node (ALWAYS, even if parsing fails)
            logger.debug("Creating File node", path=rel_path, ext=ext)
            query = "MERGE (f:File {path: $path}) SET f.language = $lang"
            self.memgraph.execute(query, {"path": rel_path, "lang": ext})

            # Parse (only for supported extensions)
            tree = self.parser_service.parse(content_str, ext)
            if tree:
                logger.debug("Parsed file successfully", path=rel_path)
                for type_, name, extra_info in self.parser_service.extract_structure(tree.root_node, bytes(content_str, "utf8")):
                    self._create_node(type_, name, rel_path, extra_info)
            else:
                logger.debug("No parser for extension or parse failed", path=rel_path, ext=ext)

        except Exception as e:
            logger.warning("Failed to process file", file=rel_path, error=str(e))

    def _create_node(self, type_: str, name: str, file_path: str, extra_info: str = None):
        # Escape single quotes in name and extra_info to prevent injection
        safe_name = name.replace("'", "\\'")
        safe_extra = extra_info.replace("'", "\\'") if extra_info else None
        
        if type_ == 'Endpoint' and safe_extra:
            # Store endpoints with their route decorator
            query = f"""
            MATCH (f:File {{path: '{file_path}'}})
            MERGE (n:Endpoint {{name: '{safe_name}', route: '{safe_extra}'}})
            MERGE (n)-[:DEFINED_IN]->(f)
            """
        else:
            query = f"""
            MATCH (f:File {{path: '{file_path}'}})
            MERGE (n:{type_} {{name: '{safe_name}'}})
            MERGE (n)-[:DEFINED_IN]->(f)
            """
        self.memgraph.execute(query)

    def execute_cypher(self, query: str):
        logger.debug("Executing Cypher", query=query)
        return list(self.memgraph.execute_and_fetch(query))
