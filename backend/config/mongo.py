import os
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv

load_dotenv()
DB_PASSWORD=os.getenv("DB_PASSWORD")

uri = f"mongodb+srv://ct_dev_app:{DB_PASSWORD}@coursetracker-main.zyd7ln1.mongodb.net/?appName=coursetracker-main"

# Create a new client and connect to the server
client = MongoClient(uri, server_api=ServerApi('1'))


# Send a ping to confirm a successful connection
try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
    db = client["courses"]
    course_collection = db["course_info"]
    
    # Create index on file_hash for fast lookups
    course_collection.create_index("file_hash", unique=True)
    print("MongoDB index created on file_hash")
except Exception as e:
    print(f"MongoDB connection or index creation failed: {e}")
    course_collection = None