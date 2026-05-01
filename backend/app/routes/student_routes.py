from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, current_app, session
from werkzeug.utils import secure_filename
import os
import pickle
import numpy as np
import logging
import base64
import io
from PIL import Image
from ..services.face_recognition import FaceRecognitionService
from ..db.mongo_client import get_collections
from ..extensions import cache
from ..utils.cloudinary_utils import (
    upload_pickle_to_cloudinary_from_memory, 
    get_pickle_from_cloudinary,
    list_encodings_from_cloudinary
)
from ..utils.api_contract import build_auth_response, wants_json_response
import pandas as pd
import bcrypt
import re
import datetime

bp = Blueprint('students', __name__)

@bp.route('/student/login', methods=['POST'])
def student_login():
    """Student login endpoint used by multilogin page"""
    logger = logging.getLogger(__name__)
    
    try:
        collections = get_collections()
    except Exception as e:
        logger.error(f"Database connection error during student login: {str(e)}")
        flash(f"Database connection error: {str(e)}. Please check MongoDB connection.", "error")
        return redirect('/multilogin')
    
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        roll_no = str(payload.get('roll_no', '')).strip()
        password = payload.get('password', '')
    else:
        roll_no = request.form.get('roll_no', '').strip()
        password = request.form.get('password', '')

    if not roll_no or not password:
        logger.warning(f"Student login attempt with missing credentials from IP: {request.remote_addr}")
        if wants_json_response():
            return jsonify({'success': False, 'errors': ['Please enter roll number and password.']}), 400
        flash("Please enter roll number and password.", "error")
        return redirect('/multilogin')

    logger.info(f"Student login attempt: {roll_no} from IP: {request.remote_addr}")

    try:
        user = collections['students'].find_one({"roll_no": roll_no})
        if not user or not isinstance(user.get('password'), (bytes, bytearray)) or not bcrypt.checkpw(password.encode('utf-8'), user['password']):
            logger.warning(f"Student login failed: Invalid credentials for roll_no {roll_no}")
            if wants_json_response():
                return jsonify({'success': False, 'errors': ['Invalid roll number or password.']}), 401
            flash("Invalid roll number or password.", "error")
            return redirect('/multilogin')

        session['student_roll_no'] = roll_no
        session['student_name'] = user.get('name', 'Student')
        session['role'] = 'student'

        logger.info(f"✓ Student successfully logged in: {roll_no} ({user.get('name')}) from IP: {request.remote_addr}")
        if wants_json_response():
            return jsonify(
                build_auth_response(
                    user={
                        'roll_no': roll_no,
                        'name': session.get('student_name', 'Student'),
                        'role': 'student',
                    },
                    role='student',
                    redirect_path='/student/dashboard',
                )
            )
        # Redirect student after login
        return redirect('/student/dashboard')
    except Exception as e:
        logger.error(f"Student login error for {roll_no}: {str(e)}")
        if wants_json_response():
            return jsonify({'success': False, 'errors': [f'Login error: {str(e)}']}), 500
        flash(f"Login error: {str(e)}", "error")
        return redirect('/multilogin')


def _require_student_session():
    roll_no = session.get('student_roll_no')
    if not roll_no:
        return None
    return roll_no


def _get_student_doc(roll_no):
    cols = get_collections()
    return cols['students'].find_one({"roll_no": roll_no})


