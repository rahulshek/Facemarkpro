from flask import Blueprint, render_template, session, redirect, url_for, flash, request, current_app, make_response
from app.db.mongo_client import get_collections
from app.services.face_recognition import FaceRecognitionService
from werkzeug.utils import secure_filename
import bcrypt
import os
import pickle
import numpy as np
import cv2
import base64
from datetime import datetime
from bson import ObjectId
from app.utils.report_utils import (
    build_attendance_report,
    export_csv_report,
    export_pdf_report,
    normalize_date_range,
)
from app.utils.cloudinary_utils import (
    upload_pickle_to_cloudinary_from_memory, 
    get_pickle_from_cloudinary,
    list_encodings_from_cloudinary
)

bp = Blueprint('admin', __name__, url_prefix='/admin')

@bp.app_context_processor
def inject_admin_info():
    """Provide admin info for admin templates."""
    from flask import url_for
    default_photo = 'img/faculty.jpg'
    
    faculty_email = session.get('faculty_email')
    if not faculty_email:
        return {
            'photo_path': url_for('static', filename=default_photo),
            'is_admin': False,
            'email': '',
            'faculty': 'Admin'
        }

    try:
        collections = get_collections()
        user = collections['faculty'].find_one({'email': faculty_email})
        if not user:
            return {
                'photo_path': url_for('static', filename=default_photo),
                'is_admin': False,
                'email': faculty_email,
                'faculty': 'Admin'
            }
        
        raw_path = user.get('photo_path', default_photo)
        def resolve_photo_url(path):
            if not path:
                return url_for('static', filename=default_photo)
            if path.startswith('http') or path.startswith('https'):
                return path
            return url_for('static', filename=path)
        
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
            'faculty': 'Admin'
        }

@bp.before_request
def require_admin():
    """Protect all admin routes"""
    if 'faculty_email' not in session:
        return redirect(url_for('faculty.multilogin'))
    
    if session.get('role') != 'super_admin':
        flash("Access Denied: You are not an administrator.", "error")
        return redirect(url_for('faculty.dashboard'))


def _get_admin_filter_options(collections):
    """Collect subjects, classes, and faculty options for report filters."""
    timetable_docs = list(collections['timetable'].find({}, {"_id": 0}))

    subjects = sorted({doc.get("subject", "") for doc in timetable_docs if doc.get("subject")})

    class_set = set()
    for doc in timetable_docs:
        branch = doc.get("branch", "")
        semester_val = doc.get("semester")
        section = doc.get("section", "")
        try:
            semester_int = int(semester_val) if semester_val is not None else None
        except Exception:
            semester_int = semester_val

        if branch and semester_int is not None and section:
            class_set.add((branch, semester_int, section))

    class_options = [
        {"branch": b, "semester": s, "section": sec}
        for (b, s, sec) in sorted(class_set, key=lambda x: (x[0], x[1], x[2]))
    ]

    faculty_options = list(collections['faculty'].find({'role': {'$ne': 'super_admin'}}, {"_id": 0, "name": 1, "email": 1}))
    faculty_options.sort(key=lambda f: (f.get('name') or '').lower())

    return subjects, class_options, faculty_options

@bp.route('/dashboard')
def dashboard():
    collections = get_collections()
    total_faculty = collections['faculty'].count_documents({})
    total_students = collections['students'].count_documents({})
    stats = {
        'faculty_count': total_faculty,
        'student_count': total_students,
        'attendance_today': 0
    }
    return render_template('admin/dashboard.html', stats=stats)


