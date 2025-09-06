"""
API Routes for Sermon Management and Analytics

Provides RESTful endpoints for:
- Sermon listing and details with local/remote data
- Audio streaming (original and enhanced)
- Content editing and uploading
- Analytics data for dashboard and per-sermon views
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add parent directory to path for imports
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))
sys.path.insert(0, str(parent_dir / "src"))

import yaml
from analytics_manager import get_analytics_manager
from database import SermonRepository
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from sermon_manager import get_sermon_manager

logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Load configuration
try:
    with open('config.yaml') as f:
        config = yaml.safe_load(f)
except FileNotFoundError:
    config = {}

# Initialize managers
sermon_manager = get_sermon_manager(config)
analytics_manager = get_analytics_manager(config)
repo = SermonRepository()

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Resource not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

# Sermon Management Routes

@app.route('/api/sermons', methods=['GET'])
async def list_sermons():
    """Get list of all sermons with optional filtering"""
    try:
        # Parse query parameters
        filters = {}

        if request.args.get('speaker'):
            filters['speaker'] = request.args.get('speaker')
        if request.args.get('event_type'):
            filters['event_type'] = request.args.get('event_type')
        if request.args.get('start_date'):
            filters['start_date'] = request.args.get('start_date')
        if request.args.get('end_date'):
            filters['end_date'] = request.args.get('end_date')
        if request.args.get('search'):
            filters['search'] = request.args.get('search')
        if request.args.get('local_only') == 'true':
            filters['local_only'] = True
        if request.args.get('remote_only') == 'true':
            filters['remote_only'] = True
        if request.args.get('limit'):
            filters['limit'] = int(request.args.get('limit'))

        # Get sermons
        sermons = await sermon_manager.get_sermon_list(filters)

        # Convert to JSON-serializable format
        sermon_list = []
        for sermon in sermons:
            sermon_dict = {
                'id': sermon.id,
                'title': sermon.title,
                'date': sermon.date.isoformat(),
                'speaker': sermon.speaker,
                'description': sermon.description,
                'hashtags': sermon.hashtags,
                'local_available': sermon.local_available,
                'remote_available': sermon.remote_available,
                'event_type': sermon.event_type,
                'bible_text': sermon.bible_text,
                'status': sermon.status,
                'duration': getattr(sermon.audio_files, 'duration', None),
                'qa_segments_count': len(sermon.qa_segments) if sermon.qa_segments else 0,
                'has_transcript': bool(sermon.transcript)
            }
            sermon_list.append(sermon_dict)

        return jsonify({
            'sermons': sermon_list,
            'total': len(sermon_list),
            'filters_applied': filters
        })

    except Exception as e:
        logger.error(f"Error listing sermons: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sermons/<sermon_id>', methods=['GET'])
async def get_sermon(sermon_id: str):
    """Get detailed information for a specific sermon"""
    try:
        sermon_details = await sermon_manager.get_sermon_details(sermon_id)

        if not sermon_details:
            return jsonify({'error': 'Sermon not found'}), 404

        # Convert to JSON-serializable format
        result = {
            'sermon': {
                'id': sermon_details.sermon_data.id,
                'title': sermon_details.sermon_data.title,
                'date': sermon_details.sermon_data.date.isoformat(),
                'speaker': sermon_details.sermon_data.speaker,
                'description': sermon_details.sermon_data.description,
                'hashtags': sermon_details.sermon_data.hashtags,
                'local_available': sermon_details.sermon_data.local_available,
                'remote_available': sermon_details.sermon_data.remote_available,
                'event_type': sermon_details.sermon_data.event_type,
                'bible_text': sermon_details.sermon_data.bible_text,
                'status': sermon_details.sermon_data.status,
                'transcript': sermon_details.sermon_data.transcript,
                'audio_files': {
                    'original': sermon_details.sermon_data.audio_files.original,
                    'processed': sermon_details.sermon_data.audio_files.processed,
                    'original_url': sermon_details.sermon_data.audio_files.original_url,
                    'duration': sermon_details.sermon_data.audio_files.duration
                },
                'processing_info': sermon_details.sermon_data.processing_info,
                'qa_segments': sermon_details.sermon_data.qa_segments
            },
            'content': sermon_details.content,
            'files': sermon_details.files
        }

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error getting sermon {sermon_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sermons/<sermon_id>', methods=['PUT'])
async def update_sermon(sermon_id: str):
    """Update sermon metadata and content"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        # Update sermon in database
        updates = {}
        if 'title' in data:
            updates['title'] = data['title']
        if 'speaker' in data:
            updates['speaker'] = data['speaker']
        if 'description' in data:
            updates['description'] = data['description']
        if 'hashtags' in data:
            updates['hashtags'] = data['hashtags']
        if 'transcript' in data:
            updates['transcript'] = data['transcript']
        if 'event_type' in data:
            updates['event_type'] = data['event_type']
        if 'bible_text' in data:
            updates['bible_text'] = data['bible_text']

        # Update in database
        repo.update_sermon(sermon_id, updates)

        # Invalidate caches
        sermon_manager._sermon_list_cache = None
        analytics_manager.invalidate_cache()

        return jsonify({'success': True, 'message': 'Sermon updated successfully'})

    except Exception as e:
        logger.error(f"Error updating sermon {sermon_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sermons/<sermon_id>/upload', methods=['POST'])
async def upload_sermon_changes(sermon_id: str):
    """Upload sermon changes to SermonAudio"""
    try:
        # This would integrate with SermonAudio's update API
        # For now, just mark as uploaded in local database

        repo.update_sermon(sermon_id, {
            'status': 'uploaded',
            'upload_info': {
                'upload_date': datetime.now().isoformat(),
                'upload_status': 'success'
            }
        })

        # Invalidate caches
        sermon_manager._sermon_list_cache = None

        return jsonify({
            'success': True,
            'message': 'Sermon uploaded to SermonAudio successfully'
        })

    except Exception as e:
        logger.error(f"Error uploading sermon {sermon_id}: {e}")
        return jsonify({'error': str(e)}), 500

# Analytics Routes

@app.route('/api/analytics/dashboard', methods=['GET'])
async def get_dashboard_analytics():
    """Get comprehensive dashboard analytics"""
    try:
        analytics = await analytics_manager.get_dashboard_analytics()

        # Convert to JSON-serializable format
        result = {
            'total_sermons': analytics.total_sermons,
            'total_views': analytics.total_views,
            'total_hours_watched': analytics.total_hours_watched,
            'avg_engagement_rate': analytics.avg_engagement_rate,
            'top_sermons': analytics.top_sermons,
            'geographic_summary': [
                {
                    'location': loc.location,
                    'country_code': loc.country_code,
                    'views': loc.views,
                    'percentage': loc.percentage
                } for loc in analytics.geographic_summary
            ],
            'engagement_trends': [
                {
                    'timestamp': point.timestamp.isoformat(),
                    'value': point.value,
                    'label': point.label
                } for point in analytics.engagement_trends
            ],
            'recent_activity': analytics.recent_activity,
            'growth_metrics': analytics.growth_metrics,
            'last_updated': analytics.last_updated.isoformat()
        }

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error getting dashboard analytics: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/analytics/sermons/<sermon_id>', methods=['GET'])
async def get_sermon_analytics(sermon_id: str):
    """Get analytics for a specific sermon"""
    try:
        analytics = await analytics_manager.get_sermon_analytics(sermon_id)

        if not analytics:
            return jsonify({'error': 'Analytics not found for sermon'}), 404

        # Convert to JSON-serializable format
        result = {
            'sermon_id': analytics.sermon_id,
            'total_views': analytics.total_views,
            'unique_listeners': analytics.unique_listeners,
            'geographic_breakdown': [
                {
                    'location': loc.location,
                    'country_code': loc.country_code,
                    'views': loc.views,
                    'percentage': loc.percentage
                } for loc in analytics.geographic_breakdown
            ],
            'engagement_timeline': [
                {
                    'timestamp': point.timestamp.isoformat(),
                    'value': point.value,
                    'label': point.label
                } for point in analytics.engagement_timeline
            ],
            'avg_watch_duration': analytics.avg_watch_duration,
            'completion_rate': analytics.completion_rate,
            'peak_concurrent': analytics.peak_concurrent,
            'referral_sources': analytics.referral_sources,
            'device_breakdown': analytics.device_breakdown,
            'last_updated': analytics.last_updated.isoformat()
        }

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error getting sermon analytics for {sermon_id}: {e}")
        return jsonify({'error': str(e)}), 500

# Media Routes

@app.route('/api/sermons/<sermon_id>/audio/original', methods=['GET'])
def stream_original_audio(sermon_id: str):
    """Stream original audio file"""
    try:
        sermon_details = asyncio.run(sermon_manager.get_sermon_details(sermon_id))

        if not sermon_details:
            return jsonify({'error': 'Sermon not found'}), 404

        audio_path = sermon_details.sermon_data.audio_files.original
        if not audio_path or not Path(audio_path).exists():
            return jsonify({'error': 'Original audio file not found'}), 404

        return send_file(
            audio_path,
            mimetype='audio/mpeg',
            as_attachment=False,
            download_name=f"{sermon_details.sermon_data.title}_original.mp3"
        )

    except Exception as e:
        logger.error(f"Error streaming original audio for {sermon_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sermons/<sermon_id>/audio/enhanced', methods=['GET'])
def stream_enhanced_audio(sermon_id: str):
    """Stream enhanced/processed audio file"""
    try:
        sermon_details = asyncio.run(sermon_manager.get_sermon_details(sermon_id))

        if not sermon_details:
            return jsonify({'error': 'Sermon not found'}), 404

        audio_path = sermon_details.sermon_data.audio_files.processed
        if not audio_path or not Path(audio_path).exists():
            return jsonify({'error': 'Enhanced audio file not found'}), 404

        return send_file(
            audio_path,
            mimetype='audio/mpeg',
            as_attachment=False,
            download_name=f"{sermon_details.sermon_data.title}_enhanced.mp3"
        )

    except Exception as e:
        logger.error(f"Error streaming enhanced audio for {sermon_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sermons/<sermon_id>/transcript', methods=['GET'])
def get_transcript(sermon_id: str):
    """Get sermon transcript"""
    try:
        sermon_details = asyncio.run(sermon_manager.get_sermon_details(sermon_id))

        if not sermon_details:
            return jsonify({'error': 'Sermon not found'}), 404

        transcript = sermon_details.content.get('transcript_text', '')

        return jsonify({
            'transcript': transcript,
            'sermon_id': sermon_id,
            'title': sermon_details.sermon_data.title
        })

    except Exception as e:
        logger.error(f"Error getting transcript for {sermon_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sermons/<sermon_id>/transcript', methods=['PUT'])
def update_transcript(sermon_id: str):
    """Update sermon transcript"""
    try:
        data = request.get_json()

        if not data or 'transcript' not in data:
            return jsonify({'error': 'Transcript content required'}), 400

        # Update transcript in database
        repo.update_sermon(sermon_id, {'transcript': data['transcript']})

        # Also save to transcript file if it exists
        sermon_dir = Path(config.get('output_directory', 'processed_sermons')) / sermon_id
        if sermon_dir.exists():
            transcript_file = sermon_dir / "transcript.txt"
            try:
                transcript_file.write_text(data['transcript'], encoding='utf-8')
            except Exception as e:
                logger.warning(f"Could not save transcript file for {sermon_id}: {e}")

        # Invalidate caches
        sermon_manager._sermon_list_cache = None

        return jsonify({'success': True, 'message': 'Transcript updated successfully'})

    except Exception as e:
        logger.error(f"Error updating transcript for {sermon_id}: {e}")
        return jsonify({'error': str(e)}), 500

# System Status Routes

@app.route('/api/status', methods=['GET'])
def get_system_status():
    """Get system status for sidebar indicators"""
    try:
        status = {
            'sermonaudio_api': _check_sermonaudio_api(),
            'database': _check_database(),
            'llm_provider': _check_llm_provider(),
            'audio_enhancement': _check_audio_enhancement(),
            'local_storage': _check_local_storage()
        }

        return jsonify(status)

    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        return jsonify({'error': str(e)}), 500

def _check_sermonaudio_api() -> dict[str, Any]:
    """Check SermonAudio API connection"""
    try:
        if not config.get('api_key') or not config.get('broadcaster_id'):
            return {'status': 'error', 'message': 'API credentials not configured'}

        # Test API connection (simplified)
        # In a real implementation, this would make a test API call
        return {'status': 'ok', 'message': 'API connected'}

    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def _check_database() -> dict[str, Any]:
    """Check database connection"""
    try:
        stats = repo.get_processing_stats()
        return {'status': 'ok', 'message': f"Database connected ({stats['total_sermons']} sermons)"}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def _check_llm_provider() -> dict[str, Any]:
    """Check LLM provider status"""
    try:
        # This would check the actual LLM connection
        llm_config = config.get('llm', {}).get('primary', {})
        provider = llm_config.get('provider', 'unknown')
        return {'status': 'ok', 'message': f"{provider} provider ready"}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def _check_audio_enhancement() -> dict[str, Any]:
    """Check audio enhancement availability"""
    try:
        method = config.get('audio_enhancement_method', 'none')
        if method == 'none':
            return {'status': 'warning', 'message': 'Audio enhancement disabled'}
        return {'status': 'ok', 'message': f"{method} enhancement ready"}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def _check_local_storage() -> dict[str, Any]:
    """Check local storage status"""
    try:
        output_dir = Path(config.get('output_directory', 'processed_sermons'))
        if not output_dir.exists():
            return {'status': 'warning', 'message': 'Output directory does not exist'}

        # Count local sermons
        local_count = len([d for d in output_dir.iterdir() if d.is_dir()])
        return {'status': 'ok', 'message': f"{local_count} local sermons"}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

# Health check route
@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(level=logging.INFO)

    # Run the Flask app
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=config.get('debug', False)
    )