@bp.route('/student/dashboard')
def student_dashboard():
    roll_no = _require_student_session()
    if not roll_no:
        return redirect('/multilogin')

    cols = get_collections()
    student = _get_student_doc(roll_no)
    if not student:
        flash('Student not found.', 'error')
        return redirect('/multilogin')

    student_name = student.get('name', 'Student')
    branch = student.get('branch', '')
    semester = str(student.get('semester', ''))
    section = student.get('section', 'A')

    # Today's classes from timetable.csv
    df = pd.read_csv('timetable.csv') if os.path.exists('timetable.csv') else pd.DataFrame()
    today_classes = []
    attendance_stats = {}
    recent_attendance = []
    monthly_trend = {}

    if not df.empty:
        today = pd.Timestamp.now().strftime('%A')
        class_df = df[(df['branch'] == branch) & (df['semester'].astype(str) == semester) & (df['section'] == section) & (df['day'] == today)]
        today_classes = class_df.to_dict(orient='records')

    # Subject-wise attendance stats for this student
    # Build list of subjects from timetable or attendance
    subjects = set([c.get('subject') for c in today_classes])
    for doc in cols['attendance'].find({"student.roll_no": roll_no}):
        if doc.get('subject'):
            subjects.add(doc['subject'])

    for subj in subjects:
        total = cols['attendance'].count_documents({"student.roll_no": roll_no, "subject": subj})
        present = cols['attendance'].count_documents({"student.roll_no": roll_no, "subject": subj, "student.status": "Present"})
        percentage = int(round((present / total) * 100)) if total > 0 else 0
        attendance_stats[subj] = {"total": total, "present": present, "percentage": percentage}

    # Recent attendance (latest 10)
    recent_cursor = cols['attendance'].find({"student.roll_no": roll_no}).sort("_id", -1).limit(10)
    for r in recent_cursor:
        recent_attendance.append({
            'subject': r.get('subject', ''),
            'date': r.get('date', ''),
            'status': r.get('student', {}).get('status', '')
        })

    # Get all unique subjects from timetable for this student
    timetable_subjects = set()
    if not df.empty:
        student_timetable = df[(df['branch'] == branch) & (df['semester'].astype(str) == semester) & (df['section'] == section)]
        timetable_subjects = student_timetable['subject'].drop_duplicates().tolist()

    # Weekly attendance by subject (past 7 days)
    from datetime import datetime, timedelta

    weekly_attendance = {}
    week_ago = datetime.now() - timedelta(days=7)

    for subject in timetable_subjects:
        # Get attendance records for this subject in the past week
        weekly_docs = cols['attendance'].find({
            "student.roll_no": roll_no,
            "subject": subject,
            "date": {"$gte": week_ago.strftime("%Y-%m-%d")}
        })

        total_weekly = 0
        present_weekly = 0

        for doc in weekly_docs:
            total_weekly += 1
            if doc.get('student', {}).get('status') == 'Present':
                present_weekly += 1

        if total_weekly > 0:
            weekly_attendance[subject] = {
                "present": present_weekly,
                "absent": total_weekly - present_weekly,
                "total": total_weekly
            }

    overall_total = sum(v['total'] for v in attendance_stats.values())
    overall_present = sum(v['present'] for v in attendance_stats.values())
    overall_absent = overall_total - overall_present
    overall_percentage = int(round((overall_present / overall_total) * 100)) if overall_total > 0 else 0

    return render_template(
        'student/student_dashboard.html',
        student_name=student_name,
        student_roll_no=roll_no,
        student_branch=branch,
        student_semester=semester,
        student_section=section,
        today_classes=today_classes,
        attendance_stats=attendance_stats,
        recent_attendance=recent_attendance,
        monthly_trend=monthly_trend,
        overall_percentage=overall_percentage,
        overall_stats={
            'total_present': overall_present,
            'total_absent': overall_absent
        },
        timetable_subjects=timetable_subjects,
        weekly_attendance=weekly_attendance
    )


@bp.route('/api/student/dashboard', methods=['GET'])
def student_dashboard_api():
    logger = logging.getLogger(__name__)
    roll_no = _require_student_session()
    logger.info(f"DEBUG: student_dashboard_api called for roll_no: {roll_no}")
    
    if not roll_no:
        logger.warning("DEBUG: No student roll_no in session")
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    cols = get_collections()
    student = _get_student_doc(roll_no)
    if not student:
        logger.warning(f"DEBUG: Student not found for roll_no: {roll_no}")
        return jsonify({'success': False, 'error': 'Student not found'}), 404

    logger.info(f"DEBUG: Found student: {student.get('name')} for roll_no: {roll_no}")

    cache_key = f"student_dashboard:v3:{roll_no}:{student.get('branch','')}:{student.get('semester','')}:{student.get('section','')}"
    cached_payload = cache.get(cache_key)
    if cached_payload:
        return jsonify(cached_payload)

    branch = str(student.get('branch', '') or '').strip()
    semester = str(student.get('semester', '') or '').strip()
    section = str(student.get('section', 'A') or 'A').strip()

    # Prefer Mongo timetable (source of truth for admin/faculty flows), fallback to CSV.
    student_timetable = pd.DataFrame()
    semester_number = None
    if semester.isdigit():
        try:
            semester_number = int(semester)
        except Exception:
            semester_number = None

    timetable_query = {
        'branch': {'$regex': f"^{re.escape(branch)}$", '$options': 'i'},
        'section': {'$regex': f"^{re.escape(section)}$", '$options': 'i'},
    }
    if semester_number is not None:
        timetable_query['semester'] = {'$in': [semester, semester_number]}
    else:
        timetable_query['semester'] = semester

    mongo_timetable = list(
        cols['timetable'].find(
            timetable_query,
            {
                '_id': 0,
                'day': 1,
                'start_time': 1,
                'end_time': 1,
                'subject': 1,
                'faculty_name': 1,
                'faculty_email': 1,
                'branch': 1,
                'semester': 1,
                'section': 1,
            },
        )
    )

    if mongo_timetable:
        student_timetable = pd.DataFrame(mongo_timetable)

    # Build today's classes.
    today_classes = []
    if not student_timetable.empty:
        today = pd.Timestamp.now().strftime('%A')
        day_df = student_timetable[
            student_timetable['day'].astype(str).str.strip().str.lower() == today.lower()
        ].copy()
        if 'start_time' in day_df.columns:
            day_df = day_df.sort_values(by='start_time')
        for row in day_df.to_dict(orient='records'):
            today_classes.append({
                'time': f"{str(row.get('start_time', '-') or '-').strip()} - {str(row.get('end_time', '-') or '-').strip()}",
                'subject': str(row.get('subject', '') or '').strip(),
                'faculty': str(row.get('faculty_name', row.get('faculty_email', '')) or '').strip(),
            })

    # Build recent attendance.
    recent_attendance = []
    recent_cursor = cols['attendance'].find({"student.roll_no": roll_no}).sort("_id", -1).limit(10)
    for record in recent_cursor:
        recent_attendance.append({
            'subject': record.get('subject', ''),
            'date': record.get('date', ''),
            'status': record.get('student', {}).get('status', ''),
        })

    # Build attendance summary.
    total = cols['attendance'].count_documents({"student.roll_no": roll_no})
    present = cols['attendance'].count_documents({"student.roll_no": roll_no, "student.status": "Present"})
    absent = max(total - present, 0)
    logger.info(f"DEBUG: Attendance stats for {roll_no}: total={total}, present={present}, absent={absent}")

    # Build weekly timetable matrix (real data) for frontend table.
    default_headers = ['09:00', '10:00', '11:00', '12:00', '02:00']
    weekly_headers = default_headers
    weekly_rows = []
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']

    if not student_timetable.empty:
        if 'start_time' in student_timetable.columns:
            slots = [str(value).strip() for value in student_timetable['start_time'].dropna().astype(str).unique().tolist() if str(value).strip()]
            slots = sorted(slots)
            if slots:
                weekly_headers = slots[:5]

        for day in days:
            day_df = student_timetable[
                student_timetable['day'].astype(str).str.strip().str.lower() == day.lower()
            ].copy()
            if 'start_time' in day_df.columns:
                day_df = day_df.sort_values(by='start_time')

            subject_by_slot = {}
            for _, row in day_df.iterrows():
                key = str(row.get('start_time', '') or '').strip()
                if key and key not in subject_by_slot:
                    subject_by_slot[key] = str(row.get('subject', '') or '').strip()

            row_cells = [day]
            for slot in weekly_headers:
                row_cells.append(subject_by_slot.get(slot, '-'))
            weekly_rows.append(row_cells)

    if not weekly_rows:
        weekly_rows = [
            ['Monday', '-', '-', '-', '-', '-'],
            ['Tuesday', '-', '-', '-', '-', '-'],
            ['Wednesday', '-', '-', '-', '-', '-'],
            ['Thursday', '-', '-', '-', '-', '-'],
            ['Friday', '-', '-', '-', '-', '-'],
        ]

    payload = {
        'success': True,
        'todayClasses': today_classes,
        'attendanceSummary': {
            'present': int(present),
            'absent': int(absent),
            'total': int(total),
        },
        'recentAttendance': recent_attendance,
        'weeklyHeaders': weekly_headers,
        'weeklyTimetable': weekly_rows,
    }

    cache.set(cache_key, payload, timeout=int(os.environ.get('DASHBOARD_CACHE_TTL', '60')))
    return jsonify(payload)


