from pymongo import MongoClient
client = MongoClient("mongodb://localhost:27017/")
db = client["amazondb"]
products_collection = db["products"]
