# PocketBase ORM

A Python ORM (Object-Relational Mapper) for PocketBase that provides Pydantic model integration and automatic schema synchronization.

## Features

- 🚀 Pydantic model integration for data validation and serialization
- 🔄 Automatic schema synchronization with PocketBase collections
- 📦 Support for most PocketBase field types including relations and file uploads
- 🛠️ Simple and intuitive API for CRUD operations

## Installation

```bash
uv install pocketbase-orm
```

## Quick Start

```python
from pocketbase import PocketBase
from pocketbase_orm import PBModel
from pydantic import EmailStr, AnyUrl, Field
from datetime import datetime, timezone
from pocketbase.client import FileUpload

# Define your models
class RelatedModel(PBModel):
    name: str

    class Meta:
        collection_name = "related_models" # Optional

class Example(PBModel):
    text_field: str
    number_field: int
    is_active: bool
    url_field: AnyUrl
    created_at: datetime
    options: list[str]
    email_field: EmailStr | None = None
    related_model: RelatedModel | str = Field(..., description="Related model reference")
    image: FileUpload | str = Field(default=None, description="Image file upload")

# Initialize PocketBase client and bind it to the ORM
client = PocketBase("YOUR_POCKETBASE_URL")
client.admins.auth_with_password("admin@example.com", "password")
PBModel.bind_client(client)

# Sync collection schemas
RelatedModel.sync_collection()
Example.sync_collection()

# Create and save records
related_model = RelatedModel(name="Related Model")
related_model.save()

# Create a new record with file upload
with open("image.png", "rb") as f:
    example = Example(
        text_field="Test with image",
        number_field=123,
        is_active=True,
        email_field="test@example.com",
        url_field="http://example.com",
        created_at=datetime.now(timezone.utc),
        options=["option1", "option2"],
        related_model=related_model.id,
        image=FileUpload(("image.png", f))
    )
    example.save()

# Query records
examples = Example.get_full_list()
single_example = Example.get_one("RECORD_ID")
filtered_example = Example.get_first_list_item(filter='email_field = "test@example.com"')

# Get file contents
image_bytes = example.get_file_contents("image")
```

## Model Definition

Models inherit from `PBModel` and use Pydantic field types:

```python
class MyModel(PBModel):
    name: str
    age: int
    email: EmailStr | None = None
    
    class Meta:
        collection_name = "custom_collection_name"  # Optional
```

The collection name will be automatically derived from the class name (pluralized) if not specified in the Meta class.

## Supported Field Types

- Text: `str`
- Number: `int`, `float`
- Boolean: `bool`
- Email: `EmailStr`
- URL: `AnyUrl`
- DateTime: `datetime`
- JSON: `List`, `Dict`
- File: `FileUpload | str`
- Relation: `Union[RelatedModel, str]`

## API Reference

### Class Methods

- `bind_client(client: PocketBase)`: Bind PocketBase client to the model class
- `sync_collection()`: Create or update the collection schema in PocketBase
- `get_one(id: str, **kwargs) -> T`: Get a single record by ID
- `get_list(*args, **kwargs) -> List[T]`: Get a paginated list of records
- `get_full_list(*args, **kwargs) -> List[T]`: Get all records
- `get_first_list_item(*args, **kwargs) -> T`: Get the first matching record
- `delete(*args, **kwargs)`: Delete a record

### Instance Methods

- `save() -> T`: Create or update the record
- `get_file_contents(field: str) -> bytes`: Get the contents of a file field

## Limitations

- The ORM currently supports basic CRUD operations and schema synchronization
- Complex queries should use the PocketBase client directly
- Relationship handling is limited to single relations
- Indexes must be created manually

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
