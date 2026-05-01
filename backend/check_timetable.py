from pymongo import MongoClient
client = MongoClient('mongodb://127.0.0.1:27017/')
db = client['attendance_db']
branch = 'CSE'
semester = 1
section = 'A'

print(f"Checking timetable for {branch} sem {semester} sec {section}:")
timetable = list(db.timetable.find({"branch": branch, "semester": semester, "section": section}))
print(f"Found {len(timetable)} entries.")
for entry in timetable:
    print(f"{entry['day']} {entry['start_time']} - {entry['end_time']}: {entry['subject']}")