@bp.route('/reports')
def reports():
    """Admin attendance reports across all subjects/classes."""
    collections = get_collections()
    subject_options, class_options, faculty_options = _get_admin_filter_options(collections)

    today_str = datetime.now().strftime('%Y-%m-%d')
    start_date, end_date = normalize_date_range(
        request.args.get('start_date'), request.args.get('end_date'), today_str
    )

    subject = request.args.get('subject') or None
    branch = request.args.get('branch') or None
    semester = request.args.get('semester') or None
    section = request.args.get('section') or None
    student_roll = request.args.get('student_roll') or None
    faculty_email = request.args.get('faculty_email') or None
    export_format = request.args.get('export')

    summary_rows, detail_rows, totals = build_attendance_report(
        collections,
        start_date=start_date,
        end_date=end_date,
        faculty_email=faculty_email,
        subject=subject,
        branch=branch,
        semester=semester,
        section=section,
        student_roll=student_roll,
    )

    if export_format == 'csv':
        csv_bytes, filename = export_csv_report(
            summary_rows,
            detail_rows,
            start_date,
            end_date,
            filename_prefix='admin_attendance_report',
        )
        response = make_response(csv_bytes)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        return response

    if export_format == 'pdf':
        pdf_bytes, filename = export_pdf_report(
            summary_rows,
            detail_rows,
            start_date,
            end_date,
            filename_prefix='admin_attendance_report',
        )
        response = make_response(pdf_bytes)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        return response

    branch_options = sorted({c.get('branch') for c in class_options if c.get('branch')})
    semester_options = sorted({c.get('semester') for c in class_options if c.get('semester') is not None})
    section_options = sorted({c.get('section') for c in class_options if c.get('section')})

    return render_template(
        'admin/admin_reports.html',
        start_date=start_date,
        end_date=end_date,
        subject_options=subject_options,
        class_options=class_options,
        branch_options=branch_options,
        semester_options=semester_options,
        section_options=section_options,
        faculty_options=faculty_options,
        selected_subject=subject or '',
        selected_branch=branch or '',
        selected_semester=str(semester) if semester else '',
        selected_section=section or '',
        selected_faculty=faculty_email or '',
        student_roll=student_roll or '',
        summary_rows=summary_rows,
        detail_rows=detail_rows,
        totals=totals,
    )

# --------------------------------------------------------------------
# FACULTY MANAGEMENT
# --------------------------------------------------------------------

@bp.route('/faculty')
def manage_faculty():
    collections = get_collections()
    faculty_list = list(collections['faculty'].find({}))
    return render_template('admin/manage_faculty.html', faculty_list=faculty_list)

@bp.route('/faculty/add', methods=['POST'])
def add_faculty():
    collections = get_collections()
    name = request.form.get('name')
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password')
    department = request.form.get('department', 'CSE')

    if not name or not email or not password:
        flash("All fields are required.", "error")
        return redirect(url_for('admin.manage_faculty'))

    # Check MongoDB
    if collections['faculty'].find_one({"email": email}):
        flash("Faculty with this email already exists.", "error")
        return redirect(url_for('admin.manage_faculty'))

    # Add to MongoDB (single source of truth)
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    user_doc = {
        "email": email,
        "password": hashed_password,
        "name": name,
        "role": "teacher",
        "department": department,
        "created_at": datetime.now().strftime('%Y-%m-%d')
    }
    collections['faculty'].insert_one(user_doc)
    
    flash(f"Faculty {name} added successfully.", "success")
    return redirect(url_for('admin.manage_faculty'))

@bp.route('/faculty/delete/<string:email_id>', methods=['POST'])
def delete_faculty(email_id):
    collections = get_collections()
    
    # Prvent deleting self
    if email_id == session.get('faculty_email'):
        flash("You cannot delete your own account.", "error")
        return redirect(url_for('admin.manage_faculty'))

    # Remove from MongoDB (single source of truth)
    collections['faculty'].delete_one({"email": email_id})

    flash(f"Faculty {email_id} deleted successfully.", "success")
    return redirect(url_for('admin.manage_faculty'))


