"""
Sermon Viewer Page - Detailed sermon viewing with Q&A highlights

Provides comprehensive sermon viewing with:
- Full transcript display with Q&A highlighting
- Audio player with Q&A segment navigation
- Detailed processing information
- Content editing capabilities
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional, Any
import sys
from pathlib import Path
import json

# Add src and ui directories to path
ui_dir = Path(__file__).parent.parent
src_dir = ui_dir.parent / "src"
sys.path.insert(0, str(ui_dir))
sys.path.insert(0, str(src_dir))

from database import SermonRepository, get_db

# Try to import PDF generation (optional)
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    import io
    pdf_available = True
except ImportError:
    pdf_available = False

# Page configuration
st.set_page_config(page_title="Sermon Viewer", page_icon="📖", layout="wide")

def format_time(seconds):
    """Format time in seconds to MM:SS format"""
    if not seconds:
        return "00:00"
    
    minutes = int(seconds // 60)
    seconds = int(seconds % 60)
    return f"{minutes:02d}:{seconds:02d}"

def generate_pdf_transcript(sermon):
    """Generate PDF transcript with Q&A highlighting"""
    if not pdf_available:
        return None
    
    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []
        
        # Title page
        title_style = styles['Title']
        title = sermon.get('title', 'Untitled Sermon')
        speaker = sermon.get('speaker', 'Unknown Speaker')
        date = sermon.get('recorded_date', 'Unknown Date')
        
        story.append(Paragraph(title, title_style))
        story.append(Spacer(1, 0.2*inch))
        story.append(Paragraph(f"Speaker: {speaker}", styles['Normal']))
        story.append(Paragraph(f"Date: {date}", styles['Normal']))
        story.append(Spacer(1, 0.5*inch))
        
        # Q&A segments summary
        qa_segments = sermon.get('processing_info', {}).get('qa_segments', [])
        if qa_segments:
            story.append(Paragraph("Q&A Segments Detected:", styles['Heading2']))
            for i, segment in enumerate(qa_segments, 1):
                start_time = format_time(segment.get('start_time', 0))
                end_time = format_time(segment.get('end_time', 0))
                gain = segment.get('gain_applied', 0)
                story.append(Paragraph(
                    f"Segment {i}: {start_time} - {end_time} (+{gain:.1f}dB boost)",
                    styles['Normal']
                ))
            story.append(Spacer(1, 0.3*inch))
        
        # Transcript content
        content = sermon.get('content', {})
        transcript = content.get('transcript_text', '')
        if transcript:
            story.append(Paragraph("Full Transcript:", styles['Heading2']))
            story.append(Spacer(1, 0.1*inch))
            
            # Split transcript into paragraphs for better formatting
            paragraphs = transcript.split('\n\n')
            for para in paragraphs:
                if para.strip():
                    story.append(Paragraph(para.strip(), styles['Normal']))
                    story.append(Spacer(1, 0.1*inch))
        
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
        
    except Exception as e:
        st.error(f"PDF generation failed: {e}")
        return None
    """
    Format transcript with Q&A segment highlighting.
    
    Note: This is a simplified implementation. For precise highlighting,
    we would need word-level timestamps from the speech recognition.
    """
    if not transcript_text or not qa_segments:
        return transcript_text
    
    # For now, just add markers at approximate locations
    # In a real implementation, this would use word-level timestamps
    highlighted_text = transcript_text
    
    # Add Q&A segment indicators
    qa_indicators = []
    for i, segment in enumerate(qa_segments, 1):
        start_time = segment.get('start_time', 0)
        end_time = segment.get('end_time', 0)
        segment_type = segment.get('segment_type', 'question')
        
        indicator = f"""
        <div style="background-color: #e8f4fd; border-left: 4px solid #1f77b4; padding: 10px; margin: 10px 0;">
            <strong>🗣️ Q&A Segment {i} ({segment_type.title()})</strong><br>
            <small>Time: {format_time(start_time)} - {format_time(end_time)}</small>
        </div>
        """
        qa_indicators.append(indicator)
    
    # Insert Q&A indicators at the beginning for now
    if qa_indicators:
        highlighted_text = "".join(qa_indicators) + "\n\n" + highlighted_text
    
    return highlighted_text

def show_audio_player(sermon):
    """Display audio player with Q&A segment navigation"""
    st.subheader("🎵 Audio Player")
    
    # Get audio file path
    audio_path = sermon.get('file_paths', {}).get('processed_audio')
    if not audio_path:
        audio_path = sermon.get('file_paths', {}).get('original_audio')
    
    if audio_path and Path(audio_path).exists():
        # Main audio player
        st.audio(audio_path)
        
        # Q&A segment navigation
        qa_segments = sermon.get('processing_info', {}).get('qa_segments', [])
        if qa_segments:
            st.subheader("🗣️ Q&A Segments")
            
            # Create columns for segment buttons
            cols = st.columns(min(len(qa_segments), 4))
            
            for i, segment in enumerate(qa_segments):
                col_idx = i % 4
                with cols[col_idx]:
                    start_time = segment.get('start_time', 0)
                    end_time = segment.get('end_time', 0)
                    gain_applied = segment.get('gain_applied', 0)
                    segment_type = segment.get('segment_type', 'question')
                    
                    # Segment info card
                    st.markdown(f"""
                    <div style="border: 1px solid #ddd; border-radius: 5px; padding: 10px; margin: 5px 0;">
                        <strong>Segment {i+1}</strong><br>
                        <small>Type: {segment_type.title()}</small><br>
                        <small>Time: {format_time(start_time)} - {format_time(end_time)}</small><br>
                        <small>Gain: +{gain_applied:.1f}dB</small>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if st.button(f"▶️ Play Segment {i+1}", key=f"play_segment_{i}"):
                        st.info(f"Note: Jump to {format_time(start_time)} in the audio player above")
    else:
        st.warning("Audio file not found")
        st.write("Expected locations:")
        if audio_path:
            st.code(audio_path)

