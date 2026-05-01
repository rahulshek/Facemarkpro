import bcrypt
import os
import pickle
from collections import defaultdict
from datetime import datetime, timedelta
from uuid import uuid4
from flask import Blueprint, jsonify, request, session, current_app, make_response
from bson import ObjectId

from ..db.mongo_client import get_collections
from ..extensions import cache
from ..utils.cloudinary_utils import (
    get_pickle_from_cloudinary,
    list_encodings_from_cloudinary,
    upload_pickle_to_cloudinary_from_memory,
)
from ..utils.api_contract import (
    build_auth_response,
    current_session_user,
    json_error,
    require_session_role,
)
from ..utils.report_utils import (
    build_attendance_report,
    export_csv_report,
    export_pdf_report,
    normalize_date_range,
)

bp = Blueprint('api_routes', __name__, url_prefix='/api')

TIMETABLE_DAY_ORDER = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def _collect_face_registrations():
    """Return all face registrations discovered in cloud and local pickle stores."""
    registrations = []
    seen = set()

    try:
        all_pickle_files = list_encodings_from_cloudinary()
    except Exception:
        all_pickle_files = []

    for pickle_file in all_pickle_files:
        class_id = str(pickle_file).replace('.pickle', '')
        try:
            data = get_pickle_from_cloudinary(class_id)
            if not data:
                continue
            metadata = data.get('metadata', []) or []
            parts = class_id.split('_')
            branch = parts[0] if len(parts) >= 1 else "Unknown"
            semester = parts[1] if len(parts) >= 2 else "Unknown"

            for student in metadata:
                roll_no = str(student.get('roll_no', '')).strip()
                name = str(student.get('name', '')).strip()
                if not roll_no:
                    continue
                key = f"{roll_no}_{class_id}"
                if key in seen:
                    continue
                seen.add(key)
                registrations.append({
                    'student_roll': roll_no,
                    'student_name': name,
                    'branch': str(student.get('branch') or branch),
                    'semester': str(student.get('semester') or semester),
                    'section': str(student.get('section', 'A') or 'A'),
                    'class_file': class_id,
                    'source': 'cloud',
                })
        except Exception:
            continue

    split_dir = current_app.config.get('SPLIT_DIR', 'split_encodings')
    if os.path.exists(split_dir):
        local_files = [f for f in os.listdir(split_dir) if f.endswith('.pickle')]
        for pickle_file in local_files:
            class_id = str(pickle_file).replace('.pickle', '')
            try:
                file_path = os.path.join(split_dir, pickle_file)
                with open(file_path, 'rb') as f:
                    data = pickle.load(f)

                metadata = (data or {}).get('metadata', []) or []
                parts = class_id.split('_')
                branch = parts[0] if len(parts) >= 1 else "Unknown"
                semester = parts[1] if len(parts) >= 2 else "Unknown"

                for student in metadata:
                    roll_no = str(student.get('roll_no', '')).strip()
                    name = str(student.get('name', '')).strip()
                    if not roll_no:
                        continue
                    key = f"{roll_no}_{class_id}"
                    if key in seen:
                        continue
                    seen.add(key)
                    registrations.append({
                        'student_roll': roll_no,
                        'student_name': name,
                        'branch': str(student.get('branch') or branch),
                        'semester': str(student.get('semester') or semester),
                        'section': str(student.get('section', 'A') or 'A'),
                        'class_file': class_id,
                        'source': 'local',
                    })
            except Exception:
                continue

    return registrations


def _normalize_day_label(value):
    raw = str(value or '').strip()
    if not raw:
        return ''

    lowered = raw.lower()
    aliases = {
        'mon': 'Monday',
        'monday': 'Monday',
        'tue': 'Tuesday',
        'tues': 'Tuesday',
        'tuesday': 'Tuesday',
        'wed': 'Wednesday',
        'wednesday': 'Wednesday',
        'thu': 'Thursday',
        'thur': 'Thursday',
        'thurs': 'Thursday',
        'thursday': 'Thursday',
        'fri': 'Friday',
        'friday': 'Friday',
        'sat': 'Saturday',
        'saturday': 'Saturday',
        'sun': 'Sunday',
        'sunday': 'Sunday',
    }
    return aliases.get(lowered, '')


def _parse_clock_time(value):
    return datetime.strptime(str(value or '').strip(), '%H:%M')


def _faculty_timetable_query(faculty_email, faculty_name_lower):
    filters = []
    if faculty_email:
        filters.append({'faculty_email': faculty_email})
    if faculty_name_lower:
        filters.append({'faculty_name': faculty_name_lower})
    if not filters:
        return {'faculty_email': '__missing__'}
    if len(filters) == 1:
        return filters[0]
    return {'$or': filters}


def _faculty_assignment_query(faculty_email, faculty_name_lower):
    filters = []
    if faculty_email:
        filters.append({'faculty_email': faculty_email})
    if faculty_name_lower:
        filters.append({'faculty_name': faculty_name_lower})
    if not filters:
        return {'faculty_email': '__missing__'}
    if len(filters) == 1:
        return filters[0]
    return {'$or': filters}


def _clear_faculty_dashboard_cache(faculty_email):
    for role in ('teacher', 'faculty', 'super_admin'):
        cache.delete(f'faculty_dashboard:{faculty_email}:{role}')


def _serialize_timetable_slot(doc):
    day = _normalize_day_label(doc.get('day'))
    start_time = str(doc.get('start_time', '')).strip()
    end_time = str(doc.get('end_time', '')).strip()
    subject = str(doc.get('subject', '')).strip()
    subject_code = str(doc.get('subject_code', '')).strip().upper()
    classroom = str(doc.get('classroom', '')).strip()
    branch = str(doc.get('branch', '')).strip()
    section = str(doc.get('section', '')).strip()

    semester_value = doc.get('semester', '')
    try:
        semester = int(semester_value)
    except Exception:
        semester = str(semester_value or '').strip()

    try:
        period_no = int(doc.get('period_no', 0) or 0)
    except Exception:
        period_no = 0

    return {
        'id': str(doc.get('_id', '')),
        'day': day,
        'start_time': start_time,
        'end_time': end_time,
        'subject': subject,
        'subject_code': subject_code,
        'classroom': classroom,
        'branch': branch,
        'semester': semester,
        'section': section,
        'period_no': period_no,
        'class_label': ' / '.join([part for part in [branch, str(semester), section] if str(part).strip()]),
    }


ACADEMIC_SETUP_CONFIG = {
    'branches': {'collection': 'academic_branches', 'label': 'Branch'},
    'classes': {'collection': 'academic_classes', 'label': 'Class'},
    'classrooms': {'collection': 'academic_classrooms', 'label': 'Classroom'},
    'subjects': {'collection': 'academic_subjects', 'label': 'Subject'},
    'assignments': {'collection': 'faculty_assignments', 'label': 'Faculty assignment'},
}


def _to_int_or_none(value):
    if value in (None, ''):
        return None
    try:
        return int(value)
    except Exception:
        return None


def _normalize_boolean(value, default=True):
    if isinstance(value, bool):
        return value
    text = str(value if value is not None else '').strip().lower()
    if text in {'true', '1', 'yes', 'active'}:
        return True
    if text in {'false', '0', 'no', 'inactive'}:
        return False
    return default


def _serialize_academic_branch(doc):
    return {
        'id': str(doc.get('_id', '')),
        'code': str(doc.get('code', '')).strip().upper(),
        'name': str(doc.get('name', '')).strip(),
        'active': bool(doc.get('active', True)),
    }


def _serialize_academic_class(doc):
    branch = str(doc.get('branch', '')).strip().upper()
    semester = _to_int_or_none(doc.get('semester'))
    section = str(doc.get('section', '')).strip().upper()
    return {
        'id': str(doc.get('_id', '')),
        'branch': branch,
        'semester': semester,
        'section': section,
        'label': str(doc.get('label', '')).strip() or f'{branch} / {semester} / {section}',
        'active': bool(doc.get('active', True)),
    }


def _serialize_academic_classroom(doc):
    return {
        'id': str(doc.get('_id', '')),
        'name': str(doc.get('name', '')).strip(),
        'type': str(doc.get('type', '')).strip() or 'Classroom',
        'capacity': _to_int_or_none(doc.get('capacity')),
        'active': bool(doc.get('active', True)),
    }


def _serialize_academic_subject(doc):
    return {
        'id': str(doc.get('_id', '')),
        'code': str(doc.get('code', '')).strip().upper(),
        'name': str(doc.get('name', '')).strip(),
        'branch': str(doc.get('branch', '')).strip().upper(),
        'semester': _to_int_or_none(doc.get('semester')),
        'type': str(doc.get('type', '')).strip() or 'theory',
        'active': bool(doc.get('active', True)),
    }


def _serialize_academic_assignment(doc):
    faculty_name = str(doc.get('faculty_name', '')).strip()
    faculty_email = str(doc.get('faculty_email', '')).strip().lower()
    branch = str(doc.get('branch', '')).strip().upper()
    semester = _to_int_or_none(doc.get('semester'))
    section = str(doc.get('section', '')).strip().upper()
    subject_code = str(doc.get('subject_code', '')).strip().upper()
    subject_name = str(doc.get('subject_name', '')).strip()
    classroom = str(doc.get('classroom', '')).strip()
    return {
        'id': str(doc.get('_id', '')),
        'faculty_email': faculty_email,
        'faculty_name': faculty_name,
        'branch': branch,
        'semester': semester,
        'section': section,
        'class_label': f'{branch} / {semester} / {section}',
        'subject_code': subject_code,
        'subject_name': subject_name,
        'subject_label': f'{subject_name} ({subject_code})' if subject_code and subject_name else (subject_name or subject_code),
        'classroom': classroom,
        'active': bool(doc.get('active', True)),
    }


def _collect_registered_rolls():
    regs = _collect_face_registrations()
    return {str(r.get('student_roll', '')).strip() for r in regs if str(r.get('student_roll', '')).strip()}


def _get_faculty_filter_options(collections, faculty_email, faculty_name_lower):
    faculty_email = str(faculty_email).strip().lower()
    
    # We strictly use faculty_assignments as the source of truth
    query = {"faculty_email": faculty_email}
    assignments = list(collections['faculty_assignments'].find(query))

    subject_set = set()
    combo_set = set()
    class_set = set()

    for doc in assignments:
        b, s, sec, subj = doc.get("branch"), doc.get("semester"), doc.get("section"), doc.get("subject_name")
        if b and s is not None and sec and subj:
            try:
                b_str, s_str, sec_str, subj_str = str(b).strip().upper(), str(s), str(sec).strip().upper(), str(subj).strip()
                subject_set.add(subj_str)
                combo_set.add((b_str, s_str, sec_str, subj_str))
                class_set.add((b_str, int(s), sec_str))
            except: pass

    subjects = sorted(list(subject_set))
    class_options = [{"branch": b, "semester": s, "section": sec} for (b, s, sec) in sorted(class_set, key=lambda x: (x[0], x[1], x[2]))]
    combinations = [{"branch": b, "semester": s, "section": sec, "subject": subj} for (b, s, sec, subj) in combo_set]

    return subjects, class_options, combinations


