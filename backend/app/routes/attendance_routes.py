from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, session, current_app
from werkzeug.utils import secure_filename
import os
import pickle
import numpy as np
import cv2
import base64
import io
import threading
import time
from threading import Lock
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from PIL import Image
from ..services.face_recognition import FaceRecognitionService, get_face_recognition_service
from ..db.mongo_client import get_collections
from ..services.attendance import AttendanceService
from ..utils.cloudinary_utils import get_pickle_from_cloudinary

bp = Blueprint('attendance', __name__, url_prefix='/attendance')

@bp.app_context_processor
def inject_faculty_info():
    """Provide photo_path, email, and faculty name to all attendance templates."""
    from flask import url_for
    default_photo = 'img/faculty.jpg'
    
    def resolve_photo_url(path):
        if not path:
            return url_for('static', filename=default_photo)
        if path.startswith('http') or path.startswith('https'):
            return path
        return url_for('static', filename=path)

    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return {
            'photo_path': url_for('static', filename=default_photo),
            'is_admin': False,
            'email': '',
            'faculty': 'Faculty'
        }

    try:
        collections = get_collections()
        user = collections['faculty'].find_one({'email': faculty_email})
        if not user:
            return {
                'photo_path': url_for('static', filename=default_photo),
                'is_admin': False,
                'email': faculty_email,
                'faculty': 'Faculty'
            }
        
        raw_path = user.get('photo_path', default_photo)
        faculty_name = user.get('name', faculty_email.split('@')[0].title())
        return {
            'photo_path': resolve_photo_url(raw_path),
            'is_admin': user.get('role') == 'super_admin',
            'email': faculty_email,
            'faculty': faculty_name
        }
    except Exception:
        return {
            'photo_path': url_for('static', filename=default_photo),
            'is_admin': False,
            'email': faculty_email if faculty_email else '',
            'faculty': 'Faculty'
        }

# Global variables for live attendance tracking
live_attendance_sessions = {}  # Store active sessions
session_lock = Lock()  # Thread-safe access to sessions

# Add logging for debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_LIVE_TARGET_FPS = 12
DEFAULT_LIVE_FRAME_SCALE = 0.5


def get_frame_processing_logger():
    """Return a dedicated logger for live frame processing logs."""
    frame_logger = logging.getLogger('attendance.frame_processing')
    if frame_logger.handlers:
        return frame_logger

    log_path = os.environ.get(
        'FRAME_PROCESSING_LOG',
        os.path.join(current_app.config.get('ATTENDANCE_DIR', 'attendance_logs'), 'frame_processing.log')
    )
    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    handler = RotatingFileHandler(
        log_path,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding='utf-8'
    )
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    frame_logger.addHandler(handler)
    frame_logger.setLevel(logging.INFO)
    frame_logger.propagate = False
    return frame_logger


def _get_faculty_identity(faculty_email: str):
    """Return lowercased faculty name for matching timetable using Mongo only."""
    collections = get_collections()
    doc = collections['faculty'].find_one({'email': faculty_email})
    if doc and doc.get('name'):
        return str(doc.get('name')).strip().lower()
    return None


def _get_todays_lectures(faculty_email: str):
    """Fetch today's lectures for a faculty from Mongo timetable (fallback returns [])."""
    faculty_name = _get_faculty_identity(faculty_email)
    collections = get_collections()
    today = datetime.now().strftime('%A')
    query = {
        'day': today,
        '$or': [
            {'faculty_email': faculty_email}
        ]
    }
    if faculty_name:
        query['$or'].append({'faculty_name': faculty_name})

    lectures = list(collections['timetable'].find(query, {'_id': 0}))
    for lec in lectures:
        lec['id'] = f"{lec.get('branch', '')}_{lec.get('semester', '')}"
    return lectures, faculty_name


def _find_lecture(branch: str, semester: str, faculty_email: str, faculty_name: str = None):
    """Lookup a lecture in Mongo timetable by class and faculty (email/name)."""
    faculty_name = faculty_name or _get_faculty_identity(faculty_email)
    collections = get_collections()
    try:
        sem_value = int(semester)
    except Exception:
        sem_value = semester
    query = {
        'branch': branch,
        'semester': sem_value,
        '$or': [
            {'faculty_email': faculty_email}
        ]
    }
    if faculty_name:
        query['$or'].append({'faculty_name': faculty_name})
    return collections['timetable'].find_one(query, {'_id': 0})