@bp.route('/faculty/toggle-admin/<string:email_id>', methods=['POST'])
def toggle_faculty_admin(email_id):
    """Toggle faculty between teacher and super_admin role"""
    collections = get_collections()
    
    if email_id == session.get('faculty_email'):
        flash("You cannot change your own role.", "error")
        return redirect(url_for('admin.manage_faculty'))
    
    faculty = collections['faculty'].find_one({"email": email_id})
    if not faculty:
        flash("Faculty not found.", "error")
        return redirect(url_for('admin.manage_faculty'))
    
    new_role = "teacher" if faculty.get('role') == 'super_admin' else 'super_admin'
    collections['faculty'].update_one(
        {"email": email_id},
        {"$set": {"role": new_role}}
    )
    
    role_text = "Admin" if new_role == 'super_admin' else "Teacher"
    flash(f"Faculty {faculty.get('name')} is now a {role_text}.", "success")
    return redirect(url_for('admin.manage_faculty'))


@bp.route('/faculty/reset-password/<string:email_id>', methods=['POST'])
def reset_faculty_password(email_id):
    """Reset faculty password to 123456"""
    collections = get_collections()
    
    if email_id == session.get('faculty_email'):
        flash("You cannot reset your own password here.", "error")
        return redirect(url_for('admin.manage_faculty'))
    
    faculty = collections['faculty'].find_one({"email": email_id})
    if not faculty:
        flash("Faculty not found.", "error")
        return redirect(url_for('admin.manage_faculty'))
    
    default_password = "123456"
    hashed_password = bcrypt.hashpw(default_password.encode('utf-8'), bcrypt.gensalt())
    collections['faculty'].update_one(
        {"email": email_id},
        {"$set": {"password": hashed_password}}
    )
    
    flash(f"Password for {faculty.get('name')} reset to 123456.", "success")
    return redirect(url_for('admin.manage_faculty'))


@bp.route('/student/reset-password/<string:student_id>', methods=['POST'])
def reset_student_password(student_id):
    """Reset student password to 123456"""
    collections = get_collections()
    
    try:
        student = collections['students'].find_one({"_id": ObjectId(student_id)})
    except:
        flash("Invalid student ID.", "error")
        return redirect(url_for('admin.manage_students'))
    
    if not student:
        flash("Student not found.", "error")
        return redirect(url_for('admin.manage_students'))
    
    default_password = "123456"
    hashed_password = bcrypt.hashpw(default_password.encode('utf-8'), bcrypt.gensalt())
    collections['students'].update_one(
        {"_id": ObjectId(student_id)},
        {"$set": {"password": hashed_password}}
    )
    
    flash(f"Password for {student.get('name')} reset to 123456.", "success")
    return redirect(url_for('admin.manage_students'))


# --------------------------------------------------------------------
# STUDENT MANAGEMENT
# --------------------------------------------------------------------

@bp.route('/students')
def manage_students():
    collections = get_collections()
    
    # Filtering
    branch = request.args.get('branch')
    semester = request.args.get('semester')
    section = request.args.get('section')
    
    query = {}
    if branch: query['branch'] = branch
    if semester: query['semester'] = int(semester)
    if section: query['section'] = section
    
    students_list = list(collections['students'].find(query))
    return render_template('admin/manage_students.html', students_list=students_list)

@bp.route('/students/add', methods=['POST'])
def add_student():
    collections = get_collections()
    name = request.form.get('name')
    roll_no = request.form.get('roll_no')
    branch = request.form.get('branch')
    semester = request.form.get('semester')
    section = request.form.get('section')

    if not all([name, roll_no, branch, semester, section]):
        flash("All fields are required.", "error")
        return redirect(url_for('admin.manage_students'))

    # Check existence
    if collections['students'].find_one({"roll_no": roll_no}):
        flash("Student with this Roll No already exists.", "error")
        return redirect(url_for('admin.manage_students'))

    student_doc = {
        "name": name,
        "roll_no": roll_no,
        "branch": branch,
        "semester": int(semester),
        "section": section,
        "created_at": datetime.now().strftime('%Y-%m-%d'),
        "role": "student"
    }
    
    collections['students'].insert_one(student_doc)
    flash(f"Student {name} ({roll_no}) added successfully.", "success")
    return redirect(url_for('admin.manage_students'))

@bp.route('/students/delete/<string:student_id>', methods=['POST'])
def delete_student(student_id):
    collections = get_collections()
    try:
        collections['students'].delete_one({"_id": ObjectId(student_id)})
        flash("Student deleted successfully.", "success")
    except:
        flash("Error deleting student.", "error")
        
    return redirect(url_for('admin.manage_students'))