@bp.route('/api/student/attendance', methods=['GET'])
def student_attendance_api():
    roll_no = _require_student_session()
    if not roll_no:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    cols = get_collections()
    detailed = []

    # Build subject list from attendance docs
    subjects = cols['attendance'].distinct('subject', {"student.roll_no": roll_no})
    for subj in subjects:
        if not subj:
            continue
        total = cols['attendance'].count_documents({"student.roll_no": roll_no, "subject": subj})
        present = cols['attendance'].count_documents({"student.roll_no": roll_no, "subject": subj, "student.status": "Present"})
        percentage = int(round((present / total) * 100)) if total > 0 else 0

        # recent records for subject
        records = []
        for r in cols['attendance'].find({"student.roll_no": roll_no, "subject": subj}).sort("_id", -1).limit(20):
            records.append({
                'date': r.get('date', ''),
                'status': r.get('student', {}).get('status', '')
            })

        # Calculate trend based on attendance percentage buckets
        if percentage <= 60:
            trend = "Critical"
        elif percentage <= 75:
            trend = "Watch"
        elif percentage <= 90:
            trend = "Good"
        else:
            trend = "Excellent"

        detailed.append({
            'subject': subj,
            'attendance': f"{percentage}%",
            'trend': trend,
            'present_classes': present,
            'total_classes': total,
            'percentage': percentage,
            'records': records
        })

    # Overall stats
    total_all = sum(d['total_classes'] for d in detailed)
    present_all = sum(d['present_classes'] for d in detailed)
    overall_percentage = int(round((present_all / total_all) * 100)) if total_all > 0 else 0

    best_subject_doc = max(detailed, key=lambda x: x['percentage'], default=None)
    needs_focus_doc = min(detailed, key=lambda x: x['percentage'], default=None)

    # Global recent list (all subjects mixed, sorted by date)
    all_recent = []
    global_recent_cursor = cols['attendance'].find({"student.roll_no": roll_no}).sort("_id", -1).limit(10)
    for r in global_recent_cursor:
        all_recent.append({
            'date': r.get('date', ''),
            'subject': r.get('subject', ''),
            'status': r.get('student', {}).get('status', '')
        })

    return jsonify({
        'success': True,
        'detailedAttendance': detailed,
        'overallStats': {
            'semester': f"{overall_percentage}%",
            'bestSubject': best_subject_doc['attendance'] if best_subject_doc else "0%",
            'needsFocus': needs_focus_doc['attendance'] if needs_focus_doc else "0%"
        },
        'recentAttendance': all_recent
    })
