import bcrypt
from pymongo import MongoClient
import os
from datetime import datetime

# Connection details
MONGO_URI = 'mongodb://127.0.0.1:27017/'
DB_NAME = 'attendance_db'

def get_db():
    client = MongoClient(MONGO_URI)
    return client[DB_NAME]

def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

def add_users():
    db = get_db()
    faculty_col = db['faculty']
    students_col = db['students']

    # Admins
    admins = [
        ('rahul@facemarkpro.com', 'Rahul Admin'),
        ('umang@facemarkpro.com', 'Umang Admin'),
        ('malhar@facemarkpro.com', 'Malhar Admin'),
        ('harsh@facemarkpro.com', 'Harsh Admin')
    ]

    for email, name in admins:
        user = faculty_col.find_one({'email': email})
        if not user:
            faculty_col.insert_one({
                'email': email,
                'name': name,
                'password': hash_password('123456'),
                'role': 'super_admin',
                'department': 'Administration',
                'faculty_id': f'ADM_{email.split("@")[0].upper()}',
                'joined_date': datetime.now().strftime('%Y-%m-%d'),
                'active': True
            })
            print(f'Added Admin: {email}')
        else:
            print(f'Admin {email} already exists.')

    # Faculty
    faculties = [
        ('smit@facemarkpro.com', 'Smit Faculty'),
        ('dev@facemarkpro.com', 'Dev Faculty')
    ]

    for email, name in faculties:
        user = faculty_col.find_one({'email': email})
        if not user:
            faculty_col.insert_one({
                'email': email,
                'name': name,
                'password': hash_password('123456'),
                'role': 'teacher',
                'department': 'Engineering',
                'faculty_id': f'FAC_{email.split("@")[0].upper()}',
                'joined_date': datetime.now().strftime('%Y-%m-%d'),
                'active': True
            })
            print(f'Added Faculty: {email}')
        else:
            print(f'Faculty {email} already exists.')

    # Students
    students = [
        ('kuldeep@facemarkpro.com', 'Kuldeep Student', '24CSE01')
    ]

    for email, name, roll_no in students:
        user = students_col.find_one({'roll_no': roll_no}) # Using roll_no as primary identifier for students usually
        if not user:
            students_col.insert_one({
                'email': email,
                'name': name,
                'roll_no': roll_no,
                'password': hash_password('123456'),
                'branch': 'CSE',
                'semester': 1,
                'section': 'A',
                'joined_date': datetime.now().strftime('%Y-%m-%d'),
                'active': True
            })
            print(f'Added Student: {email} (Roll: {roll_no})')
        else:
            print(f'Student {roll_no} already exists.')

if __name__ == '__main__':
    add_users()
