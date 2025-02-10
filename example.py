from pocketbase import PocketBase
import os

# Initialize PocketBase client
pb = PocketBase(os.environ["POCKETBASE_URL"])

# Authenticate as admin
pb.admins.auth_with_password(
    os.environ["POCKETBASE_USERNAME"], os.environ["POCKETBASE_PASSWORD"]
)

# Define the collection schema
collection_data = {
    "name": "example_collection",
    "type": "base",
    "fields": [
        {"name": "title", "type": "text", "required": True},
        {
            "name": "category",
            "type": "select",
            "required": True,
            # "options": {
                "maxSelect": 1,
                "values": [
                    "Option 1",
                    "Option 2",
                    "Option 3",
                ],
            # },
        },
    ],
}

# Create the collection
new_collection = pb.collections.create(collection_data)
print("Collection created:", new_collection)