def student_timetable():
    roll_no = _require_student_session()
    if not roll_no:
        return redirect('/multilogin')

    student = _get_student_doc(roll_no)
    if not student:
        flash('Student not found.', 'error')
        return redirect('/multilogin')

    student_name = student.get('name', 'Student')
    branch = student.get('branch', '')
    semester = str(student.get('semester', ''))
    section = student.get('section', 'A')

    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    timetable = {d: [] for d in days}

    df = pd.read_csv('timetable.csv') if os.path.exists('timetable.csv') else pd.DataFrame()
    if not df.empty:
        class_df = df[(df['branch'] == branch) & (df['semester'].astype(str) == semester) & (df['section'] == section)]
        # sort by start_time within day
        for day in days:
            day_df = class_df[class_df['day'] == day]
            try:
                day_df = day_df.sort_values(by='start_time')
            except:
                pass
            timetable[day] = day_df.to_dict(orient='records')

    return render_template('student/student_timetable.html', student_name=student_name, days=days, timetable=timetable)


@bp.route('/student/attendance')
def student_attendance():
    roll_no = _require_student_session()
    if not roll_no:
        return redirect('/multilogin')

    student = _get_student_doc(roll_no)
    if not student:
        flash('Student not found.', 'error')
        return redirect('/multilogin')

    student_name = student.get('name', 'Student')

    cols = get_collections()
    detailed = []

    # Build subject list from attendance docs
    subjects = cols['attendance'].distinct('subject', {"student.roll_no": roll_no})
    for subj in subjects:
        if not subj:
            continue
        total = cols['attendance'].count_documents({"student.roll_no": roll_no, "subject": subj})
        present = cols['attendance'].count_documents({"student.roll_no": roll_no, "subject": subj, "student.status": "Present"})
        percentage = int(round((present / total) * 100)) if total > 0 else 0
        # recent records for subject
        records = []
        for r in cols['attendance'].find({"student.roll_no": roll_no, "subject": subj}).sort("_id", -1).limit(20):
            records.append({
                'date': r.get('date', ''),
                'status': r.get('student', {}).get('status', '')
            })
        detailed.append({
            'subject': subj,
            'faculty': r.get('faculty_email', '' ) if records else '',
            'present_classes': present,
            'total_classes': total,
            'percentage': percentage,
            'attendance_records': records
        })

    return render_template('student/student_attendance.html', student_name=student_name, detailed_attendance=detailed)


@bp.route('/student/profile')
def student_profile():
    roll_no = _require_student_session()
    if not roll_no:
        return redirect('/multilogin')

    student = _get_student_doc(roll_no)
    if not student:
        flash('Student not found.', 'error')
        return redirect('/multilogin')

    return render_template('student/student_profile.html', student=student)


@bp.route('/student/change-password', methods=['GET', 'POST'])
def student_change_password():
    roll_no = _require_student_session()
    if not roll_no:
        return redirect('/multilogin')

    cols = get_collections()
    student = _get_student_doc(roll_no)
    if not student:
        flash('Student not found.', 'error')
        return redirect('/multilogin')

    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if new_password != confirm_password:
            flash('New password and confirm password do not match.', 'error')
            return render_template('student/student_change_password.html')

        stored_hash = student.get('password')
        if not isinstance(stored_hash, (bytes, bytearray)) or not bcrypt.checkpw(current_password.encode('utf-8'), stored_hash):
            flash('Current password is incorrect.', 'error')
            return render_template('student/student_change_password.html')

        new_hashed = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
        cols['students'].update_one({'_id': student['_id']}, {'$set': {'password': new_hashed}})
        # Logout after password change and send to multilogin
        session.pop('student_roll_no', None)
        session.pop('student_name', None)
        if 'role' in session and session['role'] == 'student':
            session.pop('role', None)
        flash('Password changed successfully. Please log in again.', 'success')
        return redirect('/multilogin')

    return render_template('student/student_change_password.html')
@bp.route('/student/logout', methods=['POST', 'GET'])
def student_logout():
    logger = logging.getLogger(__name__)
    roll_no = session.get('student_roll_no', 'Unknown')
    logger.info(f"Student logged out: {roll_no}")
    session.pop('student_roll_no', None)
    session.pop('student_name', None)
    if 'role' in session and session['role'] == 'student':
        session.pop('role', None)
    if wants_json_response():
        return jsonify({'success': True, 'message': 'Logged out'})
    return redirect('/multilogin')

@bp.route('/students')
def students():
    """Display all students for the logged-in faculty"""
    from flask import session
    
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return redirect('/multilogin')

    collections = get_collections()
    faculty_doc = collections['faculty'].find_one({'email': faculty_email.strip().lower()})
    if not faculty_doc:
        flash("Faculty not found.", "error")
        return redirect('/multilogin')
    faculty_name = str(faculty_doc.get('name', 'Faculty')).strip().lower()

    timetable_docs = list(
        collections['timetable'].find(
            {
                '$or': [
                    {'faculty_email': faculty_email.strip().lower()},
                    {'faculty_name': faculty_name},
                ]
            },
            {'_id': 0, 'branch': 1, 'semester': 1, 'section': 1},
        )
    )
    class_tuples = set()
    for doc in timetable_docs:
        branch = doc.get('branch')
        semester = doc.get('semester')
        section = doc.get('section')
        if not (branch and semester is not None and section):
            continue
        try:
            semester = int(semester)
        except Exception:
            continue
        class_tuples.add((branch, semester, section))

    # Fetch all students in these classes
    students = []
    for branch, semester, section in sorted(class_tuples):
        students_cursor = collections['students'].find({
            "branch": branch,
            "semester": semester,
            "section": section
        })
        for s in students_cursor:
            students.append({
                "roll_no": str(s.get("roll_no")),
                "name": str(s.get("name")),
                "branch": str(branch),
                "semester": int(semester),
                "section": str(section)
            })
    return render_template('faculty/students.html', students=students, faculty=faculty_name)

