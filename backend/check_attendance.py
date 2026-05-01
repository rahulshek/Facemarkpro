from pymongo import MongoClient
client = MongoClient('mongodb://127.0.0.1:27017/')
db = client['attendance_db']
roll_no = '24CSE01'

print(f"Checking attendance for {roll_no}:")
total = db.attendance.count_documents({"student.roll_no": roll_no})
present = db.attendance.count_documents({"student.roll_no": roll_no, "student.status": "Present"})
print(f"Total: {total}, Present: {present}")

print("\nSample records:")
for doc in db.attendance.find({"student.roll_no": roll_no}).limit(5):
    print(doc)
