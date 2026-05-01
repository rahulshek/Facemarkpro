from pymongo import MongoClient
client = MongoClient('mongodb://127.0.0.1:27017/')
db = client['attendance_db']
print("STUDENTS:")
for s in db.students.find({}, {"_id": 0}):
    print(s)
print("\nTIMETABLE:")
for t in db.timetable.find({}, {"_id": 0}):
    print(t)