def show_transcript_viewer(sermon):
    """Display transcript with Q&A highlighting"""
    st.subheader("📄 Full Transcript")
    
    content = sermon.get('content', {})
    transcript_text = content.get('transcript_text', '')
    
    if transcript_text:
        # Get Q&A segments for highlighting
        qa_segments = sermon.get('processing_info', {}).get('qa_segments', [])
        
        # Format transcript with Q&A highlights
        highlighted_transcript = format_transcript_with_qa_highlights(transcript_text, qa_segments)
        
        # Display in expandable container
        with st.container():
            st.markdown(highlighted_transcript, unsafe_allow_html=True)
        
        # Download options
        col1, col2 = st.columns(2)
        
        with col1:
            st.download_button(
                "📥 Download Transcript (TXT)",
                transcript_text,
                file_name=f"{sermon.get('title', 'sermon')}_transcript.txt",
                mime="text/plain"
            )
        
        with col2:
            if pdf_available:
                pdf_data = generate_pdf_transcript(sermon)
                if pdf_data:
                    st.download_button(
                        "📥 Download Transcript (PDF)",
                        pdf_data,
                        file_name=f"{sermon.get('title', 'sermon')}_transcript.pdf",
                        mime="application/pdf"
                    )
                else:
                    st.error("PDF generation failed")
            else:
                # Create simple HTML version for download
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>{sermon.get('title', 'Sermon')} - Transcript</title>
                    <style>
                        body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 40px; }}
                        .qa-segment {{ background-color: #e8f4fd; border-left: 4px solid #1f77b4; padding: 10px; margin: 10px 0; }}
                    </style>
                </head>
                <body>
                    <h1>{sermon.get('title', 'Sermon')}</h1>
                    <p><strong>Speaker:</strong> {sermon.get('speaker', 'Unknown')}</p>
                    <p><strong>Date:</strong> {sermon.get('recorded_date', 'Unknown')}</p>
                    <hr>
                    {highlighted_transcript.replace('<div style="background-color: #e8f4fd; border-left: 4px solid #1f77b4; padding: 10px; margin: 10px 0;">', '<div class="qa-segment">')}
                </body>
                </html>
                """
                
                st.download_button(
                    "📥 Download Transcript (HTML)",
                    html_content,
                    file_name=f"{sermon.get('title', 'sermon')}_transcript.html",
                    mime="text/html"
                )
    else:
        st.info("No transcript available for this sermon")

def show_description_editor(sermon):
    """Display and allow editing of sermon description"""
    st.subheader("📝 Description & Metadata")
    
    content = sermon.get('content', {})
    
    # Description
    description = content.get('description', '')
    if description:
        st.markdown("**Current Description:**")
        st.write(description)
    else:
        st.info("No description available")
    
    # Hashtags
    hashtags = content.get('hashtags', '')
    if hashtags:
        st.markdown("**Hashtags:**")
        st.write(hashtags)
    
    # Summary
    summary = content.get('summary', '')
    if summary:
        st.markdown("**Summary:**")
        st.write(summary)
    
    # Key topics
    key_topics = content.get('key_topics', [])
    if key_topics:
        st.markdown("**Key Topics:**")
        for topic in key_topics:
            st.write(f"• {topic}")
    
    # Edit form
    with st.expander("✏️ Edit Content"):
        with st.form("edit_content"):
            new_description = st.text_area(
                "Description",
                value=description,
                height=150,
                help="Edit the sermon description"
            )
            
            new_hashtags = st.text_input(
                "Hashtags",
                value=hashtags,
                help="Edit hashtags (space or comma separated)"
            )
            
            new_summary = st.text_area(
                "Summary",
                value=summary,
                height=100,
                help="Edit the sermon summary"
            )
            
            if st.form_submit_button("💾 Save Changes"):
                # Note: In a real implementation, this would save to database
                st.success("Changes saved! (Note: Database update not implemented in demo)")

def show_sermon_analytics(sermon):
    """Display analytics and metrics for the sermon"""
    st.subheader("📊 Sermon Analytics")
    
    # Basic metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        duration = sermon.get('duration', 0)
        duration_min = duration / 60 if duration else 0
        st.metric("Duration", f"{duration_min:.1f} min")
    
    with col2:
        qa_count = sermon.get('qa_segments_count', 0)
        st.metric("Q&A Segments", qa_count)
    
    with col3:
        processing_info = sermon.get('processing_info', {})
        quality_score = processing_info.get('quality_score')
        if quality_score:
            st.metric("Quality Score", f"{quality_score:.1f}/10")
        else:
            st.metric("Quality Score", "N/A")
    
    with col4:
        enhancement = processing_info.get('enhancement_method', 'Unknown')
        st.metric("Enhancement", enhancement)
    
    # Q&A Analysis
    if qa_count > 0:
        st.subheader("🗣️ Q&A Analysis")
        
        qa_segments = processing_info.get('qa_segments', [])
        
        # Create DataFrame for analysis
        segment_data = []
        for i, segment in enumerate(qa_segments, 1):
            segment_data.append({
                'Segment': i,
                'Start Time': format_time(segment.get('start_time', 0)),
                'End Time': format_time(segment.get('end_time', 0)),
                'Duration': f"{segment.get('end_time', 0) - segment.get('start_time', 0):.1f}s",
                'Type': segment.get('segment_type', 'question').title(),
                'Original Level': f"{segment.get('audio_level_db', 0):.1f}dB",
                'Gain Applied': f"+{segment.get('gain_applied', 0):.1f}dB",
                'Confidence': f"{segment.get('confidence', 0):.1%}"
            })
        
        if segment_data:
            df = pd.DataFrame(segment_data)
            st.dataframe(df, use_container_width=True)
            
            # Summary statistics
            avg_gain = sum(s.get('gain_applied', 0) for s in qa_segments) / len(qa_segments)
            total_qa_duration = sum(s.get('end_time', 0) - s.get('start_time', 0) for s in qa_segments)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Avg Gain Applied", f"+{avg_gain:.1f}dB")
            with col2:
                st.metric("Total Q&A Duration", f"{total_qa_duration:.1f}s")
            with col3:
                qa_percentage = (total_qa_duration / duration * 100) if duration else 0
                st.metric("Q&A Percentage", f"{qa_percentage:.1f}%")

def show_processing_details(sermon):
    """Display detailed processing information"""
    st.subheader("🔧 Processing Details")
    
    processing_info = sermon.get('processing_info', {})
    
    if not processing_info:
        st.info("No processing information available")
        return
    
    # Processing overview
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**Audio Processing:**")
        enhancement = processing_info.get('enhancement_method', 'Unknown')
        noise_reduction = processing_info.get('noise_reduction_applied', False)
        normalization = processing_info.get('normalization_applied', False)
        
        st.write(f"• Enhancement Method: {enhancement}")
        st.write(f"• Noise Reduction: {'✅ Applied' if noise_reduction else '❌ Not Applied'}")
        st.write(f"• Normalization: {'✅ Applied' if normalization else '❌ Not Applied'}")
    
    with col2:
        st.markdown("**Q&A Processing:**")
        qa_applied = processing_info.get('qa_normalization_applied', False)
        qa_count = processing_info.get('qa_segments_count', 0)
        
        st.write(f"• Q&A Normalization: {'✅ Applied' if qa_applied else '❌ Not Applied'}")
        st.write(f"• Segments Detected: {qa_count}")
        
        if qa_applied and qa_count > 0:
            qa_segments = processing_info.get('qa_segments', [])
            avg_gain = sum(s.get('gain_applied', 0) for s in qa_segments) / len(qa_segments)
            st.write(f"• Average Gain: +{avg_gain:.1f}dB")
    
    with col3:
        st.markdown("**Performance:**")
        proc_duration = processing_info.get('processing_duration')
        if proc_duration:
            st.write(f"• Processing Time: {proc_duration:.1f}s")
        
        quality_score = processing_info.get('quality_score')
        if quality_score:
            st.write(f"• Quality Score: {quality_score:.1f}/10")
        
        processed_at = processing_info.get('processed_at')
        if processed_at:
            st.write(f"• Processed: {processed_at}")
    
    # File information
    st.markdown("**Files:**")
    file_paths = sermon.get('file_paths', {})
    
    for file_type, file_path in file_paths.items():
        if file_path:
            file_exists = Path(file_path).exists()
            status = "✅" if file_exists else "❌"
            
            if file_exists:
                size_mb = Path(file_path).stat().st_size / (1024 * 1024)
                st.write(f"• {file_type.replace('_', ' ').title()}: {status} ({size_mb:.1f}MB)")
            else:
                st.write(f"• {file_type.replace('_', ' ').title()}: {status} (Missing)")
    
    # Processing logs
    processing_logs = processing_info.get('processing_logs', {})
    if processing_logs:
        with st.expander("📋 Processing Logs"):
            st.json(processing_logs)

def show_sermon_viewer():
    """Main sermon viewer interface"""
    
    # Check if a sermon is selected
    if 'selected_sermon' not in st.session_state:
        st.title("📖 Sermon Viewer")
        st.info("No sermon selected. Please select a sermon from the Library page.")
        
        # Show recent sermons for selection
        st.subheader("Recent Sermons")
        repo = SermonRepository()
        recent_sermons = repo.get_all_sermons(limit=10)
        
        if recent_sermons:
            for sermon in recent_sermons:
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    title = sermon.get('title', 'Untitled Sermon')
                    speaker = sermon.get('speaker', 'Unknown Speaker')
                    date = sermon.get('recorded_date', 'Unknown Date')
                    st.write(f"**{title}** by {speaker} ({date})")
                
                with col2:
                    if st.button(f"📖 View", key=f"select_{sermon.get('id')}"):
                        st.session_state.selected_sermon = sermon.get('id')
                        st.rerun()
        else:
            st.write("No sermons available.")
        
        return
    
    # Get selected sermon
    sermon_id = st.session_state.selected_sermon
    repo = SermonRepository()
    sermon = repo.get_sermon(sermon_id)
    
    if not sermon:
        st.error(f"Sermon {sermon_id} not found")
        return
    
    # Header
    title = sermon.get('title', 'Untitled Sermon')
    speaker = sermon.get('speaker', 'Unknown Speaker')
    date = sermon.get('recorded_date', 'Unknown Date')
    
    st.title(f"📖 {title}")
    st.subheader(f"by {speaker} • {date}")
    
    # Navigation
    col1, col2 = st.columns([1, 4])
    
    with col1:
        if st.button("◀️ Back to Library"):
            if 'selected_sermon' in st.session_state:
                del st.session_state.selected_sermon
            st.rerun()
    
    with col2:
        event_type = sermon.get('event_type', 'Unknown Event')
        status = sermon.get('status', 'unknown')
        st.write(f"**Event:** {event_type} | **Status:** {status.title()}")
    
    # Tabs for different content views
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📄 Transcript", 
        "📝 Description", 
        "🎵 Audio", 
        "📊 Analytics", 
        "🔧 Processing"
    ])
    
    with tab1:
        show_transcript_viewer(sermon)
    
    with tab2:
        show_description_editor(sermon)
    
    with tab3:
        show_audio_player(sermon)
    
    with tab4:
        show_sermon_analytics(sermon)
    
    with tab5:
        show_processing_details(sermon)

if __name__ == "__main__":
    show_sermon_viewer()
else:
    # When imported as a page
    show_sermon_viewer()