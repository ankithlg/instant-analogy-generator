from database import users_collection
import asyncio

async def test_connection():
    # Try inserting a test user
    test_user = {"username": "test", "email": "test@example.com", "hashed_password": "dummy"}
    result = await users_collection.insert_one(test_user)
    print("Inserted document ID:", result.inserted_id)

    # Fetch the user back
    user = await users_collection.find_one({"email": "test@example.com"})
    print("Fetched user:", user)

    # Delete test user
    await users_collection.delete_one({"email": "test@example.com"})

asyncio.run(test_connection())
