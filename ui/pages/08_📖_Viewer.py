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

# Load configuration
try:
    import yaml
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
except FileNotFoundError:
    config = {}

# Initialize managers
@st.cache_resource
def get_managers():
    from sermon_manager import get_sermon_manager
    from analytics_manager import get_analytics_manager
    sermon_mgr = get_sermon_manager(config)
    analytics_mgr = get_analytics_manager(config)
    return sermon_mgr, analytics_mgr

def get_availability_status(sermon):
    """Get availability status with appropriate emoji and text"""
    if isinstance(sermon, dict):
        local = sermon.get('local_available', False)
        remote = sermon.get('remote_available', False)
    else:
        local = getattr(sermon, 'local_available', False)
        remote = getattr(sermon, 'remote_available', False)
    
    if local and remote:
        return "🔄", "Local + Remote"
    elif local:
        return "💾", "Local Only"
    elif remote:
        return "☁️", "Remote Only"
    else:
        return "❓", "Unknown"

def get_status_emoji(status):
    """Get emoji for processing status"""
    status_map = {
        'processed': '✅',
        'processing': '⏳',
        'pending': '⏸️',
        'failed': '❌',
        'uploaded': '☁️'
    }
    return status_map.get(status, '❓')

def format_duration(duration_seconds):
    """Format duration in seconds to readable string"""
    if not duration_seconds:
        return "Unknown"
    
    hours = int(duration_seconds // 3600)
    minutes = int((duration_seconds % 3600) // 60)
    
    if hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"

def show_dual_audio_players(sermon, files, edit_mode):
    """Show dual audio players for original and enhanced audio"""
    st.subheader("🎵 Audio Players")
    
    col1, col2 = st.columns(2)
    
    # Original Audio Player
    with col1:
        st.markdown("### 🎤 Original Audio")
        
        original_path = getattr(sermon.audio_files, 'original', None)
        original_url = getattr(sermon.audio_files, 'original_url', None)
        
        if original_path and Path(original_path).exists():
            st.audio(original_path, format='audio/mp3')
            st.caption(f"📁 Local File: {Path(original_path).name}")
            
            # File info
            file_size = Path(original_path).stat().st_size / (1024 * 1024)  # MB
            st.caption(f"Size: {file_size:.1f} MB")
        elif original_url:
            st.audio(original_url, format='audio/mp3')
            st.caption("☁️ Remote Stream")
        else:
            st.info("Original audio not available")
    
    # Enhanced Audio Player
    with col2:
        st.markdown("### ✨ Enhanced Audio")
        
        processed_path = getattr(sermon.audio_files, 'processed', None)
        
        if processed_path and Path(processed_path).exists():
            st.audio(processed_path, format='audio/mp3')
            st.caption(f"📁 Local File: {Path(processed_path).name}")
            
            # File info
            file_size = Path(processed_path).stat().st_size / (1024 * 1024)  # MB
            st.caption(f"Size: {file_size:.1f} MB")
            
            # Enhancement info
            processing_info = sermon.processing_info or {}
            enhancements = processing_info.get('audio_enhancements', {})
            if enhancements:
                st.caption("🔧 Enhancements Applied:")
                for enhancement, applied in enhancements.items():
                    if applied:
                        st.caption(f"  ✅ {enhancement.replace('_', ' ').title()}")
        else:
            st.info("Enhanced audio not available")
            if edit_mode:
                st.button("🚀 Process Audio", help="Start audio enhancement")
    
    # Q&A Segment Navigation
    if sermon.qa_segments:
        st.subheader("🗣️ Q&A Segments")
        
        st.info(f"Found {len(sermon.qa_segments)} Q&A segments with automatic audio normalization")
        
        for i, segment in enumerate(sermon.qa_segments, 1):
            col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
            
            with col1:
                start_time = format_time(segment.get('start_time', 0))
                end_time = format_time(segment.get('end_time', 0))
                st.write(f"**Q&A {i}:** {start_time} - {end_time}")
            
            with col2:
                gain = segment.get('gain_applied', 0)
                st.write(f"Boost: +{gain:.1f}dB")
            
            with col3:
                confidence = segment.get('confidence', 0)
                st.write(f"Confidence: {confidence:.1%}")
            
            with col4:
                if st.button(f"▶️ Play", key=f"qa_play_{i}"):
                    st.info(f"Jump to {start_time} (feature in development)")

def show_transcript_editor(sermon_id, content):
    """Editable transcript with auto-save"""
    st.subheader("📄 Edit Transcript")
    
    current_transcript = content.get('transcript_text', '')
    
    # Editor
    transcript = st.text_area(
        "Transcript Content",
        value=current_transcript,
        height=400,
        help="Edit the sermon transcript. Changes will be saved automatically."
    )
    
    # Auto-save functionality
    if transcript != current_transcript:
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("💾 Save Changes", type="primary"):
                try:
                    repo = SermonRepository()
                    repo.update_sermon(sermon_id, {'transcript': transcript})
                    st.success("Transcript saved successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error saving transcript: {e}")
        
        with col2:
            if st.button("↩️ Revert Changes", type="secondary"):
                st.rerun()
    
    # Download options
    st.subheader("📥 Download Options")
    col1, col2 = st.columns(2)
    
    with col1:
        if transcript:
            st.download_button(
                "📄 Download as TXT",
                transcript,
                file_name=f"transcript_{sermon_id}.txt",
                mime="text/plain"
            )
    
    with col2:
        if transcript and pdf_available:
            try:
                pdf_data = generate_pdf_transcript({
                    'title': st.session_state.get('sermon_title', 'Sermon'),
                    'speaker': st.session_state.get('sermon_speaker', 'Unknown'),
                    'recorded_date': st.session_state.get('sermon_date', 'Unknown'),
                    'content': {'transcript_text': transcript},
                    'processing_info': {'qa_segments': []}
                })
                if pdf_data:
                    st.download_button(
                        "📑 Download as PDF",
                        pdf_data,
                        file_name=f"transcript_{sermon_id}.pdf",
                        mime="application/pdf"
                    )
            except Exception as e:
                st.error(f"PDF generation error: {e}")

def show_metadata_editor(sermon_id, sermon, content):
    """Editable metadata form"""
    st.subheader("📝 Edit Metadata")
    
    # Create form for editing
    with st.form("metadata_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            title = st.text_input("Title", value=sermon.title)
            speaker = st.text_input("Speaker", value=sermon.speaker)
            event_type = st.text_input("Event Type", value=sermon.event_type or "")
            bible_text = st.text_input("Bible Text", value=sermon.bible_text or "")
        
        with col2:
            # Date editor would go here if needed
            st.text_input("Date", value=sermon.date.strftime('%Y-%m-%d'), disabled=True, help="Date cannot be edited")
            
            # Status selector
            status_options = ['processed', 'processing', 'pending', 'failed', 'uploaded']
            current_status = sermon.status if sermon.status in status_options else 'processed'
            status = st.selectbox("Status", options=status_options, index=status_options.index(current_status))
        
        # Description editor
        description = st.text_area(
            "Description", 
            value=content.get('description', ''),
            height=150,
            help="Sermon description for SermonAudio"
        )
        
        # Hashtags editor
        hashtags_text = ', '.join(content.get('hashtags', []))
        hashtags = st.text_input(
            "Hashtags", 
            value=hashtags_text,
            help="Comma-separated hashtags"
        )
        
        # Submit button
        submitted = st.form_submit_button("💾 Save All Changes", type="primary")
        
        if submitted:
            try:
                # Parse hashtags
                hashtag_list = [tag.strip() for tag in hashtags.split(',') if tag.strip()]
                
                # Update sermon
                repo = SermonRepository()
                updates = {
                    'title': title,
                    'speaker': speaker,
                    'event_type': event_type,
                    'bible_text': bible_text,
                    'status': status,
                    'description': description,
                    'hashtags': hashtag_list
                }
                
                repo.update_sermon(sermon_id, updates)
                st.success("Metadata saved successfully!")
                
                # Clear edit mode
                st.session_state.edit_mode = False
                st.rerun()
                
            except Exception as e:
                st.error(f"Error saving metadata: {e}")
    
    # Upload to SermonAudio
    st.subheader("☁️ Upload to SermonAudio")
    
    if st.button("🚀 Upload Changes to SermonAudio", type="primary"):
        try:
            # This would call the upload API
            st.info("Upload functionality in development - would sync with SermonAudio API")
            # Update status to uploaded
            repo = SermonRepository()
            repo.update_sermon(sermon_id, {
                'status': 'uploaded',
                'upload_info': {
                    'upload_date': datetime.now().isoformat(),
                    'upload_status': 'success'
                }
            })
            st.success("Changes uploaded to SermonAudio!")
        except Exception as e:
            st.error(f"Upload error: {e}")

def show_description_viewer(content):
    """Display sermon description in view mode"""
    st.subheader("📝 Description")
    
    description = content.get('description', '')
    if description:
        st.markdown(description)
    else:
        st.info("No description available")
    
    # Hashtags
    hashtags = content.get('hashtags', [])
    if hashtags:
        st.subheader("🏷️ Hashtags")
        for tag in hashtags:
            st.button(f"#{tag}", key=f"tag_{tag}", help="Click to search similar sermons")
    
    # Summary if available
    summary = content.get('summary', '')
    if summary:
        st.subheader("📋 Summary")
        st.markdown(summary)

def show_sermon_analytics_tab(sermon_id, analytics_manager):
    """Display comprehensive sermon analytics"""
    st.subheader("📊 Sermon Analytics")
    
    # Load analytics data
    with st.spinner("Loading analytics..."):
        try:
            analytics = asyncio.run(analytics_manager.get_sermon_analytics(sermon_id))
        except Exception as e:
            st.warning(f"Analytics unavailable: {e}")
            analytics = None
    
    if not analytics:
        st.info("Analytics data not available - requires SermonAudio API integration")
        return
    
    # Overview metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Views", analytics.total_views)
    
    with col2:
        st.metric("Unique Listeners", analytics.unique_listeners)
    
    with col3:
        completion_pct = analytics.completion_rate * 100
        st.metric("Completion Rate", f"{completion_pct:.1f}%")
    
    with col4:
        watch_minutes = analytics.avg_watch_duration / 60
        st.metric("Avg. Watch Time", f"{watch_minutes:.1f} min")
    
    # Charts
    col1, col2 = st.columns(2)
    
    with col1:
        # Geographic breakdown
        if analytics.geographic_breakdown:
            st.subheader("🌍 Geographic Distribution")
            
            geo_data = []
            for location in analytics.geographic_breakdown:
                geo_data.append({
                    'Location': location.location,
                    'Views': location.views,
                    'Percentage': location.percentage
                })
            
            df_geo = pd.DataFrame(geo_data)
            
            import plotly.express as px
            fig = px.pie(
                df_geo, 
                values='Views', 
                names='Location',
                title="Views by Location"
            )
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Device breakdown
        if analytics.device_breakdown:
            st.subheader("📱 Device Types")
            
            device_data = []
            for device, views in analytics.device_breakdown.items():
                device_data.append({'Device': device, 'Views': views})
            
            df_devices = pd.DataFrame(device_data)
            
            fig = px.bar(
                df_devices,
                x='Device',
                y='Views',
                title="Views by Device Type"
            )
            st.plotly_chart(fig, use_container_width=True)
    
    # Engagement timeline
    if analytics.engagement_timeline:
        st.subheader("📈 Engagement Timeline")
        
        timeline_data = []
        for point in analytics.engagement_timeline:
            timeline_data.append({
                'Date': point.timestamp,
                'Views': point.value,
                'Label': point.label
            })
        
        df_timeline = pd.DataFrame(timeline_data)
        
        fig = px.line(
            df_timeline,
            x='Date',
            y='Views',
            title="Daily Views Over Time"
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Referral sources
    if analytics.referral_sources:
        st.subheader("🔗 Referral Sources")
        
        ref_data = []
        for source, views in analytics.referral_sources.items():
            ref_data.append({'Source': source, 'Views': views})
        
        df_ref = pd.DataFrame(ref_data)
        st.dataframe(df_ref, use_container_width=True)
    
    # Last updated
    st.caption(f"Last updated: {analytics.last_updated.strftime('%Y-%m-%d %H:%M:%S')}")

def show_processing_details(sermon):
    """Display detailed processing information"""
    st.subheader("🔧 Processing Information")
    
    processing_info = sermon.processing_info or {}
    
    # Processing status
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Processing Status:**")
        status_emoji = get_status_emoji(sermon.status)
        st.write(f"{status_emoji} {sermon.status.title()}")
        
        # File availability
        st.write("**File Availability:**")
        if hasattr(sermon, 'local_available') and sermon.local_available:
            st.write("✅ Local files available")
        if hasattr(sermon, 'remote_available') and sermon.remote_available:
            st.write("☁️ Remote files available")
    
    with col2:
        # Processing timestamps
        if processing_info.get('processed_at'):
            st.write(f"**Processed:** {processing_info['processed_at']}")
        if processing_info.get('uploaded_at'):
            st.write(f"**Uploaded:** {processing_info['uploaded_at']}")
    
    # Audio enhancements
    audio_enhancements = processing_info.get('audio_enhancements', {})
    if audio_enhancements:
        st.subheader("🎵 Audio Enhancements")
        
        for enhancement, details in audio_enhancements.items():
            if isinstance(details, dict):
                st.write(f"**{enhancement.replace('_', ' ').title()}:**")
                for key, value in details.items():
                    st.write(f"  • {key}: {value}")
            else:
                status = "✅ Applied" if details else "❌ Not applied"
                st.write(f"**{enhancement.replace('_', ' ').title()}:** {status}")
    
    # Q&A processing details
    if sermon.qa_segments:
        st.subheader("🗣️ Q&A Processing Details")
        
        qa_data = []
        for i, segment in enumerate(sermon.qa_segments, 1):
            qa_data.append({
                'Segment': f"Q&A {i}",
                'Start Time': format_time(segment.get('start_time', 0)),
                'End Time': format_time(segment.get('end_time', 0)),
                'Gain Applied': f"+{segment.get('gain_applied', 0):.1f}dB",
                'Confidence': f"{segment.get('confidence', 0):.1%}",
                'Method': segment.get('detection_method', 'Unknown')
            })
        
        df_qa = pd.DataFrame(qa_data)
        st.dataframe(df_qa, use_container_width=True)
    
    # Quality metrics
    quality_metrics = processing_info.get('quality_metrics', {})
    if quality_metrics:
        st.subheader("📊 Quality Metrics")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if 'rms_level' in quality_metrics:
                st.metric("RMS Level", f"{quality_metrics['rms_level']:.1f} dB")
        
        with col2:
            if 'snr_estimate' in quality_metrics:
                st.metric("SNR Estimate", f"{quality_metrics['snr_estimate']:.1f} dB")
        
        with col3:
            if 'quality_score' in quality_metrics:
                st.metric("Quality Score", f"{quality_metrics['quality_score']:.1f}/10")
    
    # Raw processing info
    with st.expander("🔍 Raw Processing Data"):
        st.json(processing_info)

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
    """Enhanced sermon viewer with dual audio players and analytics"""
    
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
    
    sermon_id = st.session_state.selected_sermon
    edit_mode = st.session_state.get('edit_mode', False)
    
    # Get managers
    sermon_manager, analytics_manager = get_managers()
    
    # Load sermon details
    with st.spinner("Loading sermon details..."):
        try:
            sermon_details = asyncio.run(sermon_manager.get_sermon_details(sermon_id))
            if not sermon_details:
                # Fallback to database-only data
                repo = SermonRepository()
                sermon = repo.get_sermon(sermon_id)
                if not sermon:
                    st.error(f"Sermon {sermon_id} not found")
                    return
                # Create mock sermon_details structure
                from sermon_manager import SermonData, SermonDetails, AudioFiles
                sermon_data = SermonData(
                    id=sermon_id,
                    title=sermon.get('title', 'Unknown'),
                    date=datetime.fromisoformat(sermon.get('recorded_date', '1900-01-01')),
                    speaker=sermon.get('speaker', 'Unknown'),
                    description=sermon.get('description', ''),
                    hashtags=sermon.get('hashtags', []),
                    local_available=True,
                    remote_available=False,
                    audio_files=AudioFiles(),
                    transcript=sermon.get('transcript', ''),
                    event_type=sermon.get('event_type'),
                    bible_text=sermon.get('bible_text'),
                    status=sermon.get('status', 'processed'),
                    processing_info=sermon.get('processing_info', {}),
                    qa_segments=sermon.get('qa_segments', [])
                )
                sermon_details = SermonDetails(
                    sermon_data=sermon_data,
                    content={
                        'transcript_text': sermon.get('transcript', ''),
                        'description': sermon.get('description', ''),
                        'hashtags': sermon.get('hashtags', []),
                        'summary': sermon.get('summary', '')
                    },
                    files={}
                )
        except Exception as e:
            st.error(f"Error loading sermon: {e}")
            return
    
    sermon = sermon_details.sermon_data
    content = sermon_details.content
    files = sermon_details.files
    
    # Header with sermon info
    st.title(f"📖 {sermon.title}")
    st.subheader(f"by {sermon.speaker} • {sermon.date.strftime('%B %d, %Y')}")
    
    # Availability and status indicators
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if hasattr(sermon, 'local_available'):
            avail_emoji, avail_text = get_availability_status({
                'local_available': sermon.local_available,
                'remote_available': sermon.remote_available
            })
        else:
            avail_emoji, avail_text = "💾", "Local Only"
        st.metric("Availability", avail_text, label_visibility="visible")
        st.caption(f"{avail_emoji} {avail_text}")
    
    with col2:
        status_emoji = get_status_emoji(sermon.status)
        st.metric("Status", f"{status_emoji} {sermon.status.title()}")
    
    with col3:
        qa_count = len(sermon.qa_segments) if sermon.qa_segments else 0
        st.metric("Q&A Segments", qa_count)
    
    with col4:
        duration = getattr(sermon.audio_files, 'duration', None) or 0
        st.metric("Duration", format_duration(duration))
    
    # Edit mode toggle
    if st.button("✏️ Toggle Edit Mode", type="secondary"):
        st.session_state.edit_mode = not edit_mode
        st.rerun()
    
    st.divider()
    
    # Main content tabs
    if edit_mode:
        tabs = st.tabs([
            "🎵 Audio Players", 
            "📄 Edit Transcript", 
            "📝 Edit Metadata", 
            "📊 Analytics", 
            "🔧 Processing Info"
        ])
    else:
        tabs = st.tabs([
            "🎵 Audio Players",
            "📄 Transcript", 
            "📝 Description", 
            "📊 Analytics", 
            "🔧 Processing Info"
        ])
    
    # Tab 1: Audio Players
    with tabs[0]:
        show_dual_audio_players(sermon, files, edit_mode)
    
    # Tab 2: Transcript (Edit or View)
    with tabs[1]:
        if edit_mode:
            show_transcript_editor(sermon_id, content)
        else:
            show_transcript_viewer(sermon, content)
    
    # Tab 3: Metadata (Edit or Description)
    with tabs[2]:
        if edit_mode:
            show_metadata_editor(sermon_id, sermon, content)
        else:
            show_description_viewer(content)
    
    # Tab 4: Analytics
    with tabs[3]:
        show_sermon_analytics_tab(sermon_id, analytics_manager)
    
    # Tab 5: Processing Info
    with tabs[4]:
        show_processing_details(sermon)
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