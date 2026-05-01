from pymongo import MongoClient

c = MongoClient('mongodb://127.0.0.1:27017/')
db = c['attendance_db']
db['faculty'].update_one({'email': 'faculty1@example.com'}, {'$set': {'role': 'super_admin'}})
print('Updated faculty1 to super_admin')