# --------------------------------------------------------------------
# FACE REGISTRATION MANAGEMENT
# --------------------------------------------------------------------

@bp.route('/faces', methods=['GET'])
def manage_faces():
    collections = get_collections()
    all_students = list(collections['students'].find({}, {"_id": 0, "name": 1, "roll_no": 1, "branch": 1, "semester": 1}))
    
    # Get all registrations from Cloudinary AND local files
    registrations = []
    seen_students = set()  # Track unique student-class combinations
    
    # 1. Get from Cloudinary
    all_pickle_files = list_encodings_from_cloudinary()
    
    for pickle_file in all_pickle_files:
        class_id = pickle_file.replace('.pickle', '')
        try:
            data = get_pickle_from_cloudinary(class_id)
            if not data: continue
            
            metadata = data.get('metadata', [])
            parts = class_id.split('_')
            if len(parts) >= 2:
                branch = parts[0]
                semester = parts[1]
            else:
                branch = "Unknown"
                semester = "Unknown"
                
            for student in metadata:
                roll_no = student.get('roll_no', 'Unknown')
                unique_key = f"{roll_no}_{class_id}"
                if unique_key not in seen_students:
                    registrations.append({
                        'student_name': student.get('name', 'Unknown'),
                        'student_roll': roll_no,
                        'branch': branch,
                        'semester': semester,
                        'class_file': class_id,
                        'source': 'cloud'
                    })
                    seen_students.add(unique_key)
        except:
            continue
    
    # 2. Get from local split_encodings directory
    split_dir = current_app.config.get('SPLIT_DIR', 'split_encodings')
    if os.path.exists(split_dir):
        local_files = [f for f in os.listdir(split_dir) if f.endswith('.pickle')]
        for pickle_file in local_files:
            class_id = pickle_file.replace('.pickle', '')
            try:
                file_path = os.path.join(split_dir, pickle_file)
                with open(file_path, 'rb') as f:
                    data = pickle.load(f)
                    
                if not data: continue
                
                metadata = data.get('metadata', [])
                parts = class_id.split('_')
                if len(parts) >= 2:
                    branch = parts[0]
                    semester = parts[1]
                else:
                    branch = "Unknown"
                    semester = "Unknown"
                    
                for student in metadata:
                    roll_no = student.get('roll_no', 'Unknown')
                    unique_key = f"{roll_no}_{class_id}"
                    if unique_key not in seen_students:
                        registrations.append({
                            'student_name': student.get('name', 'Unknown'),
                            'student_roll': roll_no,
                            'branch': branch,
                            'semester': semester,
                            'class_file': class_id,
                            'source': 'local'
                        })
                        seen_students.add(unique_key)
            except:
                continue
                
    # Sort
    registrations.sort(key=lambda x: x['student_name'])
    
    return render_template('admin/manage_faces.html', all_students=all_students, registrations=registrations)

