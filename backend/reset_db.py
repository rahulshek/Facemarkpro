import bcrypt
from pymongo import MongoClient
from datetime import datetime

# Connection details
MONGO_URI = 'mongodb://127.0.0.1:27017/'
DB_NAME = 'attendance_db'

def get_db():
    client = MongoClient(MONGO_URI)
    return client[DB_NAME]

def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

def reset_and_setup():
    db = get_db()
    
    # Collections to clear
    collections_to_clear = [
        'faculty', 'students', 'attendance', 
        'academic_branches', 'academic_classes', 'academic_classrooms', 
        'academic_subjects', 'academic_assignments', 'timetable'
    ]
    
    print("Clearing existing dummy data...")
    for coll in collections_to_clear:
        db[coll].delete_many({})
        print(f" - Cleared {coll}")

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    date_str = datetime.now().strftime('%Y-%m-%d')
    today_day = datetime.now().strftime('%A')

    # 1. Add Branch
    db['academic_branches'].insert_one({
        'code': 'CSE',
        'name': 'Computer Science Engineering',
        'active': True,
        'created_at': now_str
    })

    # 2. Add Class
    db['academic_classes'].insert_one({
        'branch': 'CSE',
        'semester': 1,
        'section': 'A',
        'label': 'CSE / 1 / A',
        'active': True,
        'created_at': now_str
    })

    # 3. Add Classroom
    db['academic_classrooms'].insert_one({
        'name': 'Room 101',
        'type': 'Classroom',
        'capacity': 60,
        'active': True
    })

    # 4. Add Subjects
    subjects = [
        {'code': 'CS101', 'name': 'Introduction to Programming', 'branch': 'CSE', 'semester': 1, 'type': 'theory', 'active': True},
        {'code': 'CS102', 'name': 'Digital Logic', 'branch': 'CSE', 'semester': 1, 'type': 'theory', 'active': True}
    ]
    db['academic_subjects'].insert_many(subjects)

    # 5. Add Admins (super_admin)
    admins = [
        ('rahul@facemarkpro.com', 'Rahul Admin'),
        ('umang@facemarkpro.com', 'Umang Admin'),
        ('malhar@facemarkpro.com', 'Malhar Admin'),
        ('harsh@facemarkpro.com', 'Harsh Admin')
    ]
    for email, name in admins:
        db['faculty'].insert_one({
            'email': email,
            'name': name,
            'password': hash_password('123456'),
            'role': 'super_admin',
            'department': 'Administration',
            'faculty_id': f'ADM_{email.split("@")[0].upper()}',
            'active': True,
            'joined_date': date_str
        })
    print(f"Added {len(admins)} Admins")

    # 6. Add Faculty (teacher)
    faculties = [
        ('smit@facemarkpro.com', 'Smit Faculty'),
        ('dev@facemarkpro.com', 'Dev Faculty')
    ]
    for email, name in faculties:
        db['faculty'].insert_one({
            'email': email,
            'name': name,
            'password': hash_password('123456'),
            'role': 'teacher',
            'department': 'CSE',
            'faculty_id': f'FAC_{email.split("@")[0].upper()}',
            'active': True,
            'joined_date': date_str
        })
    print(f"Added {len(faculties)} Faculty")

    # 7. Add Students
    students = [
        ('kuldeep@facemarkpro.com', 'Kuldeep Student', '24CSE01'),
        ('kalp@facemarkpro.com', 'Kalp Student', '24CSE02'),
        ('vishal@facemarkpro.com', 'Vishal Student', '24CSE03')
    ]
    for email, name, roll in students:
        db['students'].insert_one({
            'email': email,
            'name': name,
            'roll_no': roll,
            'password': hash_password('123456'),
            'branch': 'CSE',
            'semester': 1,
            'section': 'A',
            'active': True,
            'joined_date': date_str
        })
    print(f"Added {len(students)} Students")

    # 8. Create Assignments (Linking Faculty to Class)
    # Assign Smit to CS101 and Dev to CS102 for CSE/1/A
    assignments = [
        {
            'faculty_email': 'smit@facemarkpro.com',
            'faculty_name': 'Smit Faculty',
            'branch': 'CSE',
            'semester': 1,
            'section': 'A',
            'subject_code': 'CS101',
            'subject_name': 'Introduction to Programming',
            'classroom': 'Room 101',
            'active': True,
            'updated_at': now_str
        },
        {
            'faculty_email': 'dev@facemarkpro.com',
            'faculty_name': 'Dev Faculty',
            'branch': 'CSE',
            'semester': 1,
            'section': 'A',
            'subject_code': 'CS102',
            'subject_name': 'Digital Logic',
            'classroom': 'Room 101',
            'active': True,
            'updated_at': now_str
        }
    ]
    db['academic_assignments'].insert_many(assignments)

    # 9. Update Timetable so it shows up on dashboard TODAY
    timetable_entries = [
        {
            'day': today_day,
            'start_time': '09:00',
            'end_time': '10:00',
            'subject': 'Introduction to Programming',
            'branch': 'CSE',
            'semester': 1,
            'section': 'A',
            'classroom': 'Room 101',
            'faculty_name': 'Smit Faculty',
            'faculty_email': 'smit@facemarkpro.com'
        },
        {
            'day': today_day,
            'start_time': '10:00',
            'end_time': '11:00',
            'subject': 'Digital Logic',
            'branch': 'CSE',
            'semester': 1,
            'section': 'A',
            'classroom': 'Room 101',
            'faculty_name': 'Dev Faculty',
            'faculty_email': 'dev@facemarkpro.com'
        }
    ]
    db['timetable'].insert_many(timetable_entries)
    print(f"Created timetable entries for {today_day}")

    print("\nDatabase Reset and Setup Complete! ✅")

if __name__ == '__main__':
    reset_and_setup()