@bp.route('/register_student_face', methods=['GET', 'POST'])
def register_student_face():
    """Register a student with face photos"""
    from flask import session
    
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return redirect('/multilogin')

    collections = get_collections()
    faculty_doc = collections['faculty'].find_one({'email': faculty_email.strip().lower()})
    if not faculty_doc:
        flash("Faculty not found.", "error")
        return redirect('/multilogin')
    faculty_name = str(faculty_doc.get('name', 'Faculty')).strip().lower()

    branches = ['CE', 'CSE', 'IT', 'ECE']
    semesters = [1, 2, 3, 4, 5, 6, 7, 8]
    message = None
    error = None
    selected_branch = None
    selected_semester = None
    students = []

    if request.method == 'POST':
        branch = request.form.get('branch')
        semester = request.form.get('semester')
        selected_branch = branch
        selected_semester = semester
        # Filter students for dropdown
        if branch and semester:
            students = list(collections['students'].find({"branch": branch, "semester": int(semester)}, {"_id": 0}))
        else:
            students = list(collections['students'].find({}, {"_id": 0}))
        student_id = request.form.get('student_id')
        allow_replace = str(request.form.get('allow_replace') or '').strip().lower() in {'1', 'true', 'yes', 'replace'}
        new_name = str(request.form.get('new_name') or '').strip()
        new_roll_no = str(request.form.get('new_roll_no') or '').strip()
        section = None
        if student_id:
            student = collections['students'].find_one({"roll_no": student_id})
            if not student:
                error = "Selected student not found."
            else:
                name = student['name']
                roll_no = student['roll_no']
                semester = student['semester']
                branch = student['branch']
                section = student.get('section', 'A')
        elif new_name and new_roll_no:
            name = new_name
            roll_no = new_roll_no
            section = 'A'
            if not collections['students'].find_one({"roll_no": roll_no}):
                default_hash = bcrypt.hashpw('123456'.encode('utf-8'), bcrypt.gensalt())
                collections['students'].insert_one({
                    "roll_no": roll_no,
                    "name": name,
                    "semester": int(semester),
                    "branch": branch,
                    "section": section,
                    "password": default_hash
                })
        else:
            error = "Please select or enter student details."
        photos = [request.files.get(f'photo{i}') for i in range(1, 4)]
        if not error and (not all(photos) or not all(photo and photo.filename for photo in photos)):
            error = "Please upload 3 face photos."
        if not error:
            face_service = FaceRecognitionService()
            encodings = []
            for idx, photo in enumerate(photos):
                filename = secure_filename(f"{roll_no}_{name}_face{idx+1}.jpg")
                save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                photo.save(save_path)
                import cv2
                img = cv2.imread(save_path)
                if img is None:
                    error = f"Failed to read uploaded image {filename}."
                    break
                rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                
                # Use proper embedding extraction based on mode
                if face_service.mode == 'remote':
                    # Remote mode: get embedding from remote service
                    embedding = face_service.get_face_embedding(rgb)
                    if embedding is None:
                        error = f"No face found in {filename}."
                        break
                    encodings.append(embedding)
                else:
                    # Local/Hybrid mode: use local detection
                    faces = face_service.get_faces(rgb)
                    if not faces:
                        error = f"No face found in {filename}."
                        break
                    encodings.append(faces[0].normed_embedding)
            
            if not error and len(encodings) == 3:
                avg_encoding = np.mean(encodings, axis=0)
                
                # Check if this face is already registered in any class via Cloudinary
                all_pickle_files = list_encodings_from_cloudinary()
                existing_registration = None
                normalized_roll_no = str(roll_no or '').strip().lower()
                target_class_ids = {
                    f"{branch}_{semester}",
                    f"{branch}_{semester}_{section or 'A'}",
                }
                
                for pickle_file in all_pickle_files:
                    class_id = pickle_file.replace('.pickle', '')
                    try:
                        data = get_pickle_from_cloudinary(class_id)
                        if not data: continue
                        
                        existing_encodings = data.get('encodings', [])
                        existing_metadata = data.get('metadata', [])
                        
                        if existing_encodings:
                            # Compare with existing encodings
                            for i, existing_encoding in enumerate(existing_encodings):
                                distance = np.linalg.norm(avg_encoding - existing_encoding)
                                if distance < 0.85:  # Same tolerance as face recognition
                                    existing_student = existing_metadata[i]

                                    existing_roll_no = str(existing_student.get('roll_no', '')).strip().lower()

                                    # Always allow same student in same target class (acts like update instead of duplicate).
                                    if existing_roll_no == normalized_roll_no and class_id in target_class_ids:
                                        continue

                                    # In replace mode, ignore matches that already belong to this same student.
                                    if allow_replace and existing_roll_no == normalized_roll_no:
                                        continue

                                    existing_registration = {
                                        'student_name': existing_student.get('name', 'Unknown'),
                                        'student_roll': existing_student.get('roll_no', 'Unknown'),
                                        'class': class_id,
                                        'distance': distance
                                    }
                                    break
                                    
                    except Exception as e:
                        continue
                    
                    if existing_registration:
                        break
                
                # If face is already registered in another class
                if existing_registration:
                    error = f"Face already registered! This face belongs to {existing_registration['student_name']} ({existing_registration['student_roll']}) in class {existing_registration['class']}"
                else:
                    # Proceed with registration in the selected class
                    # Load current data from cloud
                    data = get_pickle_from_cloudinary(f"{branch}_{semester}")
                    if not data:
                        data = {"encodings": [], "metadata": []}
                    
                    new_metadata = {"roll_no": roll_no, "name": name, "semester": int(semester), "branch": branch, "section": section}
                    filtered = [(e, m) for e, m in zip(data["encodings"], data["metadata"]) if m.get("roll_no") != roll_no]
                    data["encodings"] = [e for e, m in filtered]
                    data["metadata"] = [m for e, m in filtered]
                    data["encodings"].append(avg_encoding)
                    data["metadata"].append(new_metadata)
                    
                    # Sync to Cloudinary from memory
                    upload_pickle_to_cloudinary_from_memory(data, f"{branch}_{semester}")
                    
                    # Update student database flag
                    collections['students'].update_one({'roll_no': roll_no}, {'$set': {'face_registered': True}})
                    
                    message = f"Student {name} ({roll_no}) registered successfully!"
        # Refresh students list for the selected branch/semester
        if selected_branch and selected_semester:
            students = list(collections['students'].find({"branch": selected_branch, "semester": int(selected_semester)}, {"_id": 0}))
        else:
            students = list(collections['students'].find({}, {"_id": 0}))
        # AJAX/JSON response
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            if error:
                return {"success": False, "message": error}
            else:
                return {"success": True, "message": message}
    else:
        # GET: show all students by default
        students = list(collections['students'].find({}, {"_id": 0}))
    return render_template('student/register_student_face.html', branches=branches, semesters=semesters, students=students, message=message, error=error, selected_branch=selected_branch, selected_semester=selected_semester, faculty=faculty_name)