@bp.route('/faces/register', methods=['POST'])
def register_face():
    collections = get_collections()
    student_id = request.form.get('student_id')
    method = request.form.get('method', 'upload') # upload or camera
    
    if not student_id:
        flash("Student selection required.", "error")
        return redirect(url_for('admin.manage_faces'))
        
    student = collections['students'].find_one({"roll_no": student_id})
    if not student:
        flash("Student not found.", "error")
        return redirect(url_for('admin.manage_faces'))
        
    name = student['name']
    roll_no = student['roll_no']
    semester = student['semester']
    branch = student['branch']
    section = student.get('section', 'A')
    
    face_service = FaceRecognitionService()
    encodings = []
    
    try:
        # Check for duplicate registration (roll_no, branch, semester, section)
        data = get_pickle_from_cloudinary(f"{branch}_{semester}")
        if data:
            for meta in data.get("metadata", []):
                if meta.get("roll_no") == roll_no and str(meta.get("branch")) == str(branch) and str(meta.get("semester")) == str(semester) and str(meta.get("section", "A")) == str(section):
                    flash(f"Face already registered for this student in this class.", "error")
                    return redirect(url_for('admin.manage_faces'))

        # Determine Source
        imgs = []
        if method == 'camera':
            b64_photos = [request.form.get(f'cam_photo{i}') for i in range(1, 4)]
            if not all(b64_photos):
                raise ValueError("Incomplete camera capture. Please capture 3 photos.")
            for idx, b64 in enumerate(b64_photos):
                if ',' in b64:
                    header, encoded = b64.split(',', 1)
                else:
                    encoded = b64
                data_bytes = base64.b64decode(encoded)
                nparr = np.frombuffer(data_bytes, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is None:
                    raise ValueError(f"Failed to process camera image {idx+1}")
                imgs.append(img)
        else:
            photos = [request.files.get(f'photo{i}') for i in range(1, 4)]
            if not all(photos) or not all(p and p.filename for p in photos):
                raise ValueError("Please upload 3 distinct photos.")
            for idx, photo in enumerate(photos):
                filename = secure_filename(f"{roll_no}_{name}_face{idx+1}.jpg")
                save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                photo.save(save_path)
                img = cv2.imread(save_path)
                if img is None:
                    raise ValueError(f"Failed to read image {filename}")
                imgs.append(img)

        # Process Images
        for idx, img in enumerate(imgs):
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            
            # Use proper embedding extraction based on mode
            if face_service.mode == 'remote':
                # Remote mode: get embedding from remote service
                embedding = face_service.get_face_embedding(rgb)
                if embedding is None:
                    raise ValueError(f"No face detected or embedding failed for photo {idx+1}")
                encodings.append(embedding)
            else:
                # Local/Hybrid mode: use local detection
                faces = face_service.get_faces(rgb)
                if not faces:
                    raise ValueError(f"No face detected in photo {idx+1}")
                encodings.append(faces[0].normed_embedding)

        if len(encodings) != 3:
            raise ValueError("Could not extract face data from all 3 photos.")

        avg_encoding = np.mean(encodings, axis=0)

        # 6. Save to Cloudinary directly from memory
        print(f"DEBUG: Attempting to upload to Cloudinary for {branch}_{semester}...")
        
        # Check for existing data
        data = get_pickle_from_cloudinary(f"{branch}_{semester}")
        if not data:
            data = {"encodings": [], "metadata": []}
            
        # Update/Add student data
        filtered = [(e, m) for e, m in zip(data["encodings"], data["metadata"]) if m.get("roll_no") != roll_no]
        data["encodings"] = [e for e, m in filtered]
        data["metadata"] = [m for e, m in filtered]

        new_metadata = {"roll_no": roll_no, "name": name, "semester": int(semester), "branch": branch, "section": section}
        data["encodings"].append(avg_encoding)
        data["metadata"].append(new_metadata)

        cloud_url = upload_pickle_to_cloudinary_from_memory(data, f"{branch}_{semester}")
        if cloud_url:
            print(f"DEBUG: Cloudinary upload successful: {cloud_url}")
        else:
            print("DEBUG: Cloudinary upload failed, continuing with local save.")

        # 7. ALSO SAVE LOCALLY (Crucial for local dev)
        split_dir = current_app.config.get('SPLIT_DIR', 'split_encodings')
        os.makedirs(split_dir, exist_ok=True)
        local_pickle_path = os.path.join(split_dir, f"{branch}_{semester}.pickle")
        
        print(f"DEBUG: Saving local pickle to {local_pickle_path}...")
        try:
            with open(local_pickle_path, 'wb') as f:
                pickle.dump(data, f)
            
            if os.path.exists(local_pickle_path):
                print("DEBUG: Local save VERIFIED.")
                flash(f"Success! Face registered for {name}. You can now take attendance.", "success")
            else:
                print("DEBUG: Local save FAILED.")
                flash("Error: Could not save face data locally.", "error")
        except Exception as e:
            print(f"DEBUG: Error saving local pickle: {e}")
            flash(f"Warning: Face registered on cloud but local save failed: {e}", "warning")
            
        return redirect(url_for('admin.manage_faces'))
    except ValueError as e:
        flash(str(e), "error")
    except Exception as e:
        flash(f"System error: {str(e)}", "error")
        
    return redirect(url_for('admin.manage_faces'))

@bp.route('/faces/delete', methods=['POST'])
def delete_face_data():
    student_roll = request.form.get('student_roll')
    if not student_roll:
         flash("Student Roll No required.", "error")
         return redirect(url_for('admin.manage_faces'))
         
    deleted_count = 0
    
    # 1. Delete from Cloudinary
    all_pickle_files = list_encodings_from_cloudinary()
    
    for pickle_file in all_pickle_files:
        class_id = pickle_file.replace('.pickle', '')
        try:
            data = get_pickle_from_cloudinary(class_id)
            if not data: continue
            
            metadata = data.get('metadata', [])
            encodings = data.get('encodings', [])
            
            # Check if exists
            exists = any(m.get('roll_no') == student_roll for m in metadata)
            if exists:
                filtered = [(e, m) for e, m in zip(encodings, metadata) if m.get("roll_no") != student_roll]
                data["encodings"] = [e for e, m in filtered]
                data["metadata"] = [m for e, m in filtered]
                
                # Sync back to cloud from memory
                upload_pickle_to_cloudinary_from_memory(data, class_id)
                deleted_count += 1
        except:
            continue
    
    # 2. Delete from local split_encodings directory
    split_dir = current_app.config.get('SPLIT_DIR', 'split_encodings')
    if os.path.exists(split_dir):
        local_files = [f for f in os.listdir(split_dir) if f.endswith('.pickle')]
        for pickle_file in local_files:
            class_id = pickle_file.replace('.pickle', '')
            file_path = os.path.join(split_dir, pickle_file)
            try:
                with open(file_path, 'rb') as f:
                    data = pickle.load(f)
                    
                if not data: continue
                
                metadata = data.get('metadata', [])
                encodings = data.get('encodings', [])
                
                # Check if exists
                exists = any(m.get('roll_no') == student_roll for m in metadata)
                if exists:
                    filtered = [(e, m) for e, m in zip(encodings, metadata) if m.get("roll_no") != student_roll]
                    data["encodings"] = [e for e, m in filtered]
                    data["metadata"] = [m for e, m in filtered]
                    
                    # Save back to local file
                    with open(file_path, 'wb') as f:
                        pickle.dump(data, f)
                    deleted_count += 1
            except:
                continue

    if deleted_count > 0:
        flash(f"Deleted face data for {student_roll} from {deleted_count} class(es).", "success")
    else:
        flash("No face data found to delete.", "warning")
        
    return redirect(url_for('admin.manage_faces'))

@bp.route('/faces/cleanup_duplicates', methods=['POST'])
def cleanup_face_duplicates():
    all_pickle_files = list_encodings_from_cloudinary()
    cleaned = 0
    for pickle_file in all_pickle_files:
        class_id = pickle_file.replace('.pickle', '')
        data = get_pickle_from_cloudinary(class_id)
        if not data:
            continue
        seen = set()
        new_encodings = []
        new_metadata = []
        for encoding, meta in zip(data.get('encodings', []), data.get('metadata', [])):
            key = (str(meta.get('roll_no')), str(meta.get('branch')), str(meta.get('semester')), str(meta.get('section', 'A')))
            if key not in seen:
                seen.add(key)
                new_encodings.append(encoding)
                new_metadata.append(meta)
        if len(new_metadata) < len(data.get('metadata', [])):
            data['encodings'] = new_encodings
            data['metadata'] = new_metadata
            upload_pickle_to_cloudinary_from_memory(data, class_id)
            cleaned += 1
    if cleaned > 0:
        flash(f"Cleaned up duplicates in {cleaned} class(es).", "success")
    else:
        flash("No duplicates found.", "info")
    return redirect(url_for('admin.manage_faces'))
