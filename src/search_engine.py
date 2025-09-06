"""
Sermon Search Engine - Advanced search functionality for sermon content

Provides comprehensive search capabilities across sermons with relevance scoring,
auto-complete suggestions, and advanced filtering as specified in requirements.
"""

import logging
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Search result with relevance scoring"""
    sermon_id: str
    title: str
    speaker: str
    relevance_score: float
    snippet: str
    match_type: str  # 'title', 'transcript', 'description', 'hashtags'
    sermon_data: dict[str, Any]


class SermonSearchEngine:
    """
    Advanced search across sermon content with relevance scoring and suggestions.
    
    Provides the search functionality as specified in the requirements:
    - Full-text search across titles, transcripts, and descriptions
    - Relevance scoring and ranking
    - Auto-complete suggestions
    - Advanced filtering capabilities
    """

    def __init__(self, database_path: str = "sermon_processor.db"):
        """
        Initialize search engine with database connection.
        
        Args:
            database_path: Path to SQLite database
        """
        self.database_path = Path(database_path)
        self.index = self.build_search_index()
        logger.info(f"Search engine initialized with database: {database_path}")

    def build_search_index(self) -> dict[str, Any]:
        """
        Build in-memory search index for faster queries.
        
        Returns:
            Search index dictionary
        """
        index = {
            'terms': set(),
            'speakers': set(),
            'titles': set(),
            'topics': set()
        }

        try:
            with sqlite3.connect(self.database_path) as conn:
                conn.row_factory = sqlite3.Row

                # Index all searchable content
                cursor = conn.execute("""
                    SELECT s.title, s.speaker, sc.transcript_text, sc.description, sc.hashtags
                    FROM sermons s
                    LEFT JOIN sermon_content sc ON s.id = sc.sermon_id
                """)

                for row in cursor:
                    # Extract terms for suggestions
                    if row['title']:
                        index['titles'].add(row['title'].lower())
                        index['terms'].update(self._extract_terms(row['title']))

                    if row['speaker']:
                        index['speakers'].add(row['speaker'].lower())

                    if row['transcript_text']:
                        index['terms'].update(self._extract_terms(row['transcript_text']))

                    if row['description']:
                        index['terms'].update(self._extract_terms(row['description']))

                    if row['hashtags']:
                        index['terms'].update(self._extract_terms(row['hashtags']))

        except Exception as e:
            logger.warning(f"Failed to build search index: {e}")

        logger.info(f"Search index built: {len(index['terms'])} terms, {len(index['speakers'])} speakers")
        return index

    def _extract_terms(self, text: str) -> list[str]:
        """Extract searchable terms from text"""
        if not text:
            return []

        # Clean and split text into terms
        text = text.lower()
        # Remove punctuation and split
        terms = re.findall(r'\b\w+\b', text)
        # Filter out short words
        terms = [term for term in terms if len(term) >= 3]
        return terms

    def search(self, query: str, filters: dict[str, Any] | None = None) -> list[SearchResult]:
        """
        Advanced search across sermon content with relevance scoring.
        
        Args:
            query: Search query string
            filters: Optional filters (speaker, date_range, event_type, etc.)
            
        Returns:
            List of SearchResult objects ranked by relevance
        """
        if not query.strip():
            return []

        try:
            with sqlite3.connect(self.database_path) as conn:
                conn.row_factory = sqlite3.Row

                # Try FTS search first
                fts_results = self._fts_search(conn, query, filters)
                if fts_results:
                    return fts_results

                # Fallback to LIKE search
                return self._like_search(conn, query, filters)

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def _fts_search(self, conn: sqlite3.Connection, query: str, filters: dict[str, Any] | None) -> list[SearchResult]:
        """Full-text search using FTS5 virtual table"""
        try:
            # Build FTS query
            fts_query = self._build_fts_query(query)

            sql = """
                SELECT s.*, sc.transcript_text, sc.description, sc.hashtags,
                       snippet(sermon_search, 2, '<mark>', '</mark>', '...', 32) as snippet,
                       bm25(sermon_search) as relevance_score
                FROM sermon_search 
                JOIN sermons s ON sermon_search.sermon_id = s.id
                LEFT JOIN sermon_content sc ON s.id = sc.sermon_id
                WHERE sermon_search MATCH ?
            """

            params = [fts_query]

            # Apply filters
            if filters:
                sql, params = self._apply_filters(sql, params, filters)

            sql += " ORDER BY relevance_score DESC LIMIT 50"

            cursor = conn.execute(sql, params)
            results = []

            for row in cursor:
                # Determine match type from snippet
                match_type = self._determine_match_type(row['snippet'], row)

                result = SearchResult(
                    sermon_id=row['id'],
                    title=row['title'] or 'Untitled',
                    speaker=row['speaker'] or 'Unknown',
                    relevance_score=abs(row['relevance_score']),  # BM25 scores are negative
                    snippet=row['snippet'] or '',
                    match_type=match_type,
                    sermon_data=dict(row)
                )
                results.append(result)

            return results

        except Exception as e:
            logger.warning(f"FTS search failed: {e}")
            return []

    def _like_search(self, conn: sqlite3.Connection, query: str, filters: dict[str, Any] | None) -> list[SearchResult]:
        """Fallback LIKE-based search"""
        search_terms = query.lower().split()

        sql = """
            SELECT s.*, sc.transcript_text, sc.description, sc.hashtags
            FROM sermons s
            LEFT JOIN sermon_content sc ON s.id = sc.sermon_id
            WHERE (
                s.title LIKE ? OR
                s.speaker LIKE ? OR
                sc.transcript_text LIKE ? OR
                sc.description LIKE ? OR
                sc.hashtags LIKE ?
            )
        """

        # Create LIKE patterns for each term
        like_pattern = f"%{' '.join(search_terms)}%"
        params = [like_pattern] * 5

        # Apply filters
        if filters:
            sql, params = self._apply_filters(sql, params, filters)

        sql += " ORDER BY s.recorded_date DESC LIMIT 50"

        cursor = conn.execute(sql, params)
        results = []

        for row in cursor:
            # Calculate simple relevance score
            relevance_score = self._calculate_like_relevance(query, row)

            # Generate snippet
            snippet = self._generate_snippet(query, row)

            # Determine match type
            match_type = self._determine_match_type_like(query, row)

            result = SearchResult(
                sermon_id=row['id'],
                title=row['title'] or 'Untitled',
                speaker=row['speaker'] or 'Unknown',
                relevance_score=relevance_score,
                snippet=snippet,
                match_type=match_type,
                sermon_data=dict(row)
            )
            results.append(result)

        # Sort by relevance
        results.sort(key=lambda x: x.relevance_score, reverse=True)
        return results

    def _build_fts_query(self, query: str) -> str:
        """Build FTS5 query from user input"""
        # Clean and prepare query for FTS
        terms = query.strip().split()

        # Handle phrases in quotes
        if '"' in query:
            return query  # Return as-is for phrase search

        # Build OR query for multiple terms
        if len(terms) > 1:
            return ' OR '.join(terms)

        return query

    def _apply_filters(self, sql: str, params: list[Any], filters: dict[str, Any]) -> tuple[str, list[Any]]:
        """Apply search filters to SQL query"""
        where_clauses = []

        if filters.get('speaker'):
            where_clauses.append("s.speaker LIKE ?")
            params.append(f"%{filters['speaker']}%")

        if filters.get('event_type'):
            where_clauses.append("s.event_type = ?")
            params.append(filters['event_type'])

        if filters.get('date_from'):
            where_clauses.append("s.recorded_date >= ?")
            params.append(filters['date_from'])

        if filters.get('date_to'):
            where_clauses.append("s.recorded_date <= ?")
            params.append(filters['date_to'])

        if filters.get('has_qa_segments'):
            sql = sql.replace(
                "LEFT JOIN sermon_content sc ON s.id = sc.sermon_id",
                "LEFT JOIN sermon_content sc ON s.id = sc.sermon_id LEFT JOIN processing_info pi ON s.id = pi.sermon_id"
            )
            where_clauses.append("pi.qa_segments_count > 0")

        if where_clauses:
            sql += " AND " + " AND ".join(where_clauses)

        return sql, params

    def _calculate_like_relevance(self, query: str, row: sqlite3.Row) -> float:
        """Calculate relevance score for LIKE search results"""
        score = 0.0
        query_lower = query.lower()

        # Title matches are highest priority
        if row['title'] and query_lower in row['title'].lower():
            score += 10.0

        # Speaker matches
        if row['speaker'] and query_lower in row['speaker'].lower():
            score += 5.0

        # Description matches
        if row['description'] and query_lower in row['description'].lower():
            score += 3.0

        # Hashtag matches
        if row['hashtags'] and query_lower in row['hashtags'].lower():
            score += 2.0

        # Transcript matches (lower priority due to length)
        if row['transcript_text'] and query_lower in row['transcript_text'].lower():
            score += 1.0

        return score

    def _generate_snippet(self, query: str, row: sqlite3.Row) -> str:
        """Generate search snippet for LIKE search"""
        query_lower = query.lower()

        # Try to find best match for snippet
        for field in ['description', 'transcript_text']:
            text = row[field]
            if text and query_lower in text.lower():
                # Find the position and create snippet
                pos = text.lower().find(query_lower)
                start = max(0, pos - 50)
                end = min(len(text), pos + len(query) + 50)
                snippet = text[start:end]

                # Highlight the match
                snippet = re.sub(
                    re.escape(query),
                    f'<mark>{query}</mark>',
                    snippet,
                    flags=re.IGNORECASE
                )

                return f"...{snippet}..." if start > 0 else snippet

        return ""

    def _determine_match_type(self, snippet: str, row: sqlite3.Row) -> str:
        """Determine what type of field matched in FTS search"""
        if '<mark>' in snippet:
            return 'transcript'
        elif row['title'] and any(term in row['title'].lower() for term in snippet.lower().split()):
            return 'title'
        elif row['description'] and any(term in row['description'].lower() for term in snippet.lower().split()):
            return 'description'
        elif row['hashtags'] and any(term in row['hashtags'].lower() for term in snippet.lower().split()):
            return 'hashtags'
        else:
            return 'transcript'

    def _determine_match_type_like(self, query: str, row: sqlite3.Row) -> str:
        """Determine match type for LIKE search"""
        query_lower = query.lower()

        if row['title'] and query_lower in row['title'].lower():
            return 'title'
        elif row['speaker'] and query_lower in row['speaker'].lower():
            return 'speaker'
        elif row['description'] and query_lower in row['description'].lower():
            return 'description'
        elif row['hashtags'] and query_lower in row['hashtags'].lower():
            return 'hashtags'
        else:
            return 'transcript'

    def get_search_suggestions(self, partial_query: str, limit: int = 10) -> list[str]:
        """
        Get auto-complete suggestions for search queries.
        
        Args:
            partial_query: Partial search query
            limit: Maximum number of suggestions
            
        Returns:
            List of suggested completions
        """
        if len(partial_query) < 2:
            return []

        partial_lower = partial_query.lower()
        suggestions = set()

        # Search in indexed terms
        for term in self.index['terms']:
            if term.startswith(partial_lower):
                suggestions.add(term)
                if len(suggestions) >= limit:
                    break

        # Search in speaker names
        for speaker in self.index['speakers']:
            if speaker.startswith(partial_lower):
                suggestions.add(speaker)
                if len(suggestions) >= limit:
                    break

        # Search in titles
        for title in self.index['titles']:
            if partial_lower in title:
                suggestions.add(title)
                if len(suggestions) >= limit:
                    break

        return sorted(list(suggestions))[:limit]

    def refresh_index(self):
        """Refresh the search index from database"""
        self.index = self.build_search_index()
        logger.info("Search index refreshed")

    def get_search_stats(self) -> dict[str, Any]:
        """Get search engine statistics"""
        return {
            'indexed_terms': len(self.index['terms']),
            'indexed_speakers': len(self.index['speakers']),
            'indexed_titles': len(self.index['titles']),
            'database_path': str(self.database_path)
        }


# Global search engine instance
_search_engine = None

def get_search_engine(database_path: str = "sermon_processor.db") -> SermonSearchEngine:
    """Get global search engine instance"""
    global _search_engine
    if _search_engine is None:
        _search_engine = SermonSearchEngine(database_path)
    return _search_engine