def _get_admin_filter_options(collections):
    # 1. Collect Subjects from multiple sources
    subject_set = set()
    for doc in collections['timetable'].find({}, {"subject": 1}):
        if doc.get("subject"): subject_set.add(str(doc["subject"]).strip())
    for doc in collections['academic_subjects'].find({}, {"name": 1}):
        if doc.get("name"): subject_set.add(str(doc["name"]).strip())
    for subj in collections['attendance'].distinct('subject'):
        if subj: subject_set.add(str(subj).strip())
    subjects = sorted([s for s in subject_set if s])

    # 2. Collect Class Options
    class_set = set()
    for doc in collections['timetable'].find({}, {"branch": 1, "semester": 1, "section": 1}):
        b, s, sec = doc.get("branch"), doc.get("semester"), doc.get("section")
        if b and s is not None and sec:
            try: class_set.add((str(b).strip().upper(), int(s), str(sec).strip().upper()))
            except: pass
    for doc in collections['academic_classes'].find({}, {"branch": 1, "semester": 1, "section": 1}):
        b, s, sec = doc.get("branch"), doc.get("semester"), doc.get("section")
        if b and s is not None and sec:
            try: class_set.add((str(b).strip().upper(), int(s), str(sec).strip().upper()))
            except: pass
    class_options = [{"branch": b, "semester": s, "section": sec} for (b, s, sec) in sorted(class_set, key=lambda x: (x[0], x[1], x[2]))]

    # 3. Collect Faculty Options
    faculty_options = list(collections['faculty'].find({'role': {'$ne': 'super_admin'}}, {"_id": 0, "name": 1, "email": 1}))
    faculty_options.sort(key=lambda f: (f.get('name') or '').lower())

    # 4. Collect VALID COMBINATIONS for dependent filtering
    # We strictly use faculty_assignments as the source of truth for relationships
    combo_set = set()
    
    # From official assignments
    for doc in collections['faculty_assignments'].find({}, {"faculty_email": 1, "branch": 1, "semester": 1, "section": 1, "subject_name": 1}):
        f, b, s, sec, subj = doc.get("faculty_email"), doc.get("branch"), doc.get("semester"), doc.get("section"), doc.get("subject_name")
        if f and b and s is not None and sec and subj:
            combo_set.add((str(f).strip().lower(), str(b).strip().upper(), str(s), str(sec).strip().upper(), str(subj).strip()))

    combinations = [
        {"faculty_email": f, "branch": b, "semester": s, "section": sec, "subject": subj}
        for (f, b, s, sec, subj) in combo_set
    ]

    return subjects, class_options, faculty_options, combinations


def _build_subject_summary(
    collections,
    start_date,
    end_date,
    faculty_email=None,
    subject=None,
    branch=None,
    semester=None,
    section=None,
):
    query = {"date": {"$gte": start_date, "$lte": end_date}}
    if faculty_email:
        query["faculty_email"] = faculty_email
    if subject:
        query["subject"] = subject
    if branch:
        query["branch"] = branch
    if semester:
        try:
            query["semester"] = int(semester)
        except Exception:
            query["semester"] = semester
    if section:
        query["section"] = section

    subject_map = {}
    for doc in collections['attendance'].find(query, {'_id': 0, 'subject': 1, 'student.status': 1}):
        subject_name = str(doc.get('subject', '')).strip() or 'Unknown'
        status = str((doc.get('student') or {}).get('status', 'Absent')).strip()
        entry = subject_map.setdefault(subject_name, {'subject': subject_name, 'present': 0, 'absent': 0})
        if status == 'Present':
            entry['present'] += 1
        else:
            entry['absent'] += 1

    rows = []
    for item in subject_map.values():
        total = item['present'] + item['absent']
        item['percentage'] = round((item['present'] / total) * 100, 2) if total else 0.0
        rows.append(item)

    rows.sort(key=lambda x: x['subject'])
    return rows


def _normalize_report_filters(args):
    today_str = datetime.now().strftime('%Y-%m-%d')
    start_date, end_date = normalize_date_range(
        args.get('start_date'), args.get('end_date'), today_str
    )

    return {
        'start_date': start_date,
        'end_date': end_date,
        'subject': (args.get('subject') or '').strip() or None,
        'branch': (args.get('branch') or '').strip() or None,
        'semester': (args.get('semester') or '').strip() or None,
        'section': (args.get('section') or '').strip() or None,
        'student_roll': (args.get('student_roll') or '').strip() or None,
        'faculty_email': (args.get('faculty_email') or '').strip().lower() or None,
    }


def _sanitize_layout_items(layout_items, max_cols=12):
    cleaned = []
    if not isinstance(layout_items, list):
        return cleaned

    for item in layout_items:
        if not isinstance(item, dict):
            continue
        widget_id = str(item.get('i', '')).strip()
        if not widget_id:
            continue

        try:
            w = int(item.get('w', 3))
        except Exception:
            w = 3
        try:
            h = int(item.get('h', 3))
        except Exception:
            h = 3
        try:
            x = int(item.get('x', 0))
        except Exception:
            x = 0
        try:
            y = int(item.get('y', 0))
        except Exception:
            y = 0

        w = max(1, min(w, max_cols))
        h = max(1, h)
        x = max(0, min(x, max_cols - w))
        y = max(0, y)

        cleaned.append({
            'i': widget_id,
            'x': x,
            'y': y,
            'w': w,
            'h': h,
        })

    return cleaned


def _rectangles_overlap(first, second):
    return not (
        first['x'] + first['w'] <= second['x']
        or second['x'] + second['w'] <= first['x']
        or first['y'] + first['h'] <= second['y']
        or second['y'] + second['h'] <= first['y']
    )


def _compact_layout_items(layout_items, max_cols=12):
    """Apply vertical gravity compaction while preserving a stable item order."""
    items = _sanitize_layout_items(layout_items, max_cols=max_cols)
    ordered = sorted(items, key=lambda item: (item.get('y', 0), item.get('x', 0), item.get('i', '')))
    placed = []

    for item in ordered:
        candidate = {
            'i': item['i'],
            'x': max(0, min(int(item.get('x', 0)), max_cols - int(item.get('w', 1)))),
            'y': max(0, int(item.get('y', 0))),
            'w': max(1, min(int(item.get('w', 1)), max_cols)),
            'h': max(1, int(item.get('h', 1))),
        }

        best_y = candidate['y']
        for test_y in range(0, candidate['y'] + 1):
            probe = {**candidate, 'y': test_y}
            has_collision = any(_rectangles_overlap(probe, existing) for existing in placed)
            if not has_collision:
                best_y = test_y
                break

        candidate['y'] = best_y

        # Keep moving down only if still colliding at chosen y.
        while any(_rectangles_overlap(candidate, existing) for existing in placed):
            candidate['y'] += 1

        placed.append(candidate)

    return placed


def _remove_roll_from_face_stores(student_roll, preserve_class_ids=None):
    """Remove one student's face vectors from cloud/local pickle stores."""
    student_roll = str(student_roll or '').strip()
    if not student_roll:
        return 0
    preserve_ids = {
        str(class_id).strip()
        for class_id in (preserve_class_ids or [])
        if str(class_id).strip()
    }

    removed_count = 0

    try:
        all_pickle_files = list_encodings_from_cloudinary()
    except Exception:
        all_pickle_files = []

    for pickle_file in all_pickle_files:
        class_id = str(pickle_file).replace('.pickle', '')
        if class_id in preserve_ids:
            continue
        try:
            data = get_pickle_from_cloudinary(class_id)
            if not data:
                continue

            encodings = list(data.get('encodings', []) or [])
            metadata = list(data.get('metadata', []) or [])
            kept_encodings = []
            kept_metadata = []

            for idx, meta in enumerate(metadata):
                roll_no = str((meta or {}).get('roll_no', '')).strip()
                if roll_no == student_roll:
                    removed_count += 1
                    continue
                kept_metadata.append(meta)
                if idx < len(encodings):
                    kept_encodings.append(encodings[idx])

            if len(kept_metadata) != len(metadata):
                data['metadata'] = kept_metadata
                data['encodings'] = kept_encodings
                upload_pickle_to_cloudinary_from_memory(data, class_id)
        except Exception:
            continue

    split_dir = current_app.config.get('SPLIT_DIR', 'split_encodings')
    if os.path.exists(split_dir):
        local_files = [f for f in os.listdir(split_dir) if f.endswith('.pickle')]
        for pickle_file in local_files:
            class_id = str(pickle_file).replace('.pickle', '')
            if class_id in preserve_ids:
                continue
            file_path = os.path.join(split_dir, pickle_file)
            try:
                with open(file_path, 'rb') as f:
                    data = pickle.load(f)

                encodings = list((data or {}).get('encodings', []) or [])
                metadata = list((data or {}).get('metadata', []) or [])
                kept_encodings = []
                kept_metadata = []

                removed_here = False
                for idx, meta in enumerate(metadata):
                    roll_no = str((meta or {}).get('roll_no', '')).strip()
                    if roll_no == student_roll:
                        removed_here = True
                        continue
                    kept_metadata.append(meta)
                    if idx < len(encodings):
                        kept_encodings.append(encodings[idx])

                if removed_here:
                    data['metadata'] = kept_metadata
                    data['encodings'] = kept_encodings
                    with open(file_path, 'wb') as f:
                        pickle.dump(data, f)
            except Exception:
                continue

    return removed_count


def _parse_time_safe(value):
    try:
        return datetime.strptime(str(value), "%H:%M").time()
    except Exception:
        return datetime.min.time()


def _compute_status(doc):
    start = _parse_time_safe(doc.get('start_time', ''))
    end = _parse_time_safe(doc.get('end_time', ''))
    now = datetime.now().time()
    if start <= now <= end:
        return 'current'
    if now < start:
        return 'upcoming'
    return 'past'


def _resolve_photo_path(raw_path):
    if not raw_path:
        return None
    if str(raw_path).startswith('http://') or str(raw_path).startswith('https://'):
        return raw_path
    return f"/static/{raw_path.lstrip('/')}"


@bp.post('/auth/login/faculty')
def faculty_login_api():
    data = request.get_json(silent=True) or {}
    email = str(data.get('email', '')).strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return json_error('Email and password are required', status=400)

    collections = get_collections()
    user = collections['faculty'].find_one({'email': email})
    if not user:
        return json_error('Invalid email or password', status=401)

    hashed = user.get('password')
    if not isinstance(hashed, (bytes, bytearray)) or not bcrypt.checkpw(password.encode('utf-8'), hashed):
        return json_error('Invalid email or password', status=401)

    # Ensure prior student session does not override role resolution in current_session_user().
    session.pop('student_roll_no', None)
    session.pop('student_name', None)

    role = str(user.get('role', 'teacher') or 'teacher')
    session['faculty_email'] = email
    session['faculty_name'] = user.get('name', 'Faculty')
    session['role'] = role

    redirect_path = '/admin/dashboard' if role == 'super_admin' else '/faculty/dashboard'
    return jsonify(
        build_auth_response(
            user={
                'email': email,
                'name': session['faculty_name'],
                'role': role,
            },
            role=role,
            redirect_path=redirect_path,
        )
    )


@bp.post('/auth/login/student')
def student_login_api():
    data = request.get_json(silent=True) or {}
    roll_no = str(data.get('roll_no', '')).strip()
    password = data.get('password', '')

    if not roll_no or not password:
        return json_error('Roll number and password are required', status=400)

    collections = get_collections()
    user = collections['students'].find_one({'roll_no': roll_no})
    if not user:
        return json_error('Invalid roll number or password', status=401)

    hashed = user.get('password')
    if not isinstance(hashed, (bytes, bytearray)) or not bcrypt.checkpw(password.encode('utf-8'), hashed):
        return json_error('Invalid roll number or password', status=401)

    # Ensure prior faculty session does not remain active when switching to student.
    session.pop('faculty_email', None)
    session.pop('faculty_name', None)

    session['student_roll_no'] = roll_no
    session['student_name'] = user.get('name', 'Student')
    session['role'] = 'student'

    # Prepare user object with all fields for frontend session
    registered_rolls = _collect_registered_rolls()
    
    user_data = {
        'roll_no': roll_no,
        'name': user.get('name'),
        'branch': user.get('branch'),
        'semester': user.get('semester'),
        'section': user.get('section'),
        'email': user.get('email'),
        'phone': user.get('phone'),
        'address': user.get('address'),
        'role': 'student',
        'faceRegistered': roll_no in registered_rolls,
        'photoPath': _resolve_photo_path(user.get('photo_path', ''))
    }

    return jsonify(
        build_auth_response(
            user=user_data,
            role='student',
            redirect_path='/student/dashboard',
        )
    )


