"""
RAG System for SermonAudio Analytics

Implements Retrieval-Augmented Generation for querying sermon analytics data
using ChromaDB for vector storage and sentence transformers for embeddings.
"""

import logging
import uuid
from datetime import datetime
from typing import Any

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class SermonAnalyticsRAG:
    """RAG system for sermon analytics queries"""
    
    def __init__(self, db_path: str = "analytics_vector_db"):
        self.db_path = db_path
        self.embedding_model = None
        self.client = None
        self.collection = None
        self._initialize_components()
    
    def _initialize_components(self):
        """Initialize ChromaDB and embedding model"""
        try:
            # Initialize sentence transformer model with offline handling
            try:
                self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
                logger.info("Loaded embedding model: all-MiniLM-L6-v2")
            except Exception as model_error:
                logger.warning(f"Failed to load embedding model: {model_error}")
                # Use a simple fallback for offline mode
                self.embedding_model = None
                logger.info("Using offline mode - embeddings will be simulated")
            
            # Initialize ChromaDB client
            self.client = chromadb.PersistentClient(
                path=self.db_path,
                settings=Settings(anonymized_telemetry=False)
            )
            
            # Get or create collection
            self.collection = self.client.get_or_create_collection(
                name="sermon_analytics",
                metadata={"description": "SermonAudio analytics data for RAG queries"}
            )
            
            logger.info("RAG system initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize RAG system: {e}")
            raise
    
    def _get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Get embeddings for texts with fallback for offline mode"""
        if self.embedding_model is not None:
            try:
                return self.embedding_model.encode(texts).tolist()
            except Exception as e:
                logger.warning(f"Embedding model failed: {e}, using fallback")
        
        # Fallback: create simple hash-based embeddings for offline mode
        import hashlib
        import random
        
        embeddings = []
        for text in texts:
            # Create a deterministic but pseudo-random embedding based on text hash
            hash_value = hashlib.md5(text.encode()).hexdigest()
            random.seed(hash_value)
            # Create a 384-dimensional vector (same as all-MiniLM-L6-v2)
            embedding = [random.random() - 0.5 for _ in range(384)]
            embeddings.append(embedding)
        
        return embeddings
    
    def add_analytics_data(self, analytics_data: list[dict[str, Any]]) -> None:
        """Add analytics data to the vector database"""
        if not analytics_data:
            return
        
        documents = []
        metadatas = []
        ids = []
        
        for item in analytics_data:
            # Create a searchable text representation
            doc_text = self._create_document_text(item)
            documents.append(doc_text)
            
            # Prepare metadata (ChromaDB requires all values to be strings/numbers)
            metadata = self._prepare_metadata(item)
            metadatas.append(metadata)
            
            # Create unique ID
            sermon_id = item.get('sermon_id', str(uuid.uuid4()))
            ids.append(f"sermon_{sermon_id}")
        
        try:
            # Get embeddings for documents
            embeddings = self._get_embeddings(documents)
            
            # Add to collection with embeddings
            self.collection.add(
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids
            )
            
            logger.info(f"Added {len(documents)} analytics records to vector database")
            
        except Exception as e:
            logger.error(f"Failed to add analytics data: {e}")
            raise
    
    def _create_document_text(self, item: dict[str, Any]) -> str:
        """Create searchable text representation of analytics data"""
        text_parts = []
        
        # Basic information
        text_parts.append(f"Sermon: {item.get('title', 'Unknown Title')}")
        text_parts.append(f"Speaker: {item.get('speaker', 'Unknown Speaker')}")
        
        if item.get('series'):
            text_parts.append(f"Series: {item.get('series')}")
        
        if item.get('event_type'):
            text_parts.append(f"Event: {item.get('event_type')}")
        
        # Keywords
        if item.get('keywords'):
            keywords = item['keywords']
            if isinstance(keywords, list):
                text_parts.append(f"Keywords: {', '.join(keywords)}")
            else:
                text_parts.append(f"Keywords: {keywords}")
        
        # Analytics metrics
        text_parts.append(f"Views: {item.get('views', 0)}")
        text_parts.append(f"Listens: {item.get('listens', 0)}")
        text_parts.append(f"Downloads: {item.get('downloads', 0)}")
        text_parts.append(f"Duration: {item.get('duration_minutes', 0)} minutes")
        
        # Engagement metrics
        engagement = item.get('engagement_score', 0)
        text_parts.append(f"Engagement score: {engagement:.2f}")
        
        completion = item.get('watch_time_avg', 0)
        text_parts.append(f"Average completion rate: {completion:.1%}")
        
        # Date information
        if item.get('date_preached'):
            text_parts.append(f"Preached on: {item.get('date_preached')}")
        
        return ". ".join(text_parts)
    
    def _prepare_metadata(self, item: dict[str, Any]) -> dict[str, Any]:
        """Prepare metadata for ChromaDB (only strings and numbers allowed)"""
        metadata = {}
        
        # String fields
        string_fields = ['sermon_id', 'title', 'speaker', 'series', 'event_type', 'date_preached', 'date_uploaded']
        for field in string_fields:
            if item.get(field):
                metadata[field] = str(item[field])
        
        # Numeric fields
        numeric_fields = ['views', 'listens', 'downloads', 'duration_minutes', 'engagement_score', 'watch_time_avg']
        for field in numeric_fields:
            if field in item:
                try:
                    metadata[field] = float(item[field])
                except (ValueError, TypeError):
                    pass
        
        # Keywords as string
        if item.get('keywords'):
            keywords = item['keywords']
            if isinstance(keywords, list):
                metadata['keywords'] = ', '.join(str(k) for k in keywords)
            else:
                metadata['keywords'] = str(keywords)
        
        return metadata
    
    def query_analytics(self, question: str, n_results: int = 5) -> dict[str, Any]:
        """Query the analytics data using natural language"""
        try:
            # Get query embedding
            query_embeddings = self._get_embeddings([question])
            
            # Query the vector database
            results = self.collection.query(
                query_embeddings=query_embeddings,
                n_results=n_results
            )
            
            if not results['documents'] or not results['documents'][0]:
                return {
                    'question': question,
                    'answer': "I couldn't find any relevant sermon analytics data for your question.",
                    'relevant_sermons': [],
                    'data_source': 'rag_system'
                }
            
            # Generate answer based on retrieved data
            answer = self._generate_answer(question, results)
            
            return {
                'question': question,
                'answer': answer,
                'relevant_sermons': self._format_relevant_sermons(results),
                'data_source': 'rag_system',
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to query analytics: {e}")
            return {
                'question': question,
                'answer': f"Sorry, I encountered an error while searching: {e}",
                'relevant_sermons': [],
                'data_source': 'error'
            }
    
    def _generate_answer(self, question: str, results: dict) -> str:
        """Generate a natural language answer based on retrieved data"""
        documents = results['documents'][0]
        metadatas = results['metadatas'][0]
        
        if not documents:
            return "I couldn't find relevant data to answer your question."
        
        # Analyze the question to determine what type of answer to generate
        question_lower = question.lower()
        
        # Handle different types of questions
        if any(word in question_lower for word in ['average', 'avg', 'mean']):
            return self._generate_average_answer(question, metadatas)
        elif any(word in question_lower for word in ['top', 'best', 'highest', 'most']):
            return self._generate_top_answer(question, metadatas)
        elif any(word in question_lower for word in ['total', 'sum', 'overall']):
            return self._generate_total_answer(question, metadatas)
        elif any(word in question_lower for word in ['speaker', 'pastor', 'preacher']):
            return self._generate_speaker_answer(question, metadatas)
        elif any(word in question_lower for word in ['series']):
            return self._generate_series_answer(question, metadatas)
        else:
            return self._generate_general_answer(question, metadatas)
    
    def _generate_average_answer(self, question: str, metadatas: list[dict]) -> str:
        """Generate answer for average-type questions"""
        question_lower = question.lower()
        
        if 'view' in question_lower:
            views = [m.get('views', 0) for m in metadatas if m.get('views')]
            if views:
                avg_views = sum(views) / len(views)
                return f"The average number of views across the relevant sermons is {avg_views:.0f}."
        
        if 'listen' in question_lower:
            listens = [m.get('listens', 0) for m in metadatas if m.get('listens')]
            if listens:
                avg_listens = sum(listens) / len(listens)
                return f"The average number of listens across the relevant sermons is {avg_listens:.0f}."
        
        if 'engagement' in question_lower:
            engagement = [m.get('engagement_score', 0) for m in metadatas if m.get('engagement_score')]
            if engagement:
                avg_engagement = sum(engagement) / len(engagement)
                return f"The average engagement score across the relevant sermons is {avg_engagement:.2f}."
        
        if 'completion' in question_lower or 'watch time' in question_lower:
            completion = [m.get('watch_time_avg', 0) for m in metadatas if m.get('watch_time_avg')]
            if completion:
                avg_completion = sum(completion) / len(completion)
                return f"The average completion rate across the relevant sermons is {avg_completion:.1%}."
        
        return f"I found {len(metadatas)} relevant sermons but couldn't calculate the specific average you're looking for."
    
    def _generate_top_answer(self, question: str, metadatas: list[dict]) -> str:
        """Generate answer for top/best questions"""
        question_lower = question.lower()
        
        if 'view' in question_lower:
            sorted_by_views = sorted(metadatas, key=lambda x: x.get('views', 0), reverse=True)
            if sorted_by_views:
                top = sorted_by_views[0]
                return f"The sermon with the most views is '{top.get('title', 'Unknown')}' by {top.get('speaker', 'Unknown Speaker')} with {top.get('views', 0)} views."
        
        if 'engagement' in question_lower:
            sorted_by_engagement = sorted(metadatas, key=lambda x: x.get('engagement_score', 0), reverse=True)
            if sorted_by_engagement:
                top = sorted_by_engagement[0]
                return f"The sermon with the highest engagement is '{top.get('title', 'Unknown')}' by {top.get('speaker', 'Unknown Speaker')} with an engagement score of {top.get('engagement_score', 0):.2f}."
        
        return f"I found {len(metadatas)} relevant sermons. Could you be more specific about what metric you'd like to see ranked?"
    
    def _generate_total_answer(self, question: str, metadatas: list[dict]) -> str:
        """Generate answer for total/sum questions"""
        question_lower = question.lower()
        
        if 'view' in question_lower:
            total_views = sum(m.get('views', 0) for m in metadatas)
            return f"The total number of views across {len(metadatas)} relevant sermons is {total_views:,}."
        
        if 'listen' in question_lower:
            total_listens = sum(m.get('listens', 0) for m in metadatas)
            return f"The total number of listens across {len(metadatas)} relevant sermons is {total_listens:,}."
        
        return f"I found {len(metadatas)} relevant sermons. Could you specify which metric you'd like totaled?"
    
    def _generate_speaker_answer(self, question: str, metadatas: list[dict]) -> str:
        """Generate answer for speaker-related questions"""
        speaker_stats = {}
        for m in metadatas:
            speaker = m.get('speaker', 'Unknown')
            if speaker not in speaker_stats:
                speaker_stats[speaker] = {'count': 0, 'total_views': 0, 'total_listens': 0}
            speaker_stats[speaker]['count'] += 1
            speaker_stats[speaker]['total_views'] += m.get('views', 0)
            speaker_stats[speaker]['total_listens'] += m.get('listens', 0)
        
        # Sort by most sermons
        sorted_speakers = sorted(speaker_stats.items(), key=lambda x: x[1]['count'], reverse=True)
        
        if sorted_speakers:
            top_speaker, stats = sorted_speakers[0]
            return f"Among the relevant sermons, {top_speaker} has {stats['count']} sermons with {stats['total_views']:,} total views and {stats['total_listens']:,} total listens."
        
        return "I couldn't find speaker information in the relevant sermons."
    
    def _generate_series_answer(self, question: str, metadatas: list[dict]) -> str:
        """Generate answer for series-related questions"""
        series_stats = {}
        for m in metadatas:
            series = m.get('series')
            if series:
                if series not in series_stats:
                    series_stats[series] = {'count': 0, 'total_views': 0}
                series_stats[series]['count'] += 1
                series_stats[series]['total_views'] += m.get('views', 0)
        
        if series_stats:
            # Sort by total views
            sorted_series = sorted(series_stats.items(), key=lambda x: x[1]['total_views'], reverse=True)
            top_series, stats = sorted_series[0]
            return f"The top performing series is '{top_series}' with {stats['count']} sermons and {stats['total_views']:,} total views."
        
        return "I couldn't find series information in the relevant sermons."
    
    def _generate_general_answer(self, question: str, metadatas: list[dict]) -> str:
        """Generate a general answer based on the data"""
        if not metadatas:
            return "I couldn't find relevant data to answer your question."
        
        total_views = sum(m.get('views', 0) for m in metadatas)
        total_listens = sum(m.get('listens', 0) for m in metadatas)
        
        return f"I found {len(metadatas)} relevant sermons with a total of {total_views:,} views and {total_listens:,} listens. The sermons cover various topics and speakers."
    
    def _format_relevant_sermons(self, results: dict) -> list[dict[str, Any]]:
        """Format relevant sermons for display"""
        metadatas = results['metadatas'][0] if results['metadatas'] else []
        distances = results['distances'][0] if results['distances'] else []
        
        sermons = []
        for i, metadata in enumerate(metadatas):
            sermon = {
                'title': metadata.get('title', 'Unknown'),
                'speaker': metadata.get('speaker', 'Unknown'),
                'views': metadata.get('views', 0),
                'listens': metadata.get('listens', 0),
                'relevance_score': 1 - distances[i] if i < len(distances) else 0
            }
            sermons.append(sermon)
        
        return sermons
    
    def get_collection_stats(self) -> dict[str, Any]:
        """Get statistics about the vector database collection"""
        try:
            count = self.collection.count()
            return {
                'total_documents': count,
                'collection_name': self.collection.name,
                'last_updated': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {'error': str(e)}
    
    def clear_collection(self) -> None:
        """Clear all data from the collection"""
        try:
            # Delete the collection and recreate it
            self.client.delete_collection(name="sermon_analytics")
            self.collection = self.client.get_or_create_collection(
                name="sermon_analytics",
                metadata={"description": "SermonAudio analytics data for RAG queries"}
            )
            logger.info("Collection cleared successfully")
        except Exception as e:
            logger.error(f"Failed to clear collection: {e}")
            raise


def initialize_rag_system_with_data(analytics_data: list[dict[str, Any]]) -> SermonAnalyticsRAG:
    """Initialize RAG system and populate with analytics data"""
    rag = SermonAnalyticsRAG()
    
    if analytics_data:
        rag.add_analytics_data(analytics_data)
    
    return rag
