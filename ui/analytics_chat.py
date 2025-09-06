"""
Chat Interface for SermonAudio Analytics

Provides a conversational interface for querying sermon analytics data
using the RAG system and LLM integration.
"""

import logging
from datetime import datetime
from typing import Any, Dict

import streamlit as st

from ui.rag_system import SermonAnalyticsRAG, initialize_rag_system_with_data
from ui.sermonaudio_analytics import SermonAudioAnalytics

logger = logging.getLogger(__name__)


class AnalyticsChatInterface:
    """Chat interface for sermon analytics queries"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.rag_system: SermonAnalyticsRAG | None = None
        self.analytics = SermonAudioAnalytics()
        self._initialize_session_state()

    def _initialize_session_state(self):
        """Initialize Streamlit session state variables"""
        if 'chat_history' not in st.session_state:
            st.session_state.chat_history = []

        if 'rag_initialized' not in st.session_state:
            st.session_state.rag_initialized = False

        if 'analytics_data' not in st.session_state:
            st.session_state.analytics_data = []

    def initialize_rag_system(self, force_refresh: bool = False) -> bool:
        """Initialize the RAG system with analytics data"""
        try:
            with st.spinner("Loading analytics data and initializing RAG system..."):
                # Get analytics data
                if force_refresh or not st.session_state.analytics_data:
                    st.session_state.analytics_data = self.analytics.get_all_sermon_analytics()

                # Initialize RAG system with embedding configuration
                if not st.session_state.rag_initialized or force_refresh:
                    embedding_config = self.config.get('embeddings', {})
                    self.rag_system = initialize_rag_system_with_data(
                        st.session_state.analytics_data,
                        embedding_config=embedding_config
                    )
                    )
                    st.session_state.rag_initialized = True
                    logger.info("RAG system initialized successfully")

                return True

        except Exception as e:
            logger.error(f"Failed to initialize RAG system: {e}")
            st.error(f"Failed to initialize chat system: {e}")
            return False

    def render_chat_interface(self):
        """Render the chat interface"""
        st.subheader("🤖 Analytics Chat Assistant")
        st.write("Ask questions about your sermon analytics data using natural language.")

        # Initialize RAG system if needed
        if not st.session_state.rag_initialized:
            if st.button("Initialize Chat System", key="init_rag"):
                self.initialize_rag_system()

        if not st.session_state.rag_initialized:
            st.info("👆 Click the button above to initialize the chat system.")
            return

        # Chat interface
        col1, col2 = st.columns([4, 1])

        with col1:
            user_question = st.text_input(
                "Ask a question about your sermons:",
                placeholder=(
                    "e.g., What are the most popular sermons? "
                    "Which speaker has the highest engagement?"
                ),
                key="chat_input"
            )

        with col2:
            send_button = st.button("Send", key="send_message")
            refresh_button = st.button("🔄", help="Refresh data", key="refresh_data")

        # Handle refresh
        if refresh_button:
            with st.spinner("Refreshing analytics data..."):
                self.initialize_rag_system(force_refresh=True)
                st.success("Data refreshed!")
                st.rerun()

        # Handle message sending
        if send_button and user_question:
            self._process_question(user_question)
            st.rerun()

        # Display chat history
        self._render_chat_history()

        # Show data statistics
        self._render_data_stats()

    def _process_question(self, question: str):
        """Process a user question and get response"""
        if not self.rag_system:
            self.rag_system = SermonAnalyticsRAG()

        try:
            # Add user message to history
            st.session_state.chat_history.append({
                'type': 'user',
                'content': question,
                'timestamp': datetime.now()
            })

            with st.spinner("Searching for answer..."):
                # Query the RAG system
                response = self.rag_system.query_analytics(question)

                # Add assistant response to history
                st.session_state.chat_history.append({
                    'type': 'assistant',
                    'content': response['answer'],
                    'relevant_sermons': response.get('relevant_sermons', []),
                    'timestamp': datetime.now()
                })

                logger.info(f"Processed question: {question}")

        except Exception as e:
            logger.error(f"Failed to process question: {e}")
            st.session_state.chat_history.append({
                'type': 'error',
                'content': f"Sorry, I encountered an error: {e}",
                'timestamp': datetime.now()
            })

    def _render_chat_history(self):
        """Render the chat history"""
        if not st.session_state.chat_history:
            st.info("Start a conversation by asking a question about your sermon analytics!")
            return

        st.subheader("Conversation")

        # Display messages in reverse order (newest first)
        for _, message in enumerate(reversed(st.session_state.chat_history)):
            if message['type'] == 'user':
                with st.chat_message("user"):
                    st.write(message['content'])

            elif message['type'] == 'assistant':
                with st.chat_message("assistant"):
                    st.write(message['content'])

                    # Show relevant sermons if available
                    if message.get('relevant_sermons'):
                        with st.expander("📊 Relevant Sermons"):
                            self._render_relevant_sermons(message['relevant_sermons'])

            elif message['type'] == 'error':
                with st.chat_message("assistant"):
                    st.error(message['content'])

        # Clear chat button
        if st.button("Clear Chat History", key="clear_chat"):
            st.session_state.chat_history = []
            st.rerun()

    def _render_relevant_sermons(self, sermons: list[dict[str, Any]]):
        """Render relevant sermons data"""
        if not sermons:
            return

        for sermon in sermons[:5]:  # Show top 5 relevant sermons
            col1, col2, col3 = st.columns([3, 1, 1])

            with col1:
                st.write(f"**{sermon.get('title', 'Unknown Title')}**")
                st.write(f"by {sermon.get('speaker', 'Unknown Speaker')}")

            with col2:
                st.metric("Views", f"{sermon.get('views', 0):,}")

            with col3:
                st.metric("Listens", f"{sermon.get('listens', 0):,}")

    def _render_data_stats(self):
        """Render statistics about the loaded data"""
        if self.rag_system:
            try:
                stats = self.rag_system.get_collection_stats()
                if 'error' not in stats:
                    st.sidebar.subheader("📈 Data Status")
                    st.sidebar.metric("Total Sermons", stats.get('total_documents', 0))
                    st.sidebar.write(f"Last updated: {stats.get('last_updated', 'Unknown')[:19]}")
            except Exception as e:
                logger.error(f"Failed to get collection stats: {e}")

    def render_example_questions(self):
        """Render example questions to help users get started"""
        st.subheader("💡 Example Questions")
        st.write("Here are some questions you can ask:")

        example_questions = [
            "What are the most popular sermons by views?",
            "Which speaker has the highest engagement scores?",
            "What's the average completion rate across all sermons?",
            "Show me sermons about faith with high engagement",
            "What are the top performing sermon series?",
            "Which sermons have the most downloads?",
            "What's the total number of views across all sermons?",
            "Show me recent sermons with high listen counts"
        ]

        for question in example_questions:
            if st.button(question, key=f"example_{hash(question)}"):
                # Set the question in the input field
                st.session_state.chat_input = question
                self._process_question(question)
                st.rerun()

    def render_chat_settings(self):
        """Render chat settings and configuration"""
        with st.sidebar:
            st.subheader("🔧 Chat Settings")

            # RAG system settings
            if st.button("Reset Chat System", key="reset_rag"):
                if self.rag_system:
                    try:
                        self.rag_system.clear_collection()
                        st.session_state.rag_initialized = False
                        st.session_state.analytics_data = []
                        st.success("Chat system reset!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to reset: {e}")

            # Download chat history
            if st.button("Download Chat History", key="download_chat"):
                self._download_chat_history()
            
            # Embedding provider information
            st.subheader("🔧 Embedding Provider")
            if self.rag_system:
                try:
                    provider_info = self.rag_system.get_embedding_provider_info()
                    current = provider_info.get('current_provider', {})
                    
                    st.write(f"**Provider:** {current.get('provider', 'Unknown')}")
                    st.write(f"**Model:** {current.get('model', 'Unknown')}")
                    st.write(f"**Dimensions:** {current.get('dimensions', 'Unknown')}")
                    st.write(f"**Fallbacks:** {provider_info.get('available_fallbacks', 0)}")
                    
                except Exception as e:
                    st.error(f"Failed to get provider info: {e}")
            else:
                st.info("Initialize chat system to see embedding provider information")

    def _download_chat_history(self):
        """Prepare chat history for download"""
        if not st.session_state.chat_history:
            st.warning("No chat history to download")
            return

        # Format chat history as text
        chat_text = "Sermon Analytics Chat History\n"
        chat_text += "=" * 40 + "\n\n"

        for message in st.session_state.chat_history:
            timestamp = message['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
            msg_type = message['type'].upper()
            content = message['content']

            chat_text += f"[{timestamp}] {msg_type}:\n{content}\n\n"

            if message.get('relevant_sermons'):
                chat_text += "Relevant Sermons:\n"
                for sermon in message['relevant_sermons']:
                    title = sermon.get('title', 'Unknown')
                    speaker = sermon.get('speaker', 'Unknown')
                    chat_text += f"  - {title} by {speaker}\n"
                chat_text += "\n"

        # Provide download
        st.download_button(
            label="📥 Download Chat History",
            data=chat_text,
            file_name=f"sermon_analytics_chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain",
            key="download_chat_file"
        )


def render_analytics_chat_tab():
    """Main function to render the analytics chat tab"""
    chat_interface = AnalyticsChatInterface()

    # Main chat interface
    chat_interface.render_chat_interface()

    # Sidebar settings
    chat_interface.render_chat_settings()

    # Example questions in an expander
    with st.expander("💡 Example Questions", expanded=False):
        chat_interface.render_example_questions()


if __name__ == "__main__":
    # For testing purposes
    st.set_page_config(
        page_title="Analytics Chat",
        page_icon="🤖",
        layout="wide"
    )

    render_analytics_chat_tab()