def _parse_class_id(class_id: str):
    parts = [str(part).strip() for part in str(class_id or "").split('_') if str(part).strip()]
    branch = parts[0] if len(parts) >= 1 else ""
    semester = parts[1] if len(parts) >= 2 else ""
    section = parts[2] if len(parts) >= 3 else ""
    return branch, semester, section


def _load_encoding_data_for_class(class_id: str):
    branch, semester, section = _parse_class_id(class_id)
    candidates = []

    if branch and semester and section:
      candidates.append(f"{branch}_{semester}_{section}")
    if branch and semester:
      candidates.append(f"{branch}_{semester}")
    if class_id and class_id not in candidates:
      candidates.insert(0, class_id)

    split_dir = current_app.config.get('SPLIT_DIR', 'split_encodings')
    seen = set()

    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)

        cloud_data = get_pickle_from_cloudinary(candidate)
        if cloud_data:
            return cloud_data, candidate, 'cloud'

        local_path = os.path.join(split_dir, f"{candidate}.pickle")
        if os.path.exists(local_path):
            try:
                with open(local_path, 'rb') as handle:
                    return pickle.load(handle), candidate, 'local'
            except Exception as exc:
                logger.error(f"Failed reading local encoding file {local_path}: {exc}")

    return None, None, None

@bp.route('/', methods=['GET'])
def attendance():
    """Attendance page with class selection"""
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return redirect('/multilogin')
    lectures_today, faculty_name = _get_todays_lectures(faculty_email)
    if not lectures_today:
        flash("No timetable found for today. Please upload or sync timetable.", "error")
        lectures_today = []
    return render_template('faculty/attendance.html', faculty=faculty_name or "Faculty", lectures_today=lectures_today)

