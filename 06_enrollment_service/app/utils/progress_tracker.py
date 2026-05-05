"""
Progress tracking for enrollment workflow
"""
from typing import Dict, Callable, Optional
from datetime import datetime
import asyncio


class EnrollmentProgress:
    """Tracks progress of enrollment workflow"""
    
    STAGES = {
        'started': {'progress': 0, 'message': 'Enrollment started'},
        'validating': {'progress': 10, 'message': 'Validating input data'},
        'saving_files': {'progress': 20, 'message': 'Saving uploaded files'},
        'processing_face': {'progress': 35, 'message': 'Processing face embedding'},
        'processing_voice': {'progress': 55, 'message': 'Processing voice embedding'},
        'registering': {'progress': 75, 'message': 'Registering user'},
        'storing_data': {'progress': 85, 'message': 'Storing enrollment data'},
        'cleanup': {'progress': 95, 'message': 'Cleaning up temporary files'},
        'completed': {'progress': 100, 'message': 'Enrollment completed successfully'}
    }
    
    def __init__(self, user_name: str):
        self.user_name = user_name
        self.current_stage = 'started'
        self.start_time = datetime.utcnow()
        self.stages_completed = []
        self.error = None
        self.callbacks = []
    
    def update_stage(self, stage: str, custom_message: Optional[str] = None):
        """
        Update current stage
        
        Args:
            stage: Stage name from STAGES
            custom_message: Optional custom message
        """
        if stage not in self.STAGES:
            raise ValueError(f"Invalid stage: {stage}")
        
        self.current_stage = stage
        self.stages_completed.append({
            'stage': stage,
            'timestamp': datetime.utcnow().isoformat()
        })
        
        # Trigger callbacks
        progress_data = self.get_progress()
        if custom_message:
            progress_data['message'] = custom_message
        
        for callback in self.callbacks:
            callback(progress_data)
    
    def add_callback(self, callback: Callable):
        """Add progress callback function"""
        self.callbacks.append(callback)
    
    def set_error(self, error_message: str):
        """Set error state"""
        self.error = error_message
        self.current_stage = 'error'
    
    def get_progress(self) -> Dict:
        """Get current progress information"""
        if self.error:
            return {
                'status': 'error',
                'stage': 'error',
                'progress_percentage': 0,
                'message': self.error,
                'user_name': self.user_name
            }
        
        stage_info = self.STAGES.get(self.current_stage, self.STAGES['started'])
        
        return {
            'status': 'completed' if self.current_stage == 'completed' else 'in_progress',
            'stage': self.current_stage,
            'progress_percentage': stage_info['progress'],
            'message': stage_info['message'],
            'user_name': self.user_name,
            'elapsed_time_seconds': (datetime.utcnow() - self.start_time).total_seconds()
        }
    
    def get_summary(self) -> Dict:
        """Get complete progress summary"""
        return {
            'user_name': self.user_name,
            'current_stage': self.current_stage,
            'progress': self.get_progress(),
            'stages_completed': self.stages_completed,
            'start_time': self.start_time.isoformat(),
            'elapsed_time_seconds': (datetime.utcnow() - self.start_time).total_seconds(),
            'error': self.error
        }