@bp.route('/check_existing_registration')
def check_existing_registration():
    """Check if a student already has face registrations in any class"""
    from flask import session
    
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return jsonify({'error': 'Not logged in'}), 401
    
    student_id = request.args.get('student_id')
    if not student_id:
        return jsonify({'error': 'Missing student_id'}), 400
    
    # Get student info
    collections = get_collections()
    student = collections['students'].find_one({"roll_no": student_id})
    if not student:
        return jsonify({'error': 'Student not found'}), 404
    
    # Check all pickle files for this student's face
    split_dir = current_app.config['SPLIT_DIR']
    existing_registrations = []
    
    # Check all cloud files for this student's face
    all_pickle_files = list_encodings_from_cloudinary()
    
    for pickle_file in all_pickle_files:
        class_id = pickle_file.replace('.pickle', '')
        try:
            data = get_pickle_from_cloudinary(class_id)
            if not data: continue
            
            existing_metadata = data.get('metadata', [])
            
            # Check if this student is in this class
            for metadata in existing_metadata:
                if metadata.get('roll_no') == student_id:
                    branch, semester = class_id.split('_')
                    existing_registrations.append({
                        'class': class_id,
                        'branch': branch,
                        'semester': semester,
                        'section': metadata.get('section', 'A')
                    })
                    break
                    
        except Exception as e:
            continue
    
    return jsonify({
        'student_name': student.get('name', 'Unknown'),
        'student_roll': student.get('roll_no', 'Unknown'),
        'existing_registrations': existing_registrations
    })

@bp.route('/face_registrations_summary')
def face_registrations_summary():
    """Show a summary of all face registrations in the system"""
    from flask import session
    
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return redirect('/multilogin')
    
    collections = get_collections()
    faculty_doc = collections['faculty'].find_one({'email': faculty_email.strip().lower()})
    if not faculty_doc:
        flash("Faculty not found.", "error")
        return redirect('/multilogin')
    faculty_name = str(faculty_doc.get('name', 'Faculty')).strip().lower()
    
    # Get all face registrations from Cloudinary
    all_registrations = []
    all_pickle_files = list_encodings_from_cloudinary()
    
    for pickle_file in all_pickle_files:
        class_id = pickle_file.replace('.pickle', '')
        try:
            data = get_pickle_from_cloudinary(class_id)
            if not data: continue
            
            encodings = data.get('encodings', [])
            metadata = data.get('metadata', [])
            
            branch, semester = class_id.split('_')
            
            for i, student_meta in enumerate(metadata):
                all_registrations.append({
                    'student_name': student_meta.get('name', 'Unknown'),
                    'student_roll': student_meta.get('roll_no', 'Unknown'),
                    'class': class_id,
                    'branch': branch,
                    'semester': semester,
                    'section': student_meta.get('section', 'A'),
                    'encoding_index': i
                })
                        
        except Exception as e:
            continue
    # Sort by class and then by student name
    all_registrations.sort(key=lambda x: (x['class'], x['student_name']))
    
    return render_template('faculty/face_registrations_summary.html', 
                         registrations=all_registrations, 
                         faculty=faculty_name)
    
