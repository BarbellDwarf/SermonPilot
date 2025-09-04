"""
UI Processing Interface for SermonAudio Processor

Provides real validation and processing functionality with progress tracking
for the Streamlit UI, connecting the interface to the actual sermon processing pipeline.
"""

import streamlit as st
import asyncio
import threading
import time
import logging
from typing import Dict, List, Optional, Callable
from pathlib import Path
import sys

# Add src directory for imports
ui_dir = Path(__file__).parent
src_dir = ui_dir.parent / 'src'
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(ui_dir.parent))

from database import get_db

logger = logging.getLogger(__name__)

class UIProcessor:
    """Handles real processing operations with UI feedback"""
    
    def __init__(self):
        self.db = get_db()
        self._active_operations = {}
    
    def validate_sermons(self, sermon_ids: List[str], 
                        progress_callback: Optional[Callable] = None) -> Dict:
        """
        Validate sermons with real-time progress updates
        
        Args:
            sermon_ids: List of sermon IDs to validate
            progress_callback: Optional callback for progress updates
            
        Returns:
            Validation results summary
        """
        try:
            # Import validation functions
            import sermon_updater
            from sermon_updater import DescriptionValidator
            
            # Initialize validator
            config = st.session_state.get('config', {})
            if not config:
                raise ValueError("No configuration available")
            
            validator = DescriptionValidator(config)
            
            results = {
                'total': len(sermon_ids),
                'completed': 0,
                'valid': 0,
                'invalid': 0,
                'errors': 0,
                'details': []
            }
            
            for i, sermon_id in enumerate(sermon_ids):
                try:
                    # Update progress
                    progress = (i + 1) / len(sermon_ids)
                    self.db.update_processing_status(
                        sermon_id, 
                        'validation', 
                        'processing', 
                        progress * 100,
                        f"Validating {i+1}/{len(sermon_ids)}"
                    )
                    
                    if progress_callback:
                        progress_callback(progress, f"Validating sermon {sermon_id}")
                    
                    # Validate single sermon
                    validation_result = validator.validate_single_sermon(sermon_id)
                    
                    if validation_result:
                        # Save to database
                        self.db.save_validation_result(
                            sermon_id,
                            validation_result.is_valid,
                            validation_result.validation_score,
                            validation_result.validation_reason,
                            [], # criteria_met - would need to be extracted from result
                            []  # criteria_failed - would need to be extracted from result
                        )
                        
                        results['details'].append({
                            'sermon_id': sermon_id,
                            'is_valid': validation_result.is_valid,
                            'score': validation_result.validation_score,
                            'reason': validation_result.validation_reason
                        })
                        
                        if validation_result.is_valid:
                            results['valid'] += 1
                        else:
                            results['invalid'] += 1
                    else:
                        results['errors'] += 1
                        results['details'].append({
                            'sermon_id': sermon_id,
                            'error': 'Could not validate sermon'
                        })
                    
                    results['completed'] += 1
                    
                    # Mark as completed
                    self.db.update_processing_status(
                        sermon_id, 
                        'validation', 
                        'completed', 
                        100.0,
                        f"Validation complete"
                    )
                    
                except Exception as e:
                    logger.error(f"Error validating sermon {sermon_id}: {e}")
                    results['errors'] += 1
                    results['details'].append({
                        'sermon_id': sermon_id,
                        'error': str(e)
                    })
                    
                    self.db.update_processing_status(
                        sermon_id, 
                        'validation', 
                        'failed', 
                        0.0,
                        f"Error: {str(e)}"
                    )
            
            return results
            
        except Exception as e:
            logger.error(f"Validation process failed: {e}")
            raise
    
    def process_sermon_async(self, sermon_id: str, options: Dict) -> None:
        """
        Process a single sermon asynchronously with progress tracking
        
        Args:
            sermon_id: Sermon ID to process
            options: Processing options dictionary
        """
        try:
            import sermon_updater
            
            # Update status
            self.db.update_processing_status(
                sermon_id, 
                'processing', 
                'starting', 
                0.0,
                "Initializing processing"
            )
            
            # Process sermon with options
            result = sermon_updater.process_single_sermon(
                sermon_id,
                no_upload=options.get('dry_run', False),
                verbose=options.get('verbose', False),
                skip_audio=options.get('metadata_only', False),
                force_description=options.get('force_description', False),
                force_hashtags=options.get('force_hashtags', False),
                no_metadata=options.get('no_metadata', False)
            )
            
            if result:
                self.db.update_processing_status(
                    sermon_id, 
                    'processing', 
                    'completed', 
                    100.0,
                    "Processing completed successfully"
                )
            else:
                self.db.update_processing_status(
                    sermon_id, 
                    'processing', 
                    'failed', 
                    0.0,
                    "Processing failed"
                )
                
        except Exception as e:
            logger.error(f"Error processing sermon {sermon_id}: {e}")
            self.db.update_processing_status(
                sermon_id, 
                'processing', 
                'failed', 
                0.0,
                f"Error: {str(e)}"
            )
    
    def get_processing_status(self, sermon_id: str = None) -> List[Dict]:
        """Get current processing status"""
        return self.db.get_processing_status(sermon_id)
    
    def get_validation_results(self, sermon_ids: List[str] = None) -> List[Dict]:
        """Get validation results"""
        return self.db.get_validation_results(sermon_ids)
    
    def cleanup_old_status(self):
        """Clean up old processing status records"""
        self.db.cleanup_old_records(days=7)


# Global processor instance
_processor = None

def get_processor() -> UIProcessor:
    """Get global processor instance"""
    global _processor
    if _processor is None:
        _processor = UIProcessor()
    return _processor


def show_validation_progress(sermon_ids: List[str]):
    """
    Show real-time validation progress in Streamlit
    
    Args:
        sermon_ids: List of sermon IDs being validated
    """
    processor = get_processor()
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    def progress_callback(progress: float, message: str):
        progress_bar.progress(progress)
        status_text.text(message)
    
    # Run validation
    with st.spinner('🔍 Running validation...'):
        try:
            results = processor.validate_sermons(sermon_ids, progress_callback)
            
            # Show results
            progress_bar.progress(1.0)
            status_text.text("✅ Validation completed!")
            
            # Display summary
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total", results['total'])
            with col2:
                st.metric("Valid", results['valid'])
            with col3:
                st.metric("Invalid", results['invalid'])
            with col4:
                st.metric("Errors", results['errors'])
            
            return results
            
        except Exception as e:
            st.error(f"❌ Validation failed: {e}")
            return None


def show_processing_status():
    """Show current processing status"""
    processor = get_processor()
    
    status_records = processor.get_processing_status()
    
    if not status_records:
        st.info("No processing operations in progress")
        return
    
    # Group by operation type
    by_operation = {}
    for record in status_records[:20]:  # Show recent 20
        op = record['operation']
        if op not in by_operation:
            by_operation[op] = []
        by_operation[op].append(record)
    
    for operation, records in by_operation.items():
        st.subheader(f"📊 {operation.title()} Operations")
        
        for record in records:
            col1, col2, col3, col4 = st.columns([2, 1, 1, 3])
            
            with col1:
                st.text(f"Sermon {record['sermon_id']}")
            
            with col2:
                status_color = {
                    'processing': '🟡',
                    'completed': '🟢', 
                    'failed': '🔴',
                    'starting': '🔵'
                }.get(record['status'], '⚪')
                st.text(f"{status_color} {record['status']}")
            
            with col3:
                st.progress(record['progress'] / 100.0)
            
            with col4:
                st.text(record['message'] or '')