@bp.post('/auth/update-profile/student')
@require_session_role({'student'})
def student_update_profile_api():
    """Update student's own profile contact info."""
    try:
        data = request.get_json(silent=True) or {}
        email = str(data.get('email', '')).strip().lower()
        phone = str(data.get('phone', '')).strip()
        address = str(data.get('address', '')).strip()

        collections = get_collections()
        roll_no = session.get('student_roll_no')
        if not roll_no:
            return json_error('Session expired', status=401)

        update_doc = {
            'email': email,
            'phone': phone,
            'address': address,
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

        result = collections['students'].update_one({'roll_no': roll_no}, {'$set': update_doc})
        if result.matched_count == 0:
            return json_error('Student record not found', status=404)

        return jsonify({
            'success': True,
            'message': 'Profile updated successfully',
            'contact': {
                'email': email,
                'phone': phone,
                'address': address
            }
        })
    except Exception as e:
        return json_error(f'Profile update error: {str(e)}', status=400)


@bp.post('/auth/logout')
def logout_api():
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out'})


@bp.get('/auth/whoami')
def whoami_api():
    info = current_session_user()
    if not info.get('authenticated'):
        return jsonify({'success': True, **info})

    collections = get_collections()
    role = info.get('role')
    user = dict(info.get('user') or {})

    if role == 'student' and user.get('roll_no'):
        student = collections['students'].find_one(
            {'roll_no': user.get('roll_no')}, 
            {'_id': 0, 'branch': 1, 'semester': 1, 'section': 1, 'email': 1, 'phone': 1, 'address': 1, 'photo_path': 1, 'face_registered': 1}
        )
        if student:
            user['branch'] = student.get('branch')
            user['semester'] = student.get('semester')
            user['section'] = student.get('section')
            user['email'] = student.get('email')
            user['phone'] = student.get('phone')
            user['address'] = student.get('address')
            
            # Perform real-time face registration check
            registered_rolls = _collect_registered_rolls()
            user['faceRegistered'] = roll_no in registered_rolls
            user['photoPath'] = _resolve_photo_path(student.get('photo_path'))
    
    elif role in ['teacher', 'super_admin'] and user.get('email'):
        faculty = collections['faculty'].find_one(
            {'email': user.get('email')}, 
            {'_id': 0, 'department': 1, 'photo_path': 1}
        )
        if faculty:
            user['department'] = faculty.get('department')
            user['photoPath'] = _resolve_photo_path(faculty.get('photo_path'))

    info['user'] = user
    return jsonify({'success': True, **info})


@bp.post('/auth/change-password')
@require_session_role({'student', 'teacher', 'super_admin', 'faculty'})
def change_password_api():
    """Unified password change API for all roles."""
    data = request.get_json(silent=True) or {}
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    confirm_password = data.get('confirm_password')

    if not current_password or not new_password or not confirm_password:
        return json_error('All fields are required', status=400)

    if new_password != confirm_password:
        return json_error('New passwords do not match', status=400)

    if len(new_password) < 6:
        return json_error('Password must be at least 6 characters long', status=400)

    role = session.get('role')
    collections = get_collections()
    
    if role == 'student':
        roll_no = session.get('student_roll_no')
        user = collections['students'].find_one({'roll_no': roll_no})
        coll = collections['students']
    else:
        email = session.get('faculty_email')
        user = collections['faculty'].find_one({'email': email})
        coll = collections['faculty']

    if not user:
        return json_error('User not found', status=404)

    stored_hash = user.get('password')
    if not isinstance(stored_hash, (bytes, bytearray)) or not bcrypt.checkpw(current_password.encode('utf-8'), stored_hash):
        return json_error('Current password is incorrect', status=401)

    new_hashed = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
    coll.update_one({'_id': user['_id']}, {'$set': {'password': new_hashed}})

    return jsonify({'success': True, 'message': 'Password updated successfully'})


@bp.get('/faculty/dashboard')
@require_session_role({'teacher', 'super_admin', 'faculty'})
def faculty_dashboard_data_api():
    cache_key = f"faculty_dashboard:{session.get('faculty_email','')}:{session.get('role','')}"
    cached_payload = cache.get(cache_key)
    if cached_payload:
        return jsonify(cached_payload)

    faculty_email = session.get('faculty_email')
    collections = get_collections()

    faculty_doc = collections['faculty'].find_one({'email': faculty_email}, {'_id': 0, 'name': 1, 'email': 1, 'role': 1, 'department': 1, 'photo_path': 1})
    if not faculty_doc:
        return json_error('Faculty not found', status=404)

    faculty_name = str(faculty_doc.get('name', 'Faculty')).strip().lower()
    # 1. Fetch from Timetable
    raw_lectures = list(collections['timetable'].find(
        {
            '$or': [
                {'faculty_email': faculty_email},
                {'faculty_name': faculty_name},
            ]
        },
        {
            '_id': 0, 'day': 1, 'period_no': 1, 'start_time': 1, 'end_time': 1,
            'subject': 1, 'classroom': 1, 'semester': 1, 'branch': 1, 'section': 1,
        }
    ))

    # 2. Fetch from Faculty Assignments (Source of Truth)
    assignments = list(collections['faculty_assignments'].find(
        {'faculty_email': faculty_email},
        {
            '_id': 0, 'branch': 1, 'semester': 1, 'section': 1, 
            'subject_name': 1, 'classroom_name': 1
        }
    ))

    # Merge assignments into raw_lectures intelligently
    # 1. Identify what is scheduled for TODAY to avoid double entries
    now_day = datetime.now().strftime('%A')
    today_combos = set()
    for l in raw_lectures:
        if str(l.get('day', '')).strip().lower() == now_day.lower():
            key = (
                str(l.get('branch', '')).strip().upper(),
                str(l.get('semester', '')).strip(),
                str(l.get('section', '')).strip().upper(),
                str(l.get('subject', '')).strip()
            )
            today_combos.add(key)

    # 2. Add assignments if they aren't already in today's timetable
    seen_in_assignments = set()
    for a in assignments:
        key = (
            str(a.get('branch', '')).strip().upper(),
            str(a.get('semester', '')).strip(),
            str(a.get('section', '')).strip().upper(),
            str(a.get('subject_name', '')).strip()
        )
        # If not already in today's timetable and not already added as an assignment
        if key not in today_combos and key not in seen_in_assignments:
            raw_lectures.append({
                'day': 'Any',
                'period_no': 0,
                'start_time': '00:00',
                'end_time': '23:59',
                'subject': a.get('subject_name'),
                'classroom': a.get('classroom_name', 'TBA'),
                'semester': a.get('semester'),
                'branch': a.get('branch'),
                'section': a.get('section'),
            })
            seen_in_assignments.add(key)

    lectures = []
    for doc in raw_lectures:
        lecture = {
            'day': doc.get('day', ''),
            'period_no': int(doc.get('period_no', 0) or 0),
            'start_time': str(doc.get('start_time', '')),
            'end_time': str(doc.get('end_time', '')),
            'subject': doc.get('subject', ''),
            'classroom': doc.get('classroom', ''),
            'semester': int(doc.get('semester', 0) or 0),
            'branch': doc.get('branch', ''),
            'section': doc.get('section', ''),
        }
        lecture['status'] = _compute_status(lecture)
        lectures.append(lecture)

    today_str = datetime.now().strftime('%Y-%m-%d')
    attendance_stats = {'Present': 0, 'Absent': 0}
    stats_pipeline = [
        {'$match': {'date': today_str, 'faculty_email': faculty_email}},
        {'$group': {'_id': '$student.status', 'count': {'$sum': 1}}},
    ]
    for doc in collections['attendance'].aggregate(stats_pipeline):
        status = doc.get('_id')
        if status in attendance_stats:
            attendance_stats[status] = doc.get('count', 0)

    today = datetime.now()
    thirty_days_ago = today - timedelta(days=30)
    monthly_trend = defaultdict(int)
    for doc in collections['attendance'].find(
        {
            'faculty_email': faculty_email,
            'date': {'$gte': thirty_days_ago.strftime('%Y-%m-%d'), '$lte': today.strftime('%Y-%m-%d')},
            'student.status': 'Present',
        },
        {'date': 1}
    ):
        date = doc.get('date')
        if date:
            monthly_trend[date] += 1

    monthly_labels = sorted(monthly_trend.keys())
    monthly_data = [monthly_trend[d] for d in monthly_labels]

    matrix = defaultdict(lambda: defaultdict(int))
    for doc in collections['attendance'].find(
        {'faculty_email': faculty_email, 'student.status': 'Present'},
        {'subject': 1, 'classroom': 1}
    ):
        subject = doc.get('subject', 'Unknown')
        classroom = doc.get('classroom', 'Unknown')
        matrix[subject][classroom] += 1

    subject_attendance = []
    subjects = sorted(set(list(matrix.keys()) + [lec.get('subject') for lec in lectures if lec.get('subject')]))
    for subject in subjects:
        total = collections['attendance'].count_documents({'faculty_email': faculty_email, 'subject': subject})
        present = collections['attendance'].count_documents({'faculty_email': faculty_email, 'subject': subject, 'student.status': 'Present'})
        pct = int(round((present / total) * 100)) if total > 0 else 0
        subject_attendance.append({'subject': subject, 'percentage': pct, 'present': present, 'total': total})

    seen_classes = set()
    class_filters = []
    for lec in lectures:
        key = (lec.get('branch'), lec.get('semester'), lec.get('section'))
        if key not in seen_classes and all(key):
            seen_classes.add(key)
            class_filters.append({'branch': key[0], 'semester': key[1], 'section': key[2]})

    students_list = []
    if class_filters:
        for s in collections['students'].find({'$or': class_filters}, {'_id': 0, 'roll_no': 1, 'name': 1, 'branch': 1, 'semester': 1, 'section': 1}):
            students_list.append({
                'roll_no': str(s.get('roll_no', '')),
                'name': str(s.get('name', '')),
                'branch': str(s.get('branch', '')),
                'semester': int(s.get('semester', 0) or 0),
                'section': str(s.get('section', '')),
            })

    bar_labels = sorted(matrix.keys())
    classroom_list = sorted(set(cls for sub in matrix.values() for cls in sub))
    heatmap_rows = []
    for subject in bar_labels:
        values = [matrix[subject].get(cls, 0) for cls in classroom_list]
        heatmap_rows.append({'label': subject, 'classrooms': values, 'classroomMap': dict(zip(classroom_list, values))})

    payload = {
        'success': True,
        'profile': {
            'name': faculty_doc.get('name', 'Faculty'),
            'email': faculty_doc.get('email', faculty_email),
            'role': faculty_doc.get('role', 'teacher'),
            'department': faculty_doc.get('department', ''),
            'photo_path': _resolve_photo_path(faculty_doc.get('photo_path')),
        },
        'lectures': lectures,
        'attendance_stats': attendance_stats,
        'monthly_labels': monthly_labels,
        'monthly_data': monthly_data,
        'subject_attendance': subject_attendance,
        'heatmap': {
            'classrooms': classroom_list,
            'rows': heatmap_rows,
        },
        'students_list': students_list,
    }

    cache.set(cache_key, payload, timeout=int(os.environ.get('DASHBOARD_CACHE_TTL', '60')))
    return jsonify(payload)


@bp.get('/admin/dashboard')
@require_session_role({'super_admin'})
def admin_dashboard_data_api():
    cache_key = f"admin_dashboard:{session.get('faculty_email','')}:{session.get('role','')}"
    cached_payload = cache.get(cache_key)
    if cached_payload:
        return jsonify(cached_payload)

    collections = get_collections()
    faculty_email = session.get('faculty_email')

    faculty_doc = collections['faculty'].find_one({'email': faculty_email}, {'_id': 0, 'name': 1, 'email': 1, 'role': 1, 'photo_path': 1, 'department': 1})
    total_faculty = collections['faculty'].count_documents({})
    total_students = collections['students'].count_documents({})
    today = datetime.now().strftime('%Y-%m-%d')
    attendance_today = collections['attendance'].count_documents({'date': today})

    payload = {
        'success': True,
        'profile': {
            'name': (faculty_doc or {}).get('name', 'Admin'),
            'email': (faculty_doc or {}).get('email', faculty_email),
            'role': (faculty_doc or {}).get('role', 'super_admin'),
            'department': (faculty_doc or {}).get('department', ''),
            'photo_path': _resolve_photo_path((faculty_doc or {}).get('photo_path')),
        },
        'stats': {
            'faculty_count': total_faculty,
            'student_count': total_students,
            'attendance_today': attendance_today,
        },
    }

    cache.set(cache_key, payload, timeout=int(os.environ.get('DASHBOARD_CACHE_TTL', '60')))
    return jsonify(payload)


@bp.get('/admin/ping')
@require_session_role({'super_admin'})
def admin_ping():
    return jsonify({'success': True, 'message': 'admin-ok'})


@bp.get('/faculty/dashboard/layout')
@require_session_role({'teacher', 'super_admin', 'faculty'})
def faculty_dashboard_layout_get_api():
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return json_error('Not authenticated', status=401)

    collections = get_collections()
    layout_collection = collections.get('faculty_layouts')
    if layout_collection is None:
        layout_collection = collections.get('dashboard_layouts')
    if layout_collection is None:
        return json_error('Layout collection is not configured', status=500)
    doc = layout_collection.find_one(
        {'faculty_email': faculty_email},
        {'_id': 0, 'desktop_layout': 1, 'mobile_layout': 1, 'updated_at': 1}
    ) or {}

    desktop_layout = _compact_layout_items(doc.get('desktop_layout', []) or [], max_cols=12)
    mobile_layout = _compact_layout_items(doc.get('mobile_layout', []) or [], max_cols=6)

    return jsonify({
        'success': True,
        'desktop_layout': desktop_layout,
        'mobile_layout': mobile_layout,
        'updated_at': doc.get('updated_at'),
    })


@bp.get('/faculty/profile')
@require_session_role({'teacher', 'super_admin', 'faculty'})
def faculty_profile_api():
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return json_error('Not authenticated', status=401)

    collections = get_collections()
    faculty_doc = collections['faculty'].find_one(
        {'email': faculty_email},
        {
            '_id': 0,
            'name': 1,
            'email': 1,
            'role': 1,
            'department': 1,
            'faculty_id': 1,
            'phone': 1,
            'joined_date': 1,
            'qualification': 1,
            'address': 1,
            'photo_path': 1,
        }
    )
    if not faculty_doc:
        return json_error('Faculty not found', status=404)

    return jsonify({
        'success': True,
        'profile': {
            'name': faculty_doc.get('name', 'Faculty'),
            'email': faculty_doc.get('email', faculty_email),
            'role': faculty_doc.get('role', 'faculty'),
            'department': faculty_doc.get('department', ''),
            'faculty_id': faculty_doc.get('faculty_id', ''),
            'phone': faculty_doc.get('phone', ''),
            'joined_date': faculty_doc.get('joined_date', ''),
            'qualification': faculty_doc.get('qualification', ''),
            'address': faculty_doc.get('address', ''),
            'photo_path': _resolve_photo_path(faculty_doc.get('photo_path')),
        },
    })


@bp.post('/faculty/profile')
@require_session_role({'teacher', 'super_admin', 'faculty'})
def faculty_profile_update_api():
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return json_error('Not authenticated', status=401)

    payload = request.get_json(silent=True) or {}
    updates = {}

    name = str(payload.get('name', '')).strip()
    phone = str(payload.get('phone', '')).strip()
    qualification = str(payload.get('qualification', '')).strip()
    address = str(payload.get('address', '')).strip()

    if name:
        updates['name'] = name
    updates['phone'] = phone
    updates['qualification'] = qualification
    updates['address'] = address

    collections = get_collections()
    result = collections['faculty'].update_one({'email': faculty_email}, {'$set': updates})
    if result.matched_count == 0:
        return json_error('Faculty not found', status=404)

    faculty_doc = collections['faculty'].find_one(
        {'email': faculty_email},
        {
            '_id': 0,
            'name': 1,
            'email': 1,
            'role': 1,
            'department': 1,
            'faculty_id': 1,
            'phone': 1,
            'joined_date': 1,
            'qualification': 1,
            'address': 1,
            'photo_path': 1,
        }
    ) or {}

    return jsonify({
        'success': True,
        'message': 'Profile updated successfully',
        'profile': {
            'name': faculty_doc.get('name', 'Faculty'),
            'email': faculty_doc.get('email', faculty_email),
            'role': faculty_doc.get('role', 'faculty'),
            'department': faculty_doc.get('department', ''),
            'faculty_id': faculty_doc.get('faculty_id', ''),
            'phone': faculty_doc.get('phone', ''),
            'joined_date': faculty_doc.get('joined_date', ''),
            'qualification': faculty_doc.get('qualification', ''),
            'address': faculty_doc.get('address', ''),
            'photo_path': _resolve_photo_path(faculty_doc.get('photo_path')),
        },
    })


@bp.get('/faculty/profile/timetable')
@require_session_role({'teacher', 'super_admin', 'faculty'})
def faculty_profile_timetable_api():
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return json_error('Not authenticated', status=401)

    collections = get_collections()
    faculty_doc = collections['faculty'].find_one(
        {'email': faculty_email},
        {'_id': 0, 'name': 1}
    ) or {}
    faculty_name_lower = str(faculty_doc.get('name', '')).strip().lower()

    slots = [
        _serialize_timetable_slot(doc)
        for doc in collections['timetable'].find(
            _faculty_timetable_query(faculty_email, faculty_name_lower),
            {
                'day': 1,
                'start_time': 1,
                'end_time': 1,
                'subject': 1,
                'classroom': 1,
                'branch': 1,
                'semester': 1,
                'section': 1,
                'period_no': 1,
            }
        )
    ]
    slots.sort(
        key=lambda item: (
            TIMETABLE_DAY_ORDER.index(item.get('day')) if item.get('day') in TIMETABLE_DAY_ORDER else 99,
            item.get('start_time', ''),
            item.get('end_time', ''),
            item.get('subject', '').lower(),
        )
    )

    return jsonify({
        'success': True,
        'timetable': slots,
        'days': TIMETABLE_DAY_ORDER[:6],
    })


@bp.get('/faculty/profile/timetable/options')
@require_session_role({'teacher', 'super_admin', 'faculty'})
def faculty_profile_timetable_options_api():
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return json_error('Not authenticated', status=401)

    collections = get_collections()
    faculty_doc = collections['faculty'].find_one(
        {'email': faculty_email},
        {'_id': 0, 'name': 1}
    ) or {}
    faculty_name_lower = str(faculty_doc.get('name', '')).strip().lower()

    branch_set = set()
    class_set = set()
    classroom_set = set()
    subject_map = {}

    assignment_query = _faculty_assignment_query(faculty_email, faculty_name_lower)
    for doc in collections['faculty_assignments'].find(assignment_query, {
        '_id': 0,
        'branch': 1,
        'semester': 1,
        'section': 1,
        'subject_code': 1,
        'subject_name': 1,
        'classroom': 1,
    }):
        branch = str(doc.get('branch', '')).strip().upper()
        section = str(doc.get('section', '')).strip().upper()
        subject_code = str(doc.get('subject_code', '')).strip().upper()
        subject_name = str(doc.get('subject_name', '')).strip()
        classroom = str(doc.get('classroom', '')).strip()

        try:
            semester = int(doc.get('semester'))
        except Exception:
            semester = None

        if branch:
            branch_set.add(branch)
        if branch and section and semester is not None:
            class_set.add((branch, semester, section))
        if classroom:
            classroom_set.add(classroom)

        subject_key = f"{subject_code or subject_name.lower()}|{branch}|{semester}|{section}"
        if subject_key and subject_key not in subject_map:
            subject_map[subject_key] = {
                'branch': branch,
                'semester': semester,
                'section': section,
                'subject_code': subject_code,
                'subject_name': subject_name,
                'value': subject_key,
                'label': f"{subject_name} ({subject_code}) - {branch} / {semester} / {section}" if subject_name and subject_code else f"{subject_name or subject_code} - {branch} / {semester} / {section}",
                'class_label': f'{branch} / {semester} / {section}',
                'classroom': classroom,
            }

    for doc in collections['students'].find({}, {'_id': 0, 'branch': 1, 'semester': 1, 'section': 1}):
        branch = str(doc.get('branch', '')).strip().upper()
        section = str(doc.get('section', '')).strip().upper()
        semester_value = doc.get('semester')
        try:
            semester = int(semester_value)
        except Exception:
            continue

        if branch:
            branch_set.add(branch)
        if branch and section:
            class_set.add((branch, semester, section))

    for doc in collections['timetable'].find({}, {'_id': 0, 'branch': 1, 'semester': 1, 'section': 1, 'classroom': 1}):
        branch = str(doc.get('branch', '')).strip().upper()
        section = str(doc.get('section', '')).strip().upper()
        semester_value = doc.get('semester')
        classroom = str(doc.get('classroom', '')).strip()

        try:
            semester = int(semester_value)
        except Exception:
            semester = None

        if branch:
            branch_set.add(branch)
        if branch and section and semester is not None:
            class_set.add((branch, semester, section))
        if classroom:
            classroom_set.add(classroom)

    for doc in collections['academic_classrooms'].find({}, {'_id': 0, 'name': 1, 'active': 1}):
        if doc.get('active', True) is False:
            continue
        name = str(doc.get('name', '')).strip()
        if name:
            classroom_set.add(name)

    branch_options = sorted(branch_set)
    assigned_class_options = [
        {
            'branch': branch,
            'semester': semester,
            'section': section,
            'value': f'{branch}|{semester}|{section}',
            'label': f'{branch} / {semester} / {section}',
        }
        for branch, semester, section in sorted(class_set, key=lambda item: (item[0], item[1], item[2]))
    ]
    class_options = [
        {
            'branch': branch,
            'semester': semester,
            'section': section,
            'value': f'{branch}|{semester}|{section}',
            'label': f'{branch} / {semester} / {section}',
        }
        for branch, semester, section in sorted(class_set, key=lambda item: (item[0], item[1], item[2]))
    ]
    classroom_options = sorted(classroom_set, key=lambda value: value.lower())
    subject_options = sorted(subject_map.values(), key=lambda item: (item['branch'], item['semester'] or 0, item['section'], item['label']))

    return jsonify({
        'success': True,
        'branches': branch_options,
        'assigned_classes': assigned_class_options,
        'classes': class_options,
        'classrooms': classroom_options,
        'subjects': subject_options,
    })


@bp.post('/faculty/profile/timetable')
@require_session_role({'teacher', 'super_admin', 'faculty'})
def faculty_profile_timetable_save_api():
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return json_error('Not authenticated', status=401)

    payload = request.get_json(silent=True) or {}
    slot_id = str(payload.get('id', '')).strip()
    day = _normalize_day_label(payload.get('day'))
    start_time = str(payload.get('start_time', '')).strip()
    end_time = str(payload.get('end_time', '')).strip()
    subject = str(payload.get('subject', '')).strip()
    subject_code = str(payload.get('subject_code', '')).strip().upper()
    classroom = str(payload.get('classroom', '')).strip()
    branch = str(payload.get('branch', '')).strip().upper()
    section = str(payload.get('section', '')).strip().upper()
    semester_raw = payload.get('semester')

    if not day or not start_time or not end_time or not subject or not branch or semester_raw in (None, '') or not section:
        return json_error('Day, time, subject, branch, semester, and section are required', status=400)

    try:
        semester = int(semester_raw)
    except Exception:
        return json_error('Semester must be a valid number', status=400)

    try:
        start_dt = _parse_clock_time(start_time)
        end_dt = _parse_clock_time(end_time)
    except Exception:
        return json_error('Time must use HH:MM format', status=400)

    if end_dt <= start_dt:
        return json_error('End time must be after start time', status=400)

    collections = get_collections()
    faculty_doc = collections['faculty'].find_one(
        {'email': faculty_email},
        {'_id': 0, 'name': 1}
    )
    if not faculty_doc:
        return json_error('Faculty not found', status=404)

    faculty_name_lower = str(faculty_doc.get('name', '')).strip().lower()
    timetable_query = _faculty_timetable_query(faculty_email, faculty_name_lower)

    assigned_subjects = list(
        collections['faculty_assignments'].find(
            _faculty_assignment_query(faculty_email, faculty_name_lower),
            {
                '_id': 0,
                'branch': 1,
                'semester': 1,
                'section': 1,
                'subject_code': 1,
                'subject_name': 1,
            }
        )
    )

    matching_assignments = []
    for assignment in assigned_subjects:
        assignment_branch = str(assignment.get('branch', '')).strip().upper()
        assignment_section = str(assignment.get('section', '')).strip().upper()
        try:
            assignment_semester = int(assignment.get('semester'))
        except Exception:
            assignment_semester = None

        if assignment_branch != branch or assignment_semester != semester or assignment_section != section:
            continue
        matching_assignments.append(assignment)

    if matching_assignments:
        allowed_subject_keys = set()
        for assignment in matching_assignments:
            allowed_subject_keys.add(str(assignment.get('subject_code', '')).strip().upper())
            allowed_subject_keys.add(str(assignment.get('subject_name', '')).strip().lower())

        if subject_code:
            subject_key = subject_code
        else:
            subject_key = subject.lower()

        if subject_key not in allowed_subject_keys:
            return json_error('Selected subject is not assigned to this class', status=409)

        if subject_code:
            resolved_subject_name = next(
                (
                    str(assignment.get('subject_name', '')).strip()
                    for assignment in matching_assignments
                    if str(assignment.get('subject_code', '')).strip().upper() == subject_code
                ),
                subject,
            )
            subject = resolved_subject_name or subject

    existing_slots = list(
        collections['timetable'].find(
            timetable_query,
            {
                'day': 1,
                'start_time': 1,
                'end_time': 1,
                'subject': 1,
            }
        )
    )

    for existing in existing_slots:
        if slot_id and str(existing.get('_id')) == slot_id:
            continue
        if _normalize_day_label(existing.get('day')) != day:
            continue
        try:
            existing_start = _parse_clock_time(existing.get('start_time'))
            existing_end = _parse_clock_time(existing.get('end_time'))
        except Exception:
            continue
        if start_dt < existing_end and end_dt > existing_start:
            return json_error(
                f"Time overlaps with {str(existing.get('subject', 'another slot')).strip() or 'another slot'} on {day}",
                status=409,
            )

    class_slots = list(
        collections['timetable'].find(
            {
                'day': day,
                'branch': branch,
                'semester': semester,
                'section': section,
            },
            {
                'start_time': 1,
                'end_time': 1,
                'subject': 1,
            }
        )
    )
    for existing in class_slots:
        if slot_id and str(existing.get('_id')) == slot_id:
            continue
        try:
            existing_start = _parse_clock_time(existing.get('start_time'))
            existing_end = _parse_clock_time(existing.get('end_time'))
        except Exception:
            continue
        if start_dt < existing_end and end_dt > existing_start:
            return json_error(
                f"Class {branch} / {semester} / {section} already has an overlapping lecture during this time",
                status=409,
            )

    ordered_times = sorted({
        str(doc.get('start_time', '')).strip()
        for doc in existing_slots
        if str(doc.get('start_time', '')).strip()
    } | {start_time})
    period_no = ordered_times.index(start_time) + 1

    slot_doc = {
        'day': day,
        'start_time': start_time,
        'end_time': end_time,
        'subject': subject,
        'subject_code': subject_code,
        'classroom': classroom,
        'branch': branch,
        'semester': semester,
        'section': section,
        'period_no': period_no,
        'faculty_email': faculty_email,
        'faculty_name': faculty_name_lower,
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }

    if slot_id:
        try:
            slot_object_id = ObjectId(slot_id)
        except Exception:
            return json_error('Invalid timetable slot', status=400)

        result = collections['timetable'].update_one(
            {
                '_id': slot_object_id,
                **timetable_query,
            },
            {'$set': slot_doc},
        )
        if result.matched_count == 0:
            return json_error('Timetable slot not found', status=404)
        saved_doc = collections['timetable'].find_one({'_id': slot_object_id})
        message = 'Timetable slot updated'
    else:
        slot_doc['created_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        insert_result = collections['timetable'].insert_one(slot_doc)
        saved_doc = collections['timetable'].find_one({'_id': insert_result.inserted_id})
        message = 'Timetable slot added'

    _clear_faculty_dashboard_cache(faculty_email)

    return jsonify({
        'success': True,
        'message': message,
        'slot': _serialize_timetable_slot(saved_doc or slot_doc),
    })


@bp.delete('/faculty/profile/timetable/<slot_id>')
@require_session_role({'teacher', 'super_admin', 'faculty'})
def faculty_profile_timetable_delete_api(slot_id):
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return json_error('Not authenticated', status=401)

    collections = get_collections()
    faculty_doc = collections['faculty'].find_one(
        {'email': faculty_email},
        {'_id': 0, 'name': 1}
    ) or {}
    faculty_name_lower = str(faculty_doc.get('name', '')).strip().lower()

    try:
        slot_object_id = ObjectId(slot_id)
    except Exception:
        return json_error('Invalid timetable slot', status=400)

    result = collections['timetable'].delete_one(
        {
            '_id': slot_object_id,
            **_faculty_timetable_query(faculty_email, faculty_name_lower),
        }
    )
    if result.deleted_count == 0:
        return json_error('Timetable slot not found', status=404)

    _clear_faculty_dashboard_cache(faculty_email)

    return jsonify({
        'success': True,
        'message': 'Timetable slot deleted',
    })


@bp.post('/faculty/dashboard/layout')
@require_session_role({'teacher', 'super_admin', 'faculty'})
def faculty_dashboard_layout_save_api():
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return json_error('Not authenticated', status=401)

    payload = request.get_json(silent=True) or {}
    desktop_layout = _compact_layout_items(payload.get('desktop_layout', []) or [], max_cols=12)
    mobile_layout = _compact_layout_items(payload.get('mobile_layout', []) or [], max_cols=6)

    collections = get_collections()
    layout_collection = collections.get('faculty_layouts')
    if layout_collection is None:
        layout_collection = collections.get('dashboard_layouts')
    if layout_collection is None:
        return json_error('Layout collection is not configured', status=500)
    layout_collection.update_one(
        {'faculty_email': faculty_email},
        {
            '$set': {
                'faculty_email': faculty_email,
                'desktop_layout': desktop_layout,
                'mobile_layout': mobile_layout,
                'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }
        },
        upsert=True,
    )

    return jsonify({
        'success': True,
        'message': 'Dashboard layout saved',
    })


def _serialize_calendar_event(doc):
    return {
        'id': str(doc.get('event_id', '')),
        'dateKey': str(doc.get('date_key', '')),
        'title': str(doc.get('title', '') or ''),
        'startTime': str(doc.get('start_time', '') or ''),
        'endTime': str(doc.get('end_time', '') or ''),
        'location': str(doc.get('location', '') or ''),
        'description': str(doc.get('description', '') or ''),
        'repeat': str(doc.get('repeat', 'none') or 'none'),
        'createdAt': str(doc.get('created_at', '') or ''),
        'updatedAt': str(doc.get('updated_at', '') or ''),
    }


def _validate_repeat(value):
    allowed = {'none', 'weekly', 'monthly', 'yearly'}
    repeat = str(value or 'none').strip().lower()
    return repeat if repeat in allowed else 'none'


@bp.get('/faculty/calendar/events')
@require_session_role({'teacher', 'super_admin', 'faculty'})
def faculty_calendar_events_list_api():
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return json_error('Not authenticated', status=401)

    collections = get_collections()
    event_collection = collections.get('faculty_calendar_events')
    if event_collection is None:
        return json_error('Calendar collection is not configured', status=500)

    docs = list(
        event_collection.find(
            {'faculty_email': faculty_email},
            {
                '_id': 0,
                'event_id': 1,
                'date_key': 1,
                'title': 1,
                'start_time': 1,
                'end_time': 1,
                'location': 1,
                'description': 1,
                'repeat': 1,
                'created_at': 1,
                'updated_at': 1,
            },
        )
    )

    docs.sort(key=lambda item: (str(item.get('date_key', '')), str(item.get('start_time', '')), str(item.get('title', ''))))
    return jsonify({'success': True, 'events': [_serialize_calendar_event(item) for item in docs]})


@bp.post('/faculty/calendar/events')
@require_session_role({'teacher', 'super_admin', 'faculty'})
def faculty_calendar_events_create_api():
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return json_error('Not authenticated', status=401)

    payload = request.get_json(silent=True) or {}
    date_key = str(payload.get('dateKey', '')).strip()
    title = str(payload.get('title', '')).strip()
    if not date_key or not title:
        return json_error('dateKey and title are required', status=400)

    created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    event_doc = {
        'faculty_email': faculty_email,
        'event_id': str(uuid4()),
        'date_key': date_key,
        'title': title,
        'start_time': str(payload.get('startTime', '')).strip(),
        'end_time': str(payload.get('endTime', '')).strip(),
        'location': str(payload.get('location', '')).strip(),
        'description': str(payload.get('description', '')).strip(),
        'repeat': _validate_repeat(payload.get('repeat')),
        'created_at': created_at,
        'updated_at': created_at,
    }

    collections = get_collections()
    event_collection = collections.get('faculty_calendar_events')
    if event_collection is None:
        return json_error('Calendar collection is not configured', status=500)

    event_collection.insert_one(event_doc)
    return jsonify({'success': True, 'event': _serialize_calendar_event(event_doc)})


@bp.put('/faculty/calendar/events/<event_id>')
@require_session_role({'teacher', 'super_admin', 'faculty'})
def faculty_calendar_events_update_api(event_id):
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return json_error('Not authenticated', status=401)

    payload = request.get_json(silent=True) or {}
    updates = {
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }

    if 'dateKey' in payload:
        updates['date_key'] = str(payload.get('dateKey') or '').strip()
    if 'title' in payload:
        updates['title'] = str(payload.get('title') or '').strip()
    if 'startTime' in payload:
        updates['start_time'] = str(payload.get('startTime') or '').strip()
    if 'endTime' in payload:
        updates['end_time'] = str(payload.get('endTime') or '').strip()
    if 'location' in payload:
        updates['location'] = str(payload.get('location') or '').strip()
    if 'description' in payload:
        updates['description'] = str(payload.get('description') or '').strip()
    if 'repeat' in payload:
        updates['repeat'] = _validate_repeat(payload.get('repeat'))

    if not str(updates.get('date_key', '')).strip() and 'date_key' in updates:
        return json_error('dateKey cannot be empty', status=400)
    if not str(updates.get('title', '')).strip() and 'title' in updates:
        return json_error('title cannot be empty', status=400)

    collections = get_collections()
    event_collection = collections.get('faculty_calendar_events')
    if event_collection is None:
        return json_error('Calendar collection is not configured', status=500)

    result = event_collection.update_one(
        {'faculty_email': faculty_email, 'event_id': str(event_id)},
        {'$set': updates},
    )
    if result.matched_count == 0:
        return json_error('Event not found', status=404)

    updated = event_collection.find_one(
        {'faculty_email': faculty_email, 'event_id': str(event_id)},
        {
            '_id': 0,
            'event_id': 1,
            'date_key': 1,
            'title': 1,
            'start_time': 1,
            'end_time': 1,
            'location': 1,
            'description': 1,
            'repeat': 1,
            'created_at': 1,
            'updated_at': 1,
        },
    )
    return jsonify({'success': True, 'event': _serialize_calendar_event(updated or {})})


@bp.delete('/faculty/calendar/events/<event_id>')
@require_session_role({'teacher', 'super_admin', 'faculty'})
def faculty_calendar_events_delete_api(event_id):
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return json_error('Not authenticated', status=401)

    collections = get_collections()
    event_collection = collections.get('faculty_calendar_events')
    if event_collection is None:
        return json_error('Calendar collection is not configured', status=500)

    result = event_collection.delete_one({'faculty_email': faculty_email, 'event_id': str(event_id)})
    if result.deleted_count == 0:
        return json_error('Event not found', status=404)

    return jsonify({'success': True, 'deleted': str(event_id)})


@bp.get('/faculty/reports/filters')
@require_session_role({'teacher', 'super_admin', 'faculty'})
def faculty_report_filters_api():
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return json_error('Not authenticated', status=401)

    cache_key = f"faculty_report_filters:{faculty_email}"
    cached_payload = cache.get(cache_key)
    if cached_payload:
        return jsonify(cached_payload)

    collections = get_collections()
    faculty_doc = collections['faculty'].find_one({'email': faculty_email}, {'_id': 0, 'name': 1})
    faculty_name_lower = str((faculty_doc or {}).get('name', '')).strip().lower()

    subject_options, class_options, combinations = _get_faculty_filter_options(collections, faculty_email, faculty_name_lower)
    branch_options = sorted({c.get('branch') for c in class_options if c.get('branch')})
    semester_options = sorted({c.get('semester') for c in class_options if c.get('semester') is not None})
    section_options = sorted({c.get('section') for c in class_options if c.get('section')})

    payload = {
        'success': True,
        'subject_options': subject_options,
        'class_options': class_options,
        'branch_options': branch_options,
        'semester_options': semester_options,
        'section_options': section_options,
        'combinations': combinations,
    }

    cache.set(cache_key, payload, timeout=int(os.environ.get('REPORT_CACHE_TTL', '120')))
    return jsonify(payload)


@bp.get('/faculty/reports')
@require_session_role({'teacher', 'super_admin', 'faculty'})
def faculty_reports_api():
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return json_error('Not authenticated', status=401)

    cache_key = f"faculty_reports:{faculty_email}:{request.query_string.decode('utf-8')}"
    cached_payload = cache.get(cache_key)
    if cached_payload:
        return jsonify(cached_payload)

    collections = get_collections()
    faculty_doc = collections['faculty'].find_one({'email': faculty_email}, {'_id': 0, 'name': 1})
    faculty_name_lower = str((faculty_doc or {}).get('name', '')).strip().lower()
    subject_options, _class_options, _combinations = _get_faculty_filter_options(collections, faculty_email, faculty_name_lower)

    filters = _normalize_report_filters(request.args)
    if filters['subject'] and filters['subject'] not in subject_options:
        return json_error('Selected subject is not available for this faculty', status=403)

    summary_rows, detail_rows, totals = build_attendance_report(
        collections,
        start_date=filters['start_date'],
        end_date=filters['end_date'],
        faculty_email=faculty_email,
        subject=filters['subject'],
        branch=filters['branch'],
        semester=filters['semester'],
        section=filters['section'],
        student_roll=filters['student_roll'],
    )

    subject_summary = _build_subject_summary(
        collections,
        start_date=filters['start_date'],
        end_date=filters['end_date'],
        faculty_email=faculty_email,
        subject=filters['subject'],
        branch=filters['branch'],
        semester=filters['semester'],
        section=filters['section'],
    )

    payload = {
        'success': True,
        'filters': filters,
        'summary_rows': summary_rows,
        'detail_rows': detail_rows,
        'totals': totals,
        'subject_summary': subject_summary,
    }

    cache.set(cache_key, payload, timeout=int(os.environ.get('REPORT_CACHE_TTL', '120')))
    return jsonify(payload)


@bp.get('/faculty/reports/export')
@require_session_role({'teacher', 'super_admin', 'faculty'})
def faculty_reports_export_api():
    export_format = str(request.args.get('format', '')).strip().lower()
    if export_format not in {'csv', 'pdf'}:
        return json_error('format must be csv or pdf', status=400)

    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return json_error('Not authenticated', status=401)

    collections = get_collections()
    faculty_doc = collections['faculty'].find_one({'email': faculty_email}, {'_id': 0, 'name': 1})
    faculty_name_lower = str((faculty_doc or {}).get('name', '')).strip().lower()
    subject_options, _class_options, _combinations = _get_faculty_filter_options(collections, faculty_email, faculty_name_lower)

    filters = _normalize_report_filters(request.args)
    if filters['subject'] and filters['subject'] not in subject_options:
        return json_error('Selected subject is not available for this faculty', status=403)

    summary_rows, detail_rows, _totals = build_attendance_report(
        collections,
        start_date=filters['start_date'],
        end_date=filters['end_date'],
        faculty_email=faculty_email,
        subject=filters['subject'],
        branch=filters['branch'],
        semester=filters['semester'],
        section=filters['section'],
        student_roll=filters['student_roll'],
    )

    if export_format == 'csv':
        csv_bytes, filename = export_csv_report(
            summary_rows,
            detail_rows,
            filters['start_date'],
            filters['end_date'],
            filename_prefix='faculty_attendance_report',
        )
        response = make_response(csv_bytes)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        return response

    pdf_bytes, filename = export_pdf_report(
        summary_rows,
        detail_rows,
        filters['start_date'],
        filters['end_date'],
        filename_prefix='faculty_attendance_report',
    )
    response = make_response(pdf_bytes)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response


@bp.get('/admin/reports/filters')
@require_session_role({'super_admin'})
def admin_report_filters_api():
    cache_key = "admin_report_filters"
    cached_payload = cache.get(cache_key)
    if cached_payload:
        return jsonify(cached_payload)

    collections = get_collections()
    subject_options, class_options, faculty_options, combinations = _get_admin_filter_options(collections)
    branch_options = sorted({c.get('branch') for c in class_options if c.get('branch')})
    semester_options = sorted({c.get('semester') for c in class_options if c.get('semester') is not None})
    section_options = sorted({c.get('section') for c in class_options if c.get('section')})

    payload = {
        'success': True,
        'subject_options': subject_options,
        'class_options': class_options,
        'branch_options': branch_options,
        'semester_options': semester_options,
        'section_options': section_options,
        'faculty_options': faculty_options,
        'combinations': combinations,
    }

    cache.set(cache_key, payload, timeout=int(os.environ.get('REPORT_CACHE_TTL', '120')))
    return jsonify(payload)


@bp.get('/admin/reports')
@require_session_role({'super_admin'})
def admin_reports_api():
    cache_key = f"admin_reports:{request.query_string.decode('utf-8')}"
    cached_payload = cache.get(cache_key)
    if cached_payload:
        return jsonify(cached_payload)

    collections = get_collections()
    filters = _normalize_report_filters(request.args)

    summary_rows, detail_rows, totals = build_attendance_report(
        collections,
        start_date=filters['start_date'],
        end_date=filters['end_date'],
        faculty_email=filters['faculty_email'],
        subject=filters['subject'],
        branch=filters['branch'],
        semester=filters['semester'],
        section=filters['section'],
        student_roll=filters['student_roll'],
    )

    subject_summary = _build_subject_summary(
        collections,
        start_date=filters['start_date'],
        end_date=filters['end_date'],
        faculty_email=filters['faculty_email'],
        subject=filters['subject'],
        branch=filters['branch'],
        semester=filters['semester'],
        section=filters['section'],
    )

    payload = {
        'success': True,
        'filters': filters,
        'summary_rows': summary_rows,
        'detail_rows': detail_rows,
        'totals': totals,
        'subject_summary': subject_summary,
    }

    cache.set(cache_key, payload, timeout=int(os.environ.get('REPORT_CACHE_TTL', '120')))
    return jsonify(payload)


@bp.get('/admin/reports/export')
@require_session_role({'super_admin'})
def admin_reports_export_api():
    export_format = str(request.args.get('format', '')).strip().lower()
    if export_format not in {'csv', 'pdf'}:
        return json_error('format must be csv or pdf', status=400)

    collections = get_collections()
    filters = _normalize_report_filters(request.args)

    summary_rows, detail_rows, _totals = build_attendance_report(
        collections,
        start_date=filters['start_date'],
        end_date=filters['end_date'],
        faculty_email=filters['faculty_email'],
        subject=filters['subject'],
        branch=filters['branch'],
        semester=filters['semester'],
        section=filters['section'],
        student_roll=filters['student_roll'],
    )

    if export_format == 'csv':
        csv_bytes, filename = export_csv_report(
            summary_rows,
            detail_rows,
            filters['start_date'],
            filters['end_date'],
            filename_prefix='admin_attendance_report',
        )
        response = make_response(csv_bytes)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        return response

    pdf_bytes, filename = export_pdf_report(
        summary_rows,
        detail_rows,
        filters['start_date'],
        filters['end_date'],
        filename_prefix='admin_attendance_report',
    )
    response = make_response(pdf_bytes)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response


@bp.get('/admin/faculty')
@require_session_role({'super_admin'})
def admin_list_faculty():
    """Get all faculty for admin management"""
    collections = get_collections()
    
    faculty_list = list(collections['faculty'].find(
        {'role': {'$ne': 'super_admin'}},
        {
            '_id': 1,
            'name': 1,
            'email': 1,
            'department': 1,
            'role': 1,
            'photo_path': 1,
        }
    ).sort([('name', 1)]))
    
    faculty_data = []
    for f in faculty_list:
        faculty_data.append({
            '_id': str(f.get('_id', '')),
            'name': f.get('name', ''),
            'email': f.get('email', ''),
            'department': f.get('department', ''),
            'role': f.get('role', 'faculty'),
            'photo_path': _resolve_photo_path(f.get('photo_path', '')),
        })
    
    return jsonify({
        'success': True,
        'faculty': faculty_data,
    })


@bp.get('/admin/students')
@require_session_role({'super_admin'})
def admin_list_students():
    """Get all students for admin management"""
    collections = get_collections()
    
    students_list = list(collections['students'].find(
        {},
        {
            '_id': 1,
            'roll_no': 1,
            'name': 1,
            'email': 1,
            'branch': 1,
            'semester': 1,
            'section': 1,
            'photo_path': 1,
        }
    ).sort([('roll_no', 1)]))
    
    registered_rolls = _collect_registered_rolls()
    students_data = []
    for s in students_list:
        roll_no = str(s.get('roll_no', '')).strip()
        students_data.append({
            '_id': str(s.get('_id', '')),
            'roll_no': roll_no,
            'name': s.get('name', ''),
            'email': s.get('email', ''),
            'branch': s.get('branch', ''),
            'semester': s.get('semester', ''),
            'section': s.get('section', ''),
            'photo_path': _resolve_photo_path(s.get('photo_path', '')),
            'face_registered': roll_no in registered_rolls,
        })
    
    return jsonify({
        'success': True,
        'students': students_data,
    })


@bp.get('/admin/faces')
@require_session_role({'super_admin'})
def admin_list_faces():
    """List all registered faces found in cloud/local encoding stores."""
    registrations = _collect_face_registrations()
    registrations.sort(key=lambda x: (str(x.get('student_name', '')).lower(), str(x.get('student_roll', '')).lower()))

    return jsonify({
        'success': True,
        'faces': registrations,
        'summary': {
            'total_registrations': len(registrations),
            'unique_students': len({str(x.get('student_roll', '')).strip() for x in registrations if str(x.get('student_roll', '')).strip()}),
        },
    })


@bp.post('/admin/faces/reregister/<student_roll>')
@require_session_role({'super_admin'})
def admin_reregister_face(student_roll):
    """Clear existing stored face data while optionally preserving the fresh replacement class file."""
    payload = request.get_json(silent=True) or {}
    preserve_class_files = payload.get('preserve_class_files') or []
    preserve_class_file = str(payload.get('preserve_class_file', '')).strip()
    if preserve_class_file:
        preserve_class_files.append(preserve_class_file)

    removed_count = _remove_roll_from_face_stores(student_roll, preserve_class_ids=preserve_class_files)
    
    # If preserve_class_files is empty, it means we are performing a full deletion.
    if not preserve_class_files:
        collections = get_collections()
        collections['students'].update_one({'roll_no': student_roll}, {'$set': {'face_registered': False}})
    return jsonify({
        'success': True,
        'message': 'Face data replaced successfully',
        'student_roll': str(student_roll),
        'removed_count': int(removed_count),
        'preserved_class_files': [str(item) for item in preserve_class_files if str(item).strip()],
    })


@bp.post('/admin/faculty')
@require_session_role({'super_admin'})
def admin_create_faculty():
    """Create a new faculty user."""
    data = request.get_json(silent=True) or {}
    name = str(data.get('name', '')).strip()
    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', '')).strip() or '123456'
    department = str(data.get('department', 'CSE')).strip() or 'CSE'

    if not name or not email:
        return json_error('Name and email are required', status=400)

    collections = get_collections()
    if collections['faculty'].find_one({'email': email}):
        return json_error('Faculty with this email already exists', status=409)

    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    doc = {
        'name': name,
        'email': email,
        'password': hashed_password,
        'department': department,
        'role': 'teacher',
        'created_at': datetime.now().strftime('%Y-%m-%d'),
    }
    insert_result = collections['faculty'].insert_one(doc)

    return jsonify({
        'success': True,
        'message': 'Faculty created successfully',
        'faculty': {
            '_id': str(insert_result.inserted_id),
            'name': name,
            'email': email,
            'department': department,
            'role': 'teacher',
            'photo_path': _resolve_photo_path(''),
        },
    })


@bp.post('/admin/students')
@require_session_role({'super_admin'})
def admin_create_student():
    """Create a new student."""
    data = request.get_json(silent=True) or {}
    name = str(data.get('name', '')).strip()
    roll_no = str(data.get('roll_no', '')).strip()
    branch = str(data.get('branch', '')).strip()
    semester_raw = data.get('semester')
    section = str(data.get('section', '')).strip()

    email = str(data.get('email', '')).strip().lower()
    phone = str(data.get('phone', '')).strip()
    address = str(data.get('address', '')).strip()

    if not name or not roll_no or not branch or semester_raw is None or not section:
        return json_error('Name, roll number, branch, semester and section are required', status=400)

    try:
        semester = int(semester_raw)
    except Exception:
        return json_error('Semester must be a valid number', status=400)

    collections = get_collections()
    if collections['students'].find_one({'roll_no': roll_no}):
        return json_error('Student with this roll number already exists', status=409)

    default_password = '123456'
    hashed_password = bcrypt.hashpw(default_password.encode('utf-8'), bcrypt.gensalt())

    doc = {
        'name': name,
        'roll_no': roll_no,
        'branch': branch,
        'semester': semester,
        'section': section,
        'email': email,
        'phone': phone,
        'address': address,
        'password': hashed_password,
        'role': 'student',
        'created_at': datetime.now().strftime('%Y-%m-%d'),
    }
    insert_result = collections['students'].insert_one(doc)

    return jsonify({
        'success': True,
        'message': 'Student created successfully',
        'student': {
            '_id': str(insert_result.inserted_id),
            'name': name,
            'roll_no': roll_no,
            'branch': branch,
            'semester': semester,
            'section': section,
            'email': email,
            'phone': phone,
            'address': address,
            'photo_path': _resolve_photo_path(''),
        },
    })


@bp.post('/admin/students/<student_id>')
@require_session_role({'super_admin'})
def admin_update_student(student_id):
    """Update an existing student."""
    try:
        data = request.get_json(silent=True) or {}
        name = str(data.get('name', '')).strip()
        roll_no = str(data.get('roll_no', '')).strip()
        branch = str(data.get('branch', '')).strip()
        semester_raw = data.get('semester')
        section = str(data.get('section', '')).strip()
        email = str(data.get('email', '')).strip().lower()
        phone = str(data.get('phone', '')).strip()
        address = str(data.get('address', '')).strip()

        if not name or not roll_no or not branch or semester_raw is None or not section:
            return json_error('Name, roll number, branch, semester and section are required', status=400)

        try:
            semester = int(semester_raw)
        except Exception:
            return json_error('Semester must be a valid number', status=400)

        collections = get_collections()
        student_oid = ObjectId(student_id)
        
        # Check if roll_no is taken by another student
        existing = collections['students'].find_one({'roll_no': roll_no, '_id': {'$ne': student_oid}})
        if existing:
            return json_error('Student with this roll number already exists', status=409)

        update_doc = {
            'name': name,
            'roll_no': roll_no,
            'branch': branch,
            'semester': semester,
            'section': section,
            'email': email,
            'phone': phone,
            'address': address,
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        
        result = collections['students'].update_one({'_id': student_oid}, {'$set': update_doc})
        
        if result.matched_count == 0:
            return json_error('Student not found', status=404)

        return jsonify({
            'success': True,
            'message': 'Student updated successfully',
            'student': {
                '_id': student_id,
                'name': name,
                'roll_no': roll_no,
                'branch': branch,
                'semester': semester,
                'section': section,
                'email': email,
                'phone': phone,
                'address': address,
            },
        })
    except Exception as e:
        return json_error(f'Update error: {str(e)}', status=400)


@bp.post('/admin/faculty/<faculty_id>/toggle-admin')
@require_session_role({'super_admin'})
def admin_toggle_faculty_admin(faculty_id):
    """Promote/demote faculty between faculty and super_admin roles."""
    try:
        collections = get_collections()
        faculty_oid = ObjectId(faculty_id)
        faculty_doc = collections['faculty'].find_one({'_id': faculty_oid})
        if not faculty_doc:
            return json_error('Faculty not found', status=404)

        current_role = str(faculty_doc.get('role', 'faculty') or 'faculty').lower()
        target_role = 'faculty' if current_role == 'super_admin' else 'super_admin'

        collections['faculty'].update_one(
            {'_id': faculty_oid},
            {'$set': {'role': target_role}}
        )

        return jsonify({
            'success': True,
            'message': 'Role updated successfully',
            'role': target_role,
        })
    except Exception as e:
        return json_error(f'Role update error: {str(e)}', status=400)


@bp.post('/admin/faculty/<faculty_id>/reset-password')
@require_session_role({'super_admin'})
def admin_reset_faculty_password(faculty_id):
    """Reset faculty password to default value 123456."""
    try:
        collections = get_collections()
        faculty_oid = ObjectId(faculty_id)
        faculty_doc = collections['faculty'].find_one({'_id': faculty_oid}, {'_id': 1})
        if not faculty_doc:
            return json_error('Faculty not found', status=404)

        default_password = '123456'
        hashed_password = bcrypt.hashpw(default_password.encode('utf-8'), bcrypt.gensalt())

        collections['faculty'].update_one(
            {'_id': faculty_oid},
            {'$set': {'password': hashed_password}}
        )

        return jsonify({
            'success': True,
            'message': 'Password reset to default 123456',
        })
    except Exception as e:
        return json_error(f'Password reset error: {str(e)}', status=400)


@bp.post('/admin/students/<student_id>/reset-password')
@require_session_role({'super_admin'})
def admin_reset_student_password(student_id):
    """Reset student password to default value 123456."""
    try:
        collections = get_collections()
        student_oid = ObjectId(student_id)
        student_doc = collections['students'].find_one({'_id': student_oid}, {'_id': 1})
        if not student_doc:
            return json_error('Student not found', status=404)

        default_password = '123456'
        hashed_password = bcrypt.hashpw(default_password.encode('utf-8'), bcrypt.gensalt())

        collections['students'].update_one(
            {'_id': student_oid},
            {'$set': {'password': hashed_password}}
        )

        return jsonify({
            'success': True,
            'message': 'Password reset to default 123456',
        })
    except Exception as e:
        return json_error(f'Password reset error: {str(e)}', status=400)


@bp.delete('/admin/faculty/<faculty_id>')
@require_session_role({'super_admin'})
def admin_delete_faculty(faculty_id):
    """Delete a faculty member"""
    try:
        collections = get_collections()
        faculty_oid = ObjectId(faculty_id)
        result = collections['faculty'].delete_one({'_id': faculty_oid})
        
        if result.deleted_count > 0:
            return jsonify({'success': True, 'message': 'Faculty deleted'})
        else:
            return json_error('Faculty not found', status=404)
    except Exception as e:
        return json_error(f'Delete error: {str(e)}', status=400)


@bp.delete('/admin/students/<student_id>')
@require_session_role({'super_admin'})
def admin_delete_student(student_id):
    """Delete a student"""
    try:
        collections = get_collections()
        student_oid = ObjectId(student_id)
        result = collections['students'].delete_one({'_id': student_oid})
        
        if result.deleted_count > 0:
            return jsonify({'success': True, 'message': 'Student deleted'})
        else:
            return json_error('Student not found', status=404)
    except Exception as e:
        return json_error(f'Delete error: {str(e)}', status=400)


@bp.get('/admin/academic-setup')
@require_session_role({'super_admin'})
def admin_academic_setup_api():
    collections = get_collections()

    branches = [
        _serialize_academic_branch(doc)
        for doc in collections['academic_branches'].find({}, {'code': 1, 'name': 1, 'active': 1}).sort([('code', 1)])
    ]
    classes = [
        _serialize_academic_class(doc)
        for doc in collections['academic_classes'].find({}, {'branch': 1, 'semester': 1, 'section': 1, 'label': 1, 'active': 1}).sort([('branch', 1), ('semester', 1), ('section', 1)])
    ]
    classrooms = [
        _serialize_academic_classroom(doc)
        for doc in collections['academic_classrooms'].find({}, {'name': 1, 'type': 1, 'capacity': 1, 'active': 1}).sort([('name', 1)])
    ]
    subjects = [
        _serialize_academic_subject(doc)
        for doc in collections['academic_subjects'].find({}, {'code': 1, 'name': 1, 'branch': 1, 'semester': 1, 'type': 1, 'active': 1}).sort([('branch', 1), ('semester', 1), ('name', 1)])
    ]
    assignments = [
        _serialize_academic_assignment(doc)
        for doc in collections['faculty_assignments'].find({}, {
            'faculty_email': 1,
            'faculty_name': 1,
            'branch': 1,
            'semester': 1,
            'section': 1,
            'subject_code': 1,
            'subject_name': 1,
            'classroom': 1,
            'active': 1,
        }).sort([('faculty_name', 1), ('branch', 1), ('semester', 1), ('section', 1)])
    ]
    faculty_options = [
        {
            'email': str(doc.get('email', '')).strip().lower(),
            'name': str(doc.get('name', '')).strip(),
            'label': f"{str(doc.get('name', '')).strip()} ({str(doc.get('email', '')).strip().lower()})",
            'department': str(doc.get('department', '')).strip().upper(),
        }
        for doc in collections['faculty'].find(
            {'role': {'$ne': 'super_admin'}}, 
            {'_id': 0, 'name': 1, 'email': 1, 'department': 1}
        ).sort([('name', 1)])
        if str(doc.get('email', '')).strip()
    ]

    return jsonify({
        'success': True,
        'summary': {
            'branches': len(branches),
            'classes': len(classes),
            'classrooms': len(classrooms),
            'subjects': len(subjects),
            'assignments': len(assignments),
        },
        'branches': branches,
        'classes': classes,
        'classrooms': classrooms,
        'subjects': subjects,
        'assignments': assignments,
        'faculty_options': faculty_options,
    })


@bp.post('/admin/academic-setup/<entity>')
@require_session_role({'super_admin'})
def admin_academic_setup_save_api(entity):
    entity = str(entity or '').strip().lower()
    if entity not in ACADEMIC_SETUP_CONFIG:
        return json_error('Unsupported academic setup entity', status=404)

    collections = get_collections()
    payload = request.get_json(silent=True) or {}
    item_id = str(payload.get('id', '')).strip()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    collection = collections[ACADEMIC_SETUP_CONFIG[entity]['collection']]

    existing_filter = {}
    doc = {}
    serializer = None

    if entity == 'branches':
        code = str(payload.get('code', '')).strip().upper()
        name = str(payload.get('name', '')).strip()
        active = _normalize_boolean(payload.get('active'), True)
        if not code or not name:
            return json_error('Branch code and name are required', status=400)
        duplicate = collection.find_one({'code': code})
        if duplicate and str(duplicate.get('_id')) != item_id:
            return json_error('Branch code already exists', status=409)
        doc = {'code': code, 'name': name, 'active': active, 'updated_at': now_str}
        existing_filter = {'code': code}
        serializer = _serialize_academic_branch
    elif entity == 'classes':
        branch = str(payload.get('branch', '')).strip().upper()
        semester = _to_int_or_none(payload.get('semester'))
        section = str(payload.get('section', '')).strip().upper()
        active = _normalize_boolean(payload.get('active'), True)
        label = str(payload.get('label', '')).strip() or f'{branch} / {semester} / {section}'
        if not branch or semester is None or not section:
            return json_error('Branch, semester, and section are required', status=400)
        duplicate = collection.find_one({'branch': branch, 'semester': semester, 'section': section})
        if duplicate and str(duplicate.get('_id')) != item_id:
            return json_error('Class already exists', status=409)
        doc = {'branch': branch, 'semester': semester, 'section': section, 'label': label, 'active': active, 'updated_at': now_str}
        existing_filter = {'branch': branch, 'semester': semester, 'section': section}
        serializer = _serialize_academic_class
    elif entity == 'classrooms':
        name = str(payload.get('name', '')).strip()
        room_type = str(payload.get('type', '')).strip() or 'Classroom'
        capacity = _to_int_or_none(payload.get('capacity'))
        active = _normalize_boolean(payload.get('active'), True)
        if not name:
            return json_error('Classroom name is required', status=400)
        duplicate = collection.find_one({'name': name})
        if duplicate and str(duplicate.get('_id')) != item_id:
            return json_error('Classroom already exists', status=409)
        doc = {'name': name, 'type': room_type, 'capacity': capacity, 'active': active, 'updated_at': now_str}
        existing_filter = {'name': name}
        serializer = _serialize_academic_classroom
    elif entity == 'subjects':
        code = str(payload.get('code', '')).strip().upper()
        name = str(payload.get('name', '')).strip()
        branch = str(payload.get('branch', '')).strip().upper()
        semester = _to_int_or_none(payload.get('semester'))
        subject_type = str(payload.get('type', '')).strip() or 'theory'
        active = _normalize_boolean(payload.get('active'), True)
        if not code or not name or not branch or semester is None:
            return json_error('Subject code, name, branch, and semester are required', status=400)
        duplicate = collection.find_one({'code': code})
        if duplicate and str(duplicate.get('_id')) != item_id:
            return json_error('Subject code already exists', status=409)
        doc = {'code': code, 'name': name, 'branch': branch, 'semester': semester, 'type': subject_type, 'active': active, 'updated_at': now_str}
        existing_filter = {'code': code}
        serializer = _serialize_academic_subject
    else:
        faculty_email = str(payload.get('faculty_email', '')).strip().lower()
        branch = str(payload.get('branch', '')).strip().upper()
        semester = _to_int_or_none(payload.get('semester'))
        section = str(payload.get('section', '')).strip().upper()
        subject_code = str(payload.get('subject_code', '')).strip().upper()
        classroom = str(payload.get('classroom', '')).strip()
        active = _normalize_boolean(payload.get('active'), True)
        if not faculty_email or not branch or semester is None or not section or not subject_code:
            return json_error('Faculty, class, and subject are required', status=400)

        faculty_doc = collections['faculty'].find_one({'email': faculty_email}, {'_id': 0, 'name': 1})
        if not faculty_doc:
            return json_error('Selected faculty was not found', status=404)
        subject_doc = collections['academic_subjects'].find_one({'code': subject_code}, {'_id': 0, 'name': 1, 'code': 1})
        if not subject_doc:
            return json_error('Selected subject was not found', status=404)

        duplicate = collection.find_one({
            'faculty_email': faculty_email,
            'branch': branch,
            'semester': semester,
            'section': section,
            'subject_code': subject_code,
        })
        if duplicate and str(duplicate.get('_id')) != item_id:
            return json_error('This faculty assignment already exists', status=409)
        doc = {
            'faculty_email': faculty_email,
            'faculty_name': str(faculty_doc.get('name', '')).strip(),
            'branch': branch,
            'semester': semester,
            'section': section,
            'subject_code': str(subject_doc.get('code', '')).strip().upper(),
            'subject_name': str(subject_doc.get('name', '')).strip(),
            'classroom': classroom,
            'active': active,
            'updated_at': now_str,
        }
        existing_filter = {
            'faculty_email': faculty_email,
            'branch': branch,
            'semester': semester,
            'section': section,
            'subject_code': subject_code,
        }
        serializer = _serialize_academic_assignment

    if item_id:
        try:
            object_id = ObjectId(item_id)
        except Exception:
            return json_error('Invalid record id', status=400)
        result = collection.update_one({'_id': object_id}, {'$set': doc})
        if result.matched_count == 0:
            return json_error(f"{ACADEMIC_SETUP_CONFIG[entity]['label']} not found", status=404)
        saved = collection.find_one({'_id': object_id})
        message = f"{ACADEMIC_SETUP_CONFIG[entity]['label']} updated successfully"
    else:
        doc['created_at'] = now_str
        insert_result = collection.insert_one(doc)
        saved = collection.find_one({'_id': insert_result.inserted_id})
        message = f"{ACADEMIC_SETUP_CONFIG[entity]['label']} created successfully"

    # Invalidate caches
    cache.delete('admin_report_filters')
    cache.clear()

    return jsonify({
        'success': True,
        'message': message,
        'item': serializer(saved or doc),
    })


@bp.delete('/admin/academic-setup/<entity>/<item_id>')
@require_session_role({'super_admin'})
def admin_academic_setup_delete_api(entity, item_id):
    entity = str(entity or '').strip().lower()
    if entity not in ACADEMIC_SETUP_CONFIG:
        return json_error('Unsupported academic setup entity', status=404)

    try:
        object_id = ObjectId(item_id)
    except Exception:
        return json_error('Invalid record id', status=400)

    collections = get_collections()
    collection = collections[ACADEMIC_SETUP_CONFIG[entity]['collection']]
    result = collection.delete_one({'_id': object_id})
    if result.deleted_count == 0:
        return json_error(f"{ACADEMIC_SETUP_CONFIG[entity]['label']} not found", status=404)

    # Invalidate caches
    cache.delete('admin_report_filters')
    cache.clear()

    return jsonify({
        'success': True,
        'message': f"{ACADEMIC_SETUP_CONFIG[entity]['label']} deleted successfully",
    })


@bp.post('/faculty/manual-attendance/students')
@require_session_role({'teacher', 'super_admin', 'faculty'})
def faculty_manual_attendance_students_api():
    faculty_email = session.get('faculty_email')
    data = request.get_json(silent=True) or {}

    branch = str(data.get('branch', '')).strip()
    semester_raw = data.get('semester')
    section = str(data.get('section', '')).strip()
    subject = str(data.get('subject', '')).strip()
    date_str = str(data.get('date', datetime.now().strftime('%Y-%m-%d'))).strip()

    try:
        semester = int(semester_raw)
    except Exception:
        return json_error('Valid semester is required', status=400)

    if not branch or not section or not subject:
        return json_error('Branch, section and subject are required', status=400)

    collections = get_collections()

    status_map = {}
    existing_cursor = collections['attendance'].find(
        {
            'date': date_str,
            'faculty_email': faculty_email,
            'branch': branch,
            'semester': semester,
            'section': section,
            'subject': subject,
        },
        {'_id': 0, 'student.roll_no': 1, 'student.status': 1}
    )
    for row in existing_cursor:
        student_doc = row.get('student') or {}
        roll_no = str(student_doc.get('roll_no', '')).strip()
        status = str(student_doc.get('status', '')).strip()
        if roll_no:
            status_map[roll_no] = status

    students = []
    students_cursor = collections['students'].find(
        {
            'branch': branch,
            'semester': semester,
            'section': section,
        },
        {'_id': 0, 'roll_no': 1, 'name': 1}
    ).sort('roll_no', 1)

    for student in students_cursor:
        roll_no = str(student.get('roll_no', '')).strip()
        name = str(student.get('name', '')).strip()
        status = status_map.get(roll_no)
        students.append({
            'roll_no': roll_no,
            'name': name,
            'status': status,
            'status_exists': status is not None,
        })

    return jsonify({
        'success': True,
        'students': students,
        'already_marked_count': len(status_map),
    })


@bp.post('/faculty/manual-attendance/submit')
@require_session_role({'teacher', 'super_admin', 'faculty'})
def faculty_manual_attendance_submit_api():
    faculty_email = session.get('faculty_email')
    data = request.get_json(silent=True) or {}

    branch = str(data.get('branch', '')).strip()
    semester_raw = data.get('semester')
    section = str(data.get('section', '')).strip()
    subject = str(data.get('subject', '')).strip()
    classroom = str(data.get('classroom', '')).strip()
    date_str = str(data.get('date', datetime.now().strftime('%Y-%m-%d'))).strip()
    present_rolls = {str(roll).strip() for roll in (data.get('present_rolls') or []) if str(roll).strip()}

    try:
        semester = int(semester_raw)
    except Exception:
        return json_error('Valid semester is required', status=400)

    if not branch or not section or not subject:
        return json_error('Branch, section and subject are required', status=400)

    collections = get_collections()
    students_cursor = collections['students'].find(
        {
            'branch': branch,
            'semester': semester,
            'section': section,
        },
        {'_id': 0, 'roll_no': 1, 'name': 1}
    )

    students = []
    for item in students_cursor:
        roll_no = str(item.get('roll_no', '')).strip()
        name = str(item.get('name', '')).strip()
        if roll_no:
            students.append({'roll_no': roll_no, 'name': name})

    if not students:
        return json_error('No students found for selected class', status=404)

    for student in students:
        roll_no = student['roll_no']
        name = student['name']
        status = 'Present' if roll_no in present_rolls else 'Absent'
        collections['attendance'].update_one(
            {
                'date': date_str,
                'subject': subject,
                'faculty_email': faculty_email,
                'branch': branch,
                'semester': semester,
                'section': section,
                'student.roll_no': roll_no,
            },
            {
                '$set': {
                    'date': date_str,
                    'subject': subject,
                    'faculty_email': faculty_email,
                    'classroom': classroom,
                    'branch': branch,
                    'semester': semester,
                    'section': section,
                    'student': {
                        'roll_no': roll_no,
                        'name': name,
                        'status': status,
                    },
                }
            },
            upsert=True,
        )

    return jsonify({
        'success': True,
        'message': 'Attendance saved',
        'present_count': len(present_rolls),
        'total_count': len(students),
        'absent_count': max(0, len(students) - len(present_rolls)),
    })