@bp.route('/delete_student_face', methods=['POST'])
def delete_student_face():
    """Delete all face registration data for a specific student"""
    from flask import session

    print("Delete student face route called")
    faculty_email = session.get('faculty_email')
    print(f"Faculty email from session: {faculty_email}")

    if not faculty_email:
        print("No faculty email in session")
        return jsonify({'success': False, 'message': 'Not logged in'}), 401

    try:
        data = request.get_json()
        print(f"Request data: {data}")
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400

        student_roll = data.get('student_roll')
        # class_name is now optional; we will remove from ALL classes regardless
        class_name = data.get('class_name')

        print(f"Student roll: {student_roll}, Class name: {class_name}")

        if not student_roll:
            return jsonify({'success': False, 'message': 'Missing student_roll'}), 400

        # Get collections and current app config
        collections = get_collections()
        split_dir = current_app.config['SPLIT_DIR']
        upload_folder = current_app.config['UPLOAD_FOLDER']

        print(f"Split dir: {split_dir}, Upload folder: {upload_folder}")

        # Remove student's face data from ALL cloud AND local class pickle files
        classes_affected = []
        total_removed = 0
        
        # 1. Remove from Cloudinary
        all_pickle_files = list_encodings_from_cloudinary()
        
        for pickle_file in all_pickle_files:
            class_id = pickle_file.replace('.pickle', '')
            try:
                data = get_pickle_from_cloudinary(class_id)
                if not data: continue
                
                encodings = data.get('encodings', [])
                metadata = data.get('metadata', [])
                
                filtered_encodings = []
                filtered_metadata = []
                removed_here = 0
                
                for i, meta in enumerate(metadata):
                    if meta.get('roll_no') != student_roll:
                        filtered_encodings.append(encodings[i])
                        filtered_metadata.append(meta)
                    else:
                        removed_here += 1
                
                if removed_here > 0:
                    data['encodings'] = filtered_encodings
                    data['metadata'] = filtered_metadata
                    
                    # Sync deletion to Cloudinary from memory
                    upload_pickle_to_cloudinary_from_memory(data, class_id)
                    
                    classes_affected.append(class_id)
                    total_removed += removed_here
            except Exception as e:
                print(f"Warning: Error processing {class_id} on cloud: {e}")
        
        # 2. Remove from local split_encodings directory
        if os.path.exists(split_dir):
            local_files = [f for f in os.listdir(split_dir) if f.endswith('.pickle')]
            for pickle_file in local_files:
                class_id = pickle_file.replace('.pickle', '')
                file_path = os.path.join(split_dir, pickle_file)
                try:
                    with open(file_path, 'rb') as f:
                        data = pickle.load(f)
                        
                    if not data: continue
                    
                    encodings = data.get('encodings', [])
                    metadata = data.get('metadata', [])
                    
                    filtered_encodings = []
                    filtered_metadata = []
                    removed_here = 0
                    
                    for i, meta in enumerate(metadata):
                        if meta.get('roll_no') != student_roll:
                            filtered_encodings.append(encodings[i])
                            filtered_metadata.append(meta)
                        else:
                            removed_here += 1
                    
                    if removed_here > 0:
                        data['encodings'] = filtered_encodings
                        data['metadata'] = filtered_metadata
                        
                        # Save back to local file
                        with open(file_path, 'wb') as f:
                            pickle.dump(data, f)
                        
                        if class_id not in classes_affected:
                            classes_affected.append(class_id)
                        total_removed += removed_here
                except Exception as e:
                    print(f"Warning: Error processing {class_id} locally: {e}")

        # Remove uploaded face images for this roll number
        removed_files = []
        try:
            import glob
            for i in range(1, 4):
                pattern = os.path.join(upload_folder, f"{student_roll}_*_face{i}.jpg")
                matching_files = glob.glob(pattern)
                for file_path in matching_files:
                    try:
                        os.remove(file_path)
                        removed_files.append(os.path.basename(file_path))
                    except Exception as e:
                        print(f"Warning: Could not remove file {file_path}: {e}")
        except Exception as e:
            print(f"Warning during photo cleanup: {e}")

        # Delete student and related attendance from MongoDB
        try:
            # Remove the student document
            student_result = collections['students'].delete_one({'roll_no': student_roll})
            # Remove attendance records referencing this student
            attendance_result = collections['attendance'].delete_many({'student.roll_no': student_roll})
        except Exception as e:
            print(f"Warning: Error deleting from database: {e}")
            student_result = type('obj', (), {'deleted_count': 0})()
            attendance_result = type('obj', (), {'deleted_count': 0})()

        # Build response
        return jsonify({
            'success': True,
            'message': (
                f"Deleted student {student_roll} everywhere. "
                f"Removed {total_removed} face entries across classes {classes_affected}. "
                f"Deleted {len(removed_files)} uploaded photo(s). "
                f"DB deletions - students: {getattr(student_result, 'deleted_count', 0)}, "
                f"attendance: {getattr(attendance_result, 'deleted_count', 0)}."
            ),
            'classes_affected': classes_affected,
            'removed_photos': removed_files,
            'removed_face_entries': total_removed,
            'db': {
                'students_deleted': getattr(student_result, 'deleted_count', 0),
                'attendance_deleted': getattr(attendance_result, 'deleted_count', 0)
            }
        })

    except Exception as e:
        print(f"General exception: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        }), 500

@bp.route('/edit_student_face', methods=['POST'])
def edit_student_face():
    """Edit student face registration data"""
    from flask import session

    print("Edit student face route called")
    faculty_email = session.get('faculty_email')
    print(f"Faculty email from session: {faculty_email}")

    if not faculty_email:
        print("No faculty email in session")
        return jsonify({'success': False, 'message': 'Not logged in'}), 401

    try:
        data = request.get_json()
        print(f"Edit request data: {data}")
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400

        old_roll_no = data.get('old_roll_no')
        old_class_name = data.get('old_class_name')
        new_name = data.get('new_name')
        new_roll_no = data.get('new_roll_no')
        new_branch = data.get('new_branch')
        new_semester = data.get('new_semester')
        new_section = data.get('new_section')

        print(f"Edit request - Old: {old_roll_no} in {old_class_name}, New: {new_name} ({new_roll_no}) in {new_branch}_{new_semester}")

        if not all([old_roll_no, old_class_name, new_name, new_roll_no, new_branch, new_semester, new_section]):
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400

        # Get collections and current app config
        collections = get_collections()
        split_dir = current_app.config['SPLIT_DIR']

        # Check if new roll number already exists in students collection
        existing_student = collections['students'].find_one({"roll_no": new_roll_no})
        if existing_student and existing_student['roll_no'] != old_roll_no:
            return jsonify({
                'success': False,
                'message': f'Student with roll number {new_roll_no} already exists'
            }), 400

        # Load and update the pickle data from cloud
        data = get_pickle_from_cloudinary(old_class_name)
        if not data:
            return jsonify({
                'success': False,
                'message': f'No face registration data found for class {old_class_name}'
            }), 404

        # Find and update the student's data
        encodings = data.get('encodings', [])
        metadata = data.get('metadata', [])

        # Find the student to update
        student_found = False
        target_idx = -1
        for i, meta in enumerate(metadata):
            if meta.get('roll_no') == old_roll_no:
                # Update metadata
                metadata[i] = {
                    'roll_no': new_roll_no,
                    'name': new_name,
                    'semester': int(new_semester),
                    'branch': new_branch,
                    'section': new_section
                }
                student_found = True
                target_idx = i
                print(f"Updated student at index {i}")
                break

        if not student_found:
            return jsonify({
                'success': False,
                'message': f'Student {old_roll_no} not found in class {old_class_name}'
            }), 404

        # Update student record in MongoDB
        update_result = collections['students'].update_one(
            {"roll_no": old_roll_no},
            {
                "$set": {
                    "roll_no": new_roll_no,
                    "name": new_name,
                    "branch": new_branch,
                    "semester": int(new_semester),
                    "section": new_section
                }
            }
        )

        if update_result.modified_count >= 0: # 0 means no changes needed or same roll_no update
            print(f"Updated student record in database")

            new_class_name = f"{new_branch}_{new_semester}"
            if new_class_name != old_class_name:
                print(f"Class changed from {old_class_name} to {new_class_name}")
                
                # Extract the encoding to move
                encoding_to_move = encodings[target_idx]
                metadata_to_move = metadata[target_idx]
                
                # Remove from old class data
                new_old_encodings = [e for i, e in enumerate(encodings) if i != target_idx]
                new_old_metadata = [m for i, m in enumerate(metadata) if i != target_idx]
                
                # Save old class back to cloud
                upload_pickle_to_cloudinary_from_memory(
                    {'encodings': new_old_encodings, 'metadata': new_old_metadata}, 
                    old_class_name
                )
                
                # Load new class data
                dest_data = get_pickle_from_cloudinary(new_class_name)
                if not dest_data:
                    dest_data = {'encodings': [], 'metadata': []}
                
                # Add to new class
                dest_data['encodings'].append(encoding_to_move)
                dest_data['metadata'].append(metadata_to_move)
                
                # Save new class back to cloud
                upload_pickle_to_cloudinary_from_memory(dest_data, new_class_name)
            else:
                # Case: same class, just updated metadata
                upload_pickle_to_cloudinary_from_memory(data, old_class_name)

            return jsonify({
                'success': True,
                'message': f'Successfully updated student information for {new_name} ({new_roll_no})'
            })
        else:
            return jsonify({
                'success': False,
                'message': f'Failed to update student record in database'
            }), 500

    except Exception as e:
        print(f"General exception in edit: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        }), 500