@bp.route('/upload', methods=['POST'])
def attendance_upload():
    """Upload video for attendance processing"""
    try:
        faculty_email = session.get('faculty_email')
        if not faculty_email:
            logger.error("No faculty email in session")
            return jsonify({'error': 'Not logged in'}), 401
        
        class_id = request.form.get('class')
        video = request.files.get('video')
        
        if not class_id or not video:
            logger.error(f"Missing class_id: {class_id}, video: {video}")
            flash('Please select a class and upload a video.', 'error')
            return redirect(url_for('attendance.attendance'))
        
        logger.info(f"Processing video upload for class {class_id} by faculty {faculty_email}")
        
        faculty_name = _get_faculty_identity(faculty_email)
        if not faculty_name:
            logger.error(f"Faculty {faculty_email} not found in Mongo faculty collection")
            flash("Faculty not found.", "error")
            return redirect('/multilogin')
        
        # Save video temporarily
        os.makedirs('temp_uploads', exist_ok=True)
        video_path = os.path.join('temp_uploads', secure_filename(video.filename))
        video.save(video_path)
        logger.info(f"Video saved to {video_path}")
        
        # 1. Try Cloudinary first
        data = get_pickle_from_cloudinary(class_id)
        
        # 2. Local Fallback
        if not data:
            split_dir = current_app.config.get('SPLIT_DIR', 'split_encodings')
            local_path = os.path.join(split_dir, f"{class_id}.pickle")
            if os.path.exists(local_path):
                try:
                    with open(local_path, 'rb') as f:
                        data = pickle.load(f)
                    logger.info(f"✓ Loaded {class_id} from local storage")
                except Exception as e:
                    logger.error(f"Error loading local pickle: {e}")

        if not data:
            logger.error(f"Encoding data not found for class: {class_id}")
            flash('Encoding file not found (Cloud or Local).', 'error')
            os.remove(video_path)
            return redirect(url_for('attendance.attendance'))
        
        try:
            known_encodings = np.array(data['encodings'])
            known_metadata = data.get('metadata', [])
        except Exception as e:
            logger.error(f"Error parsing encoding data: {e}")
            flash('Error parsing face data. Please try again.', 'error')
            os.remove(video_path)
            return redirect(url_for('attendance.attendance'))
        except (ModuleNotFoundError, ImportError, ValueError) as e:
            logger.error(f"Could not load pickle file due to version incompatibility: {e}")
            flash('Encoding file is incompatible with current numpy version. Please re-register students.', 'error')
            os.remove(video_path)
            return redirect(url_for('attendance.attendance'))
        
        logger.info(f"Loaded {len(known_encodings)} encodings for {len(known_metadata)} students")
        
        # Initialize face recognition service
        try:
            face_service = FaceRecognitionService()
            logger.info("Face recognition service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize face recognition service: {e}")
            os.remove(video_path)
            flash('Failed to initialize face recognition service.', 'error')
            return redirect(url_for('attendance.attendance'))
        
        # Check if remote mode and warn user
        if face_service.mode == 'remote':
            logger.warning("Remote mode detected for video upload - will process frames via remote service")
        
        # Process video
        video_capture = cv2.VideoCapture(video_path)
        if not video_capture.isOpened():
            logger.error(f"Failed to open video file: {video_path}")
            os.remove(video_path)
            flash('Failed to process video file.', 'error')
            return redirect(url_for('attendance.attendance'))
        
        recognized_students = set()
        tolerance = 0.85
        frame_count = 0
        
        # Get video FPS and determine frame skip rate
        video_fps = int(video_capture.get(cv2.CAP_PROP_FPS)) or 30
        target_fps = int(os.environ.get('VIDEO_PROCESSING_FPS', '20'))
        frame_skip = max(1, int(video_fps / target_fps))
        
        logger.info(f"Starting video processing... (Video FPS: {video_fps}, Target FPS: {target_fps}, Frame Skip: {frame_skip})")
        
        while True:
            ret, frame = video_capture.read()
            if not ret:
                break
            
            frame_count += 1
            
            # Skip frames based on target FPS
            if (frame_count - 1) % frame_skip != 0:
                continue
            
            if frame_count % (frame_skip * 10) == 0:  # Log every ~10 processed frames
                logger.info(f"Processing frame {frame_count} (Total read: {frame_count})")
            
            small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
            rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
            
            try:
                # Use proper recognition method that handles both remote and local modes
                recognition_results = face_service.recognize_faces_in_frame(rgb_small_frame, known_encodings, known_metadata, tolerance)
                for result in recognition_results:
                    name = result.get('roll_no') or result.get('name')
                    distance = result.get('distance', 0)
                    recognized_students.add(name)
                    logger.info(f"Recognized student: {name} (distance: {distance:.3f})")
            except Exception as e:
                logger.error(f"Error processing frame {frame_count}: {e}")
                continue
        
        video_capture.release()
        os.remove(video_path)
        logger.info(f"Video processing completed. Recognized {len(recognized_students)} students")
        
        # Mark attendance in DB for recognized students
        # Get lecture info from Mongo timetable
        branch, semester, _section = _parse_class_id(class_id)
        lecture = _find_lecture(branch, semester, faculty_email, faculty_name)
        if not lecture:
            logger.error(f"Lecture info not found for class {class_id} in Mongo timetable")
            flash('Lecture info not found.', 'error')
            return redirect(url_for('attendance.attendance'))
        
        subject = lecture.get('subject')
        section = lecture.get('section')
        classroom = lecture.get('classroom')
        start_time = lecture.get('start_time')
        end_time = lecture.get('end_time')
        date_str = datetime.now().strftime('%Y-%m-%d')
        
        # Save to database
        collections = get_collections()
        saved_count = 0
        for name in recognized_students:
            collections['attendance'].update_one(
                {
                    'date': date_str,
                    'subject': subject,
                    'faculty_email': faculty_email,
                    'branch': branch,
                    'semester': int(semester),
                    'section': section,
                    'student.roll_no': name  # roll_no stored in name for live flow
                },
                {
                    '$set': {
                        'date': date_str,
                        'subject': subject,
                        'faculty_email': faculty_email,
                        'classroom': classroom,
                        'branch': branch,
                        'semester': int(semester),
                        'section': section,
                        'student': {
                            'roll_no': name,
                            'name': name,
                            'status': 'Present'
                        }
                    }
                },
                upsert=True
            )
            saved_count += 1
        
        logger.info(f"Saved {saved_count} attendance records to database")
        
        return render_template('faculty/attendance_result.html', present_students=recognized_students, lecture=lecture)
        
    except Exception as e:
        logger.error(f"Unexpected error in attendance_upload: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Clean up video file if it exists
        try:
            if 'video_path' in locals() and os.path.exists(video_path):
                os.remove(video_path)
        except:
            pass
        
        flash(f'An error occurred while processing the video: {str(e)}', 'error')
        return redirect(url_for('attendance.attendance'))

# Manual Attendance Routes
@bp.route('/manual_attendance', methods=['GET', 'POST'])
def manual_attendance():
    """Manual attendance selection page"""
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return redirect('/login')
    lectures, faculty_name = _get_todays_lectures(faculty_email)
    if not lectures:
        flash("No timetable found for today. Please upload or sync timetable.", "error")
    return render_template('faculty/manual_attendance_select.html', lectures=lectures)

@bp.route('/manual_attendance/select_students', methods=['POST'])
def manual_attendance_select_students():
    """Select students for manual attendance"""
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return redirect('/login')

    # Get selected lecture info
    branch = request.form.get('branch')
    semester = request.form.get('semester')
    section = request.form.get('section')
    subject = request.form.get('subject')
    start_time = request.form.get('start_time')
    end_time = request.form.get('end_time')
    classroom = request.form.get('classroom')

    # Get students for this class from MongoDB
    collections = get_collections()
    date_str = datetime.now().strftime('%Y-%m-%d')

    # Existing attendance map for this class/date to avoid double marking
    existing = collections['attendance'].find({
        "date": date_str,
        "faculty_email": faculty_email,
        "branch": branch,
        "semester": int(semester),
        "section": section,
        "subject": subject
    })
    status_map = {}
    for doc in existing:
        roll_no = doc.get("student", {}).get("roll_no")
        status = doc.get("student", {}).get("status")
        if roll_no:
            status_map[roll_no] = status

    students_cursor = collections['students'].find({
        "branch": branch,
        "semester": int(semester),
        "section": section
    })
    students = []
    for s in students_cursor:
        roll_no = s.get("roll_no")
        status = status_map.get(roll_no)
        students.append({
            "Roll Number": roll_no,
            "Student Name": s.get("name"),
            "status": status,
            "status_exists": status is not None
        })

    lecture_info = {
        'branch': branch,
        'semester': semester,
        'section': section,
        'subject': subject,
        'start_time': start_time,
        'end_time': end_time,
        'classroom': classroom
    }
    return render_template('faculty/manual_attendance_mark.html', students=students, lecture=lecture_info)

@bp.route('/manual_attendance/submit', methods=['POST'])
def manual_attendance_submit():
    """Submit manual attendance"""
    faculty_email = session.get('faculty_email')
    faculty_name = session.get('faculty_name')
    if not faculty_email:
        return redirect('/login')

    # Get lecture info
    branch = request.form.get('branch')
    semester = request.form.get('semester')
    section = request.form.get('section')
    subject = request.form.get('subject')
    start_time = request.form.get('start_time')
    end_time = request.form.get('end_time')
    classroom = request.form.get('classroom')
    date_str = datetime.now().strftime('%Y-%m-%d')

    # Get all student roll numbers and names for this class from MongoDB
    collections = get_collections()
    students_cursor = collections['students'].find({
        "branch": branch,
        "semester": int(semester),
        "section": section
    })
    roll_name_map = {}
    roll_numbers = []
    for s in students_cursor:
        roll_no = s.get("roll_no")
        name = s.get("name")
        roll_name_map[roll_no] = name
        roll_numbers.append(roll_no)

    # Get present students from form
    present_rolls = request.form.getlist('present')

    # Upsert attendance per student (avoid duplicates, allow edits)
    for roll in roll_numbers:
        status = 'Present' if roll in present_rolls else 'Absent'
        name = roll_name_map.get(roll, '')
        collections['attendance'].update_one(
            {
                'date': date_str,
                'subject': subject,
                'faculty_email': faculty_email,
                'branch': branch,
                'semester': int(semester),
                'section': section,
                'student.roll_no': roll
            },
            {
                '$set': {
                    'date': date_str,
                    'subject': subject,
                    'faculty_email': faculty_email,
                    'classroom': classroom,
                    'branch': branch,
                    'semester': int(semester),
                    'section': section,
                    'student': {
                        'roll_no': roll,
                        'name': name,
                        'status': status
                    }
                }
            },
            upsert=True
        )
    flash('Attendance marked successfully!', 'success')
    return redirect(url_for('attendance.manual_attendance'))


@bp.route('/mark_attendance', methods=['POST'])
def mark_attendance_alias():
    """Backward-compatible alias used by legacy frontend JS."""
    return manual_attendance_submit()

# Live Attendance Routes
@bp.route('/live_frame', methods=['POST'])
def attendance_live_frame():
    """Process single frame for live attendance"""
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return jsonify({'error': 'Not logged in'}), 401
    
    class_id = request.form.get('class_id')
    img_data = request.form.get('frame')
    if not class_id or not img_data:
        return jsonify({'error': 'Missing data'}), 400
    
    # 1. Try Cloudinary first
    data = get_pickle_from_cloudinary(class_id)
    
    # 2. Local Fallback if Cloudinary fails or is not configured
    if not data:
        split_dir = current_app.config.get('SPLIT_DIR', 'split_encodings')
        local_path = os.path.join(split_dir, f"{class_id}.pickle")
        if os.path.exists(local_path):
            try:
                with open(local_path, 'rb') as f:
                    data = pickle.load(f)
                logger.info(f"✓ Loaded {class_id} from local storage")
            except Exception as e:
                logger.error(f"Error loading local pickle: {e}")
    
    if not data:
        return jsonify({'error': 'Encoding data not found (Cloud or Local)'}), 404
        
    try:
        known_encodings = np.array(data['encodings'])
        known_metadata = data.get('metadata', [])
    except Exception as e:
        logger.error(f"Error parsing encoding data: {e}")
        return jsonify({'error': 'Error parsing face data'}), 500
    except (ModuleNotFoundError, ImportError, ValueError) as e:
        logger.error(f"Could not load pickle file due to version incompatibility: {e}")
        return jsonify({'error': 'Encoding file is incompatible with current numpy version'}), 500
    
    face_service = FaceRecognitionService()
    img_bytes = base64.b64decode(img_data.split(',')[1])
    img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
    frame = np.array(img)
    faces = face_service.get_faces(frame)
    recognized = set()
    tolerance = 0.85
    
    for face in faces:
        embedding = face.normed_embedding
        dists = np.linalg.norm(known_encodings - embedding, axis=1)
        min_dist = np.min(dists)
        min_idx = np.argmin(dists)
        if min_dist < tolerance:
            name = known_metadata[min_idx].get('roll_no') or known_metadata[min_idx].get('name')
            recognized.add(name)
    
    return jsonify({'recognized': list(recognized)})

@bp.route('/live_submit', methods=['POST'])
def attendance_live_submit():
    """Submit live attendance results"""
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return jsonify({'error': 'Not logged in'}), 401
    
    class_id = request.form.get('class_id')
    recognized_students = request.form.getlist('recognized[]')
    if not class_id or not recognized_students:
        return jsonify({'error': 'Missing data'}), 400
    
    faculty_name = _get_faculty_identity(faculty_email)
    if not faculty_name:
        return jsonify({'error': 'Faculty not found'}), 404

    branch, semester, _section = _parse_class_id(class_id)
    lecture = _find_lecture(branch, semester, faculty_email, faculty_name)
    if not lecture:
        return jsonify({'error': 'Lecture info not found'}), 404

    subject = lecture.get('subject')
    section = lecture.get('section')
    classroom = lecture.get('classroom')
    start_time = lecture.get('start_time')
    end_time = lecture.get('end_time')
    date_str = datetime.now().strftime('%Y-%m-%d')
    
    collections = get_collections()
    for name in recognized_students:
        collections['attendance'].insert_one({
            'date': date_str,
            'subject': subject,
            'faculty_email': faculty_email,
            'classroom': classroom,
            'branch': branch,
            'semester': int(semester),
            'section': section,
            'student': {
                'name': name,
                'status': 'Present'
            }
        })
    
    return jsonify({'success': True, 'present': recognized_students})

@bp.route('/model_status')
def attendance_model_status():
    """Check if face recognition model is ready - FAST endpoint with timeout"""
    try:
        face_service = FaceRecognitionService()
        
        # For remote mode, do NOT do health check (can be slow/hang)
        # Just verify inference client exists
        if face_service.mode == 'remote':
            if face_service.inference_client:
                logger.debug("✓ Remote inference service client initialized")
                return jsonify({'ready': True})
            else:
                logger.error("Remote inference service client not initialized")
                return jsonify({'ready': False, 'error': 'Remote service not initialized'})
        
        # For local/hybrid mode, do NOT test with images (expensive)
        # Just verify models are initialized
        if face_service.mode in ['local', 'hybrid']:
            if face_service.face_app:
                logger.debug("✓ Local face recognition model is ready")
                return jsonify({'ready': True})
            else:
                # Try to initialize if not already done
                try:
                    face_service._initialize_face_app()
                    logger.debug("✓ Local face recognition model initialized")
                    return jsonify({'ready': True})
                except Exception as init_err:
                    logger.error(f"Failed to initialize local model: {init_err}")
                    return jsonify({'ready': False, 'error': 'Model initialization failed'})
        
        return jsonify({'ready': False, 'error': 'Unknown recognition mode'})
    except Exception as e:
        logger.error(f"Model status check failed: {e}")
        # Return ready=True anyway for remote mode to avoid blocking UI
        if 'remote' in str(e).lower():
            return jsonify({'ready': True, 'warning': 'Could not verify remote service, proceeding anyway'})
        return jsonify({'ready': False, 'error': str(e)})

# Live attendance session management
@bp.route('/start_session', methods=['POST'])
def start_attendance_session():
    """Start a live attendance session"""
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return jsonify({'error': 'Not logged in'}), 401
    
    class_id = request.form.get('class_id')
    if not class_id:
        return jsonify({'error': 'Missing class_id'}), 400
    
    logger.info(f"Starting attendance session for faculty {faculty_email}, class {class_id}")
    
    # Load and cache encoding data once per session
    data, resolved_class_id, source = _load_encoding_data_for_class(class_id)
    if not data:
        logger.error(f"Encoding data not found for class: {class_id}")
        return jsonify({'error': 'Encoding file not found for this class'}), 404

    try:
        known_encodings = np.array(data['encodings'])
        known_metadata = data.get('metadata', [])
    except Exception as e:
        logger.error(f"Error parsing encoding data for {resolved_class_id or class_id}: {e}")
        return jsonify({'error': 'Error parsing face data'}), 500

    if len(known_encodings) == 0:
        logger.warning(f"No face encodings found for class {resolved_class_id or class_id}")
        return jsonify({'error': 'No face encodings found for this class. Please register student faces first.'}), 404

    try:
        face_service = get_face_recognition_service()
    except Exception as e:
        logger.error(f"Failed to initialize cached face recognition service: {e}")
        return jsonify({'error': 'Failed to initialize face recognition service'}), 500
    
    # Create unique session ID
    session_id = f"{faculty_email}_{resolved_class_id or class_id}_{int(time.time())}"
    
    # Get target FPS for frame processing
    target_fps = int(os.environ.get('VIDEO_PROCESSING_FPS', str(DEFAULT_LIVE_TARGET_FPS)))
    frame_skip = max(1, int(30 / target_fps))  # Assume 30fps from client
    frame_scale = float(os.environ.get('LIVE_FRAME_SCALE', str(DEFAULT_LIVE_FRAME_SCALE)))
    frame_scale = min(max(frame_scale, 0.2), 1.0)
    
    # Initialize session data
    with session_lock:
        live_attendance_sessions[session_id] = {
            'faculty_email': faculty_email,
            'class_id': resolved_class_id or class_id,
            'face_service': face_service,
            'known_encodings': known_encodings,
            'known_metadata': known_metadata,
            'recognized_students': set(),
            'is_active': True,
            'start_time': time.time(),
            'thread': None,
            'model_verified': False,
            'frame_count': 0,
            'target_fps': target_fps,
            'frame_skip': frame_skip,
            'frame_scale': frame_scale
        }
    
    logger.info(
        f"Created session {session_id} with cached recognizer from {source or 'unknown'}, "
        f"{len(known_encodings)} encodings, FPS {target_fps}, scale {frame_scale:.2f}"
    )
    
    return jsonify({
        'success': True,
        'session_id': session_id,
        'message': 'Attendance session started'
    })

@bp.route('/process_frame', methods=['POST'])
def process_attendance_frame():
    """Process a frame in live attendance session"""
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return jsonify({'error': 'Not logged in'}), 401
    frame_logger = get_frame_processing_logger()
    
    session_id = request.form.get('session_id')
    img_data = request.form.get('frame')
    
    if not session_id or not img_data:
        return jsonify({'error': 'Missing session_id or frame data'}), 400
    
    with session_lock:
        if session_id not in live_attendance_sessions:
            return jsonify({'error': 'Session not found'}), 404
        
        session_data = live_attendance_sessions[session_id]
        if not session_data['is_active']:
            return jsonify({'error': 'Session is not active'}), 400
        
        # Get class_id from session data
        class_id = session_data['class_id']
        known_encodings = session_data['known_encodings']
        known_metadata = session_data['known_metadata']
        face_service = session_data['face_service']
        frame_scale = session_data.get('frame_scale', DEFAULT_LIVE_FRAME_SCALE)
        
        # Increment and check frame counter for FPS control
        session_data['frame_count'] += 1
        frame_skip = session_data.get('frame_skip', 1)
        current_frame = session_data['frame_count']
        
        # Skip frames based on target FPS (only process every Nth frame)
        if (current_frame - 1) % frame_skip != 0:
            frame_logger.info(
                f"Session {session_id}: skipping frame {current_frame} "
                f"(target FPS: {session_data.get('target_fps', DEFAULT_LIVE_TARGET_FPS)}, "
                f"frame_skip: {frame_skip})"
            )
            return jsonify({'success': True, 'processed': False, 'skipped_for_fps': True})
    
    try:
        frame_logger.info(f"Session {session_id}: processing frame {current_frame} for class {class_id}")

        # Process the frame
        img_bytes = base64.b64decode(img_data.split(',')[1])
        img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
        frame = np.array(img)

        if frame_scale < 1.0:
            frame = cv2.resize(frame, (0, 0), fx=frame_scale, fy=frame_scale)
        
        frame_logger.info(
            f"Session {session_id}: frame {current_frame} prepared with shape {frame.shape}, "
            f"scale {frame_scale:.2f}, known encodings {len(known_encodings)}"
        )
        
        tolerance = 0.85
        recognized_in_frame = set()
        
        # Use proper recognition method (handles both remote and local modes)
        recognized_results = face_service.recognize_faces_in_frame(frame, known_encodings, known_metadata, tolerance)
        
        frame_logger.info(
            f"Session {session_id}: frame {current_frame} detection complete, "
            f"recognized {len(recognized_results)} face(s)"
        )
        
        with session_lock:
            if session_id in live_attendance_sessions:
                live_attendance_sessions[session_id]['model_verified'] = True
        
        for result in recognized_results:
            roll_no = result.get('roll_no', '')
            name = result.get('name', '')
            distance = result.get('distance', 0)
            student_id = f"{roll_no}_{name}" if roll_no else name
            recognized_in_frame.add(student_id)
            frame_logger.info(
                f"Session {session_id}: frame {current_frame} matched "
                f"name={name}, roll_no={roll_no}, distance={distance:.3f}"
            )

        if not recognized_in_frame:
            frame_logger.info(f"Session {session_id}: frame {current_frame} had no known recognition matches")
        
        # Update session with new recognitions
        with session_lock:
            if session_id in live_attendance_sessions:
                session_data = live_attendance_sessions[session_id]
                session_data['recognized_students'].update(recognized_in_frame)
        
        with session_lock:
            current_verified = live_attendance_sessions.get(session_id, {}).get('model_verified', False)
            total_recognized = len(live_attendance_sessions.get(session_id, {}).get('recognized_students', set()))
        frame_logger.info(
            f"Session {session_id}: frame {current_frame} complete, "
            f"session total recognized={total_recognized}, model_verified={current_verified}"
        )
        return jsonify({
            'success': True,
            'recognized_in_frame': list(recognized_in_frame),
            'total_recognized': total_recognized,
            'model_verified': current_verified
        })
        
    except Exception as e:
        frame_logger.exception(f"Session {session_id}: processing error on frame {current_frame}: {e}")
        logger.exception(f"Session {session_id}: processing error on frame {current_frame}: {e}")
        return jsonify({'error': f'Processing error: {str(e)}'}), 500

@bp.route('/poll_session', methods=['GET'])
def poll_attendance_session():
    """Poll session status for live attendance"""
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return jsonify({'error': 'Not logged in'}), 401
    
    session_id = request.args.get('session_id')
    if not session_id:
        return jsonify({'error': 'Missing session_id'}), 400
    
    with session_lock:
        if session_id not in live_attendance_sessions:
            return jsonify({'error': 'Session not found'}), 404
        
        session_data = live_attendance_sessions[session_id]
        if not session_data['is_active']:
            return jsonify({'error': 'Session is not active'}), 400
        
        # Get current recognized students
        recognized_students = list(session_data['recognized_students'])
        model_verified = session_data.get('model_verified', False)
        
        return jsonify({
            'success': True,
            'recognized_students': recognized_students,
            'count': len(recognized_students),
            'is_active': session_data['is_active'],
            'model_verified': model_verified
        })

@bp.route('/stop_session', methods=['POST'])
def stop_attendance_session():
    """Stop live attendance session and save results"""
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return jsonify({'error': 'Not logged in'}), 401
    
    session_id = request.form.get('session_id')
    if not session_id:
        return jsonify({'error': 'Missing session_id'}), 400
    
    logger.info(f"Stopping attendance session {session_id} for faculty {faculty_email}")
    
    with session_lock:
        if session_id not in live_attendance_sessions:
            logger.error(f"Session {session_id} not found")
            return jsonify({'error': 'Session not found'}), 404
        
        session_data = live_attendance_sessions[session_id]
        session_data['is_active'] = False
        recognized_students = list(session_data['recognized_students'])
        
        logger.info(f"Session {session_id}: Stopping with {len(recognized_students)} recognized students")
        
        # Get lecture info for database insertion
        class_id = session_data['class_id']
        faculty_name = _get_faculty_identity(faculty_email)
        if not faculty_name:
            logger.error(f"Faculty {faculty_email} not found in Mongo faculty collection")
            return jsonify({'error': 'Faculty not found'}), 404

        branch, semester, _section = _parse_class_id(class_id)
        lecture = _find_lecture(branch, semester, faculty_email, faculty_name)
        if not lecture:
            logger.error(f"Lecture info not found for class {class_id}")
            return jsonify({'error': 'Lecture info not found'}), 404

        subject = lecture.get('subject')
        section = lecture.get('section')
        classroom = lecture.get('classroom')
        date_str = datetime.now().strftime('%Y-%m-%d')
        
        # Save attendance to database
        collections = get_collections()
        saved_count = 0
        present_roll_nos = set()
        for student_id in recognized_students:
            # Parse student_id (format: "roll_no_name" or just "name")
            if '_' in student_id:
                roll_no, name = student_id.split('_', 1)
            else:
                roll_no = ''
                name = student_id
            present_roll_nos.add(roll_no)
            collections['attendance'].update_one(
                {
                    'date': date_str,
                    'subject': subject,
                    'faculty_email': faculty_email,
                    'branch': branch,
                    'semester': int(semester),
                    'section': section,
                    'student.roll_no': roll_no
                },
                {
                    '$set': {
                        'date': date_str,
                        'subject': subject,
                        'faculty_email': faculty_email,
                        'classroom': classroom,
                        'branch': branch,
                        'semester': int(semester),
                        'section': section,
                        'student': {
                            'roll_no': roll_no,
                            'name': name,
                            'status': 'Present'
                        }
                    }
                },
                upsert=True
            )
            saved_count += 1
        
        # Mark absent for students not recognized
        attendance_service = AttendanceService()
        all_students = attendance_service.get_students_for_class(branch, semester, section)
        for student in all_students:
            if student['roll_no'] not in present_roll_nos:
                collections['attendance'].update_one(
                    {
                        'date': date_str,
                        'subject': subject,
                        'faculty_email': faculty_email,
                        'branch': branch,
                        'semester': int(semester),
                        'section': section,
                        'student.roll_no': student['roll_no']
                    },
                    {
                        '$set': {
                            'date': date_str,
                            'subject': subject,
                            'faculty_email': faculty_email,
                            'classroom': classroom,
                            'branch': branch,
                            'semester': int(semester),
                            'section': section,
                            'student': {
                                'roll_no': student['roll_no'],
                                'name': student['name'],
                                'status': 'Absent'
                            }
                        }
                    },
                    upsert=True
                )
        
        logger.info(f"Session {session_id}: Saved {saved_count} attendance records to database")
        
        # Clean up session
        del live_attendance_sessions[session_id]
        logger.info(f"Session {session_id} cleaned up. Active sessions: {len(live_attendance_sessions)}")
        
        return jsonify({
            'success': True,
            'message': 'Attendance session stopped and saved',
            'recognized_students': recognized_students,
            'count': len(recognized_students)
        }) 
