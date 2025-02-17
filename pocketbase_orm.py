import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, TypeVar, Union

import httpx
from pocketbase import PocketBase
from pocketbase.client import FileUpload
from pydantic import AnyUrl, BaseModel, EmailStr, Field

__version__ = "0.14.0"

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="PBModel")


def _pluralize(singular: str) -> str:
    """Simple English pluralization."""
    if singular.endswith("y"):
        return singular[:-1] + "ies"
    elif singular.endswith(("s", "sh", "ch", "x", "z")):
        return singular + "es"
    else:
        return singular + "s"


class PBModel(BaseModel):
    """
    Base model class for all PocketBase models.
    Provides methods for schema synchronization and querying the PocketBase database.
    """

    id: str | None = None
    created: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        str_strip_whitespace = True
        str_min_length = 1
        arbitrary_types_allowed = True

    def __init_subclass__(cls, *, collection: str | None = None, **kwargs):
        """
        Initialize subclass with optional collection name.
        If collection name is not provided, it will be derived from the class name.
        """
        super().__init_subclass__(**kwargs)
        if collection is not None:
            cls._collection_name = collection
        else:
            cls._collection_name = _pluralize(cls.__name__.lower())

    @classmethod
    def bind_client(cls, client: PocketBase):
        """
        Bind the PocketBase client to the model class.
        """
        cls._pb_client = client

    @classmethod
    def init_client(
        cls,
        url: str,
        admin_email: str | None = None,
        admin_password: str | None = None,
    ) -> PocketBase:
        """
        Initialize a PocketBase client and bind it to the model class.

        Args:
            url: The PocketBase server URL
            admin_email: Optional admin email for authentication
            admin_password: Optional admin password for authentication

        Returns:
            The initialized PocketBase client

        Example:
            client = PBModel.init_client("http://127.0.0.1:8090", "admin@example.com", "password")
        """
        client = PocketBase(url)
        if admin_email and admin_password:
            client.admins.auth_with_password(admin_email, admin_password)
        cls.bind_client(client)
        return client

    @classmethod
    def get_collection_name(cls) -> str:
        """
        Get the collection name for the model.
        Returns the collection name specified during class creation or derived from class name.
        """
        return cls._collection_name

    @classmethod
    def get_collection(cls):
        """
        Returns the collection instance for the model.
        """
        if not hasattr(cls, "_pb_client") or cls._pb_client is None:
            raise RuntimeError(
                "PocketBase client not bound. Call PBModel.bind_client() first."
            )
        return cls._pb_client.collection(cls.get_collection_name())

    @classmethod
    def delete_by_id(cls, id: str, *args, **kwargs):
        """Delete a record from the collection by ID."""
        return cls.get_collection().delete(id, *args, **kwargs)

    def delete(self, id=None, *args, **kwargs):
        """Delete this record instance from the collection."""
        return self.get_collection().delete(id or self.id, *args, **kwargs)

    @classmethod
    def delete_collection(cls):
        """
        Delete the entire collection from PocketBase.

        Raises:
            RuntimeError: If PocketBase client is not bound
            Exception: If deletion fails or collection doesn't exist
        """
        if not hasattr(cls, "_pb_client") or cls._pb_client is None:
            raise RuntimeError(
                "PocketBase client not bound. Call PBModel.bind_client() first."
            )

        collection_name = cls.get_collection_name()
        try:
            # Get collection ID first
            collection = cls._pb_client.collections.get_one(collection_name)
            # Delete the collection
            cls._pb_client.collections.delete(collection.id)
            logger.debug(f"Collection {collection_name} deleted successfully.")
        except Exception as e:
            if "404" in str(e):
                logger.warning(f"Collection {collection_name} does not exist.")
            else:
                logger.error(f"Error deleting collection {collection_name}: {e}")
                raise

    @classmethod
    def _process_record_data(cls, record_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process record data before model validation.
        Handles special cases like file fields.
        """
        processed_data = record_data.copy()

        # Get field types from annotations
        for field_name, field_type in cls.__annotations__.items():
            if field_name not in processed_data:
                continue

            # Check if field is a file type (in a Union)
            is_file_field = False
            if hasattr(field_type, "__origin__") and field_type.__origin__ is Union:
                is_file_field = FileUpload in field_type.__args__
            else:
                is_file_field = field_type is FileUpload

            # Handle file fields - convert empty strings to None
            if is_file_field and processed_data[field_name] == "":
                processed_data[field_name] = None

        return processed_data

    @classmethod
    def get_one(cls, id: str, **kwargs) -> T:
        """Get a single record from the collection and convert to model instance."""
        record = cls.get_collection().get_one(id, kwargs)
        processed_data = cls._process_record_data(record.__dict__)
        return cls.model_validate(processed_data)

    @classmethod
    def get_list(cls, page: int = 1, per_page: int = 10, **kwargs) -> list[T]:
        """Get a list of records from the collection and convert to model instances."""
        result = cls.get_collection().get_list(page, per_page, kwargs)
        items = [
            cls.model_validate(cls._process_record_data(record.__dict__))
            for record in result.items
        ]
        return items

    @classmethod
    def get_full_list(cls, **kwargs) -> list[T]:
        """Get a full list of records and convert to model instances."""
        records = cls.get_collection().get_full_list(**kwargs)
        return [
            cls.model_validate(cls._process_record_data(record.__dict__))
            for record in records
        ]

    @classmethod
    def get_first_list_item(cls, query, **kwargs) -> T:
        """Get the first matching record and convert to model instance."""
        record = cls.get_collection().get_first_list_item(query, kwargs)
        processed_data = cls._process_record_data(record.__dict__)
        return cls.model_validate(processed_data)

    @classmethod
    def sync_collection(cls):
        """
        Sync the collection schema with PocketBase. Will create or update the collection.
        """
        collection_name = cls.get_collection_name()

        try:
            existing_collection = cls._pb_client.collections.get_one(collection_name)
            logger.debug(f"Collection {collection_name} exists. Updating schema...")
            cls._update_collection(existing_collection)
        except Exception as e:
            if "404" in str(e):  # Only create if collection doesn't exist
                logger.debug(
                    f"Collection {collection_name} does not exist. Creating collection..."
                )
                cls._create_collection()
            else:
                logger.error(f"Error syncing collection: {e}")
                raise

    @classmethod
    def _create_collection(cls):
        """
        Create the collection schema in PocketBase.
        """
        fields = cls._generate_fields()
        collection_name = cls.get_collection_name()

        collection_payload = {
            "name": collection_name,
            "type": "base",
            "fields": fields,
        }

        logger.debug(f"Creating collection with payload: {collection_payload}")

        try:
            response = cls._pb_client.collections.create(collection_payload)
            logger.debug(f"Collection {collection_name} created successfully.")
            return response
        except Exception as e:
            logger.error(f"Error creating collection: {e}")
            # Try to get more details about the error
            if hasattr(e, "response") and hasattr(e.response, "json"):
                try:
                    error_details = e.response.json()
                    logger.error(f"Error details: {error_details}")
                except:
                    pass
            raise

    @classmethod
    def _update_collection(cls, existing_collection):
        """
        Update the collection schema in PocketBase.
        """
        # Get the schema from the existing collection
        current_fields = {field.name: field for field in existing_collection.schema}
        new_fields = cls._generate_fields()

        # Preserve existing fields and add new ones
        final_fields = []
        for field in existing_collection.schema:
            field_dict = {
                "name": field.name,
                "type": field.type,
                "required": field.required,
                "system": field.system,
            }
            if hasattr(field, "options") and field.options:
                field_dict["options"] = field.options
            final_fields.append(field_dict)

        # Add new fields that don't exist yet
        for new_field in new_fields:
            if new_field["name"] not in current_fields:
                final_fields.append(new_field)

        try:
            cls._pb_client.collections.update(
                existing_collection.id,
                {
                    "name": existing_collection.name,
                    "schema": final_fields,
                },
            )
            logger.debug(f"Collection {existing_collection.name} updated successfully.")
        except Exception as e:
            logger.error(f"Error updating collection: {e}")
            raise

    @classmethod
    def _generate_fields(cls) -> list[Dict[str, Any]]:
        """
        Generate the field definitions for the collection based on the Pydantic model.
        """
        fields = []
        model_fields = cls.model_fields

        logger.debug(f"Generating fields for {cls.__name__}")

        # Add fields for created and updated
        fields.extend(
            [
                {
                    "hidden": False,
                    "name": "created",
                    "onCreate": True,
                    "onUpdate": False,
                    "presentable": False,
                    "system": False,
                    "type": "autodate",
                },
                {
                    "hidden": False,
                    "name": "updated",
                    "onCreate": True,
                    "onUpdate": True,
                    "presentable": False,
                    "system": False,
                    "type": "autodate",
                },
            ]
        )

        for name, field in cls.__annotations__.items():
            if name in ["id", "created", "updated"]:  # Skip base model fields
                continue

            field_def = {"name": name, "type": cls._get_field_type(field)}
            logger.debug(f"Processing field {name} with type {field_def['type']}")

            # Get field info from Pydantic model
            field_info = model_fields[name]
            field_def["required"] = field_info.is_required()

            # Configure enum select field options if applicable
            let_enum = None
            if hasattr(field, "__origin__") and field.__origin__ is Union:
                for arg in field.__args__:
                    if isinstance(arg, type) and issubclass(arg, Enum):
                        let_enum = arg
                        break
            elif isinstance(field, type) and issubclass(field, Enum):
                let_enum = field

            if let_enum is not None and field_def["type"] == "select":
                field_def.update(
                    {
                        "maxSelect": 1,
                        "values": [e.value for e in let_enum],
                    }
                )
                logger.debug(f"Configured enum select field {name} with: {field_def}")

            # Add additional configuration for relation fields
            if field_def["type"] == "relation":
                logger.debug(f"Configuring relation field {name}")
                # Find the related model in Union types
                related_model = None
                if hasattr(field, "__origin__") and field.__origin__ is Union:
                    logger.debug(f"Field {name} args: {field.__args__}")
                    for arg in field.__args__:
                        if hasattr(arg, "__origin__"):
                            continue
                        if arg == str:
                            continue
                        related_model = arg
                        logger.debug(f"Found related model for {name}: {related_model}")
                if related_model:
                    try:
                        logger.debug(
                            f"Looking up collection for {related_model.get_collection_name()}"
                        )
                        collection = cls._pb_client.collections.get_one(
                            related_model.get_collection_name()
                        )
                        logger.debug(f"Found collection for {name}: {collection.id}")

                        field_def.update(
                            {
                                "name": name,
                                "type": "relation",
                                "system": False,
                                "required": field_info.is_required(),
                                "presentable": False,
                                "cascadeDelete": False,
                                "minSelect": 0,
                                "maxSelect": 1,
                                "collectionId": collection.id,  # This must be present and non-empty
                            }
                        )

                        logger.debug(f"Field definition for {name}: {field_def}")
                    except Exception as e:
                        logger.error(
                            f"Error getting collection ID for {related_model.Meta.collection_name}: {e}",
                            exc_info=True,
                        )
                        raise
                else:
                    logger.error(f"No valid related model found for field {name}")
                    raise ValueError(f"Invalid relation configuration for field {name}")

            fields.append(field_def)
            logger.debug(f"Added field definition: {field_def}")

        logger.debug(f"Final fields configuration: {fields}")
        return fields

    @staticmethod
    def _is_enum_type(field_type: Any) -> bool:
        """Check if a type is an Enum subclass."""
        return isinstance(field_type, type) and issubclass(field_type, Enum)

    @staticmethod
    def _is_pbmodel_type(field_type: Any) -> bool:
        """Check if a type is a PBModel subclass."""
        return isinstance(field_type, type) and issubclass(field_type, PBModel)

    @staticmethod
    def _get_field_type(pydantic_field: Any) -> str:
        """
        Convert the Pydantic field type into a PocketBase field type.
        """
        # Get all possible types to check
        types_to_check = []
        if hasattr(pydantic_field, "__origin__"):
            if pydantic_field.__origin__ is Union:
                types_to_check.extend(pydantic_field.__args__)
            elif pydantic_field.__origin__ is list:
                return "json"
        elif hasattr(pydantic_field, "__or__") and hasattr(pydantic_field, "__args__"):
            types_to_check.extend(pydantic_field.__args__)
        else:
            types_to_check.append(pydantic_field)

        # Check all types in priority order
        for field_type in types_to_check:
            # Special types
            if PBModel._is_enum_type(field_type):
                return "select"
            if PBModel._is_pbmodel_type(field_type):
                return "relation"
            if field_type == FileUpload:
                return "file"

            # Basic types
            if field_type == str:
                return "text"
            if field_type in (int, float):
                return "number"
            if field_type == bool:
                return "bool"
            if field_type == EmailStr:
                return "email"
            if field_type == AnyUrl:
                return "url"
            if field_type == datetime:
                return "date"
            if isinstance(field_type, (list, dict)):
                return "json"

        # Default to json for complex types
        return "json"

    def save(self) -> T:
        """
        Save the model instance to PocketBase.
        """
        client = self.get_collection().client
        collection_name = self.get_collection_name()

        # Prepare data for saving - handle file uploads specially
        data = {}
        for field_name, field_info in self.model_fields.items():
            if field_name in ("created", "updated"):
                continue

            field_value = getattr(self, field_name)
            if field_value is None:
                continue

            if isinstance(field_value, FileUpload):
                # Keep FileUpload objects as-is
                data[field_name] = field_value
            else:
                # For non-file fields, use model_dump to handle serialization
                try:
                    data[field_name] = self.model_dump(
                        include={field_name}, mode="json"
                    )[field_name]
                except Exception as e:
                    logger.warning(f"Error serializing field {field_name}: {e}")
                    data[field_name] = field_value

        if hasattr(self, "id") and self.id:
            result = client.collection(collection_name).update(self.id, data)
            logger.debug(f"Updated record with ID: {self.id}")
        else:
            result = client.collection(collection_name).create(data)
            self.id = result.id
            logger.debug(f"Created new record with ID: {self.id}")

        # Update instance with response data from PocketBase
        self.created = result.created
        self.updated = result.updated

        return self

    def get_file_contents(self, field: str) -> bytes:
        """
        Get the contents of a file field using httpx.

        Args:
            field: Name of the file field

        Returns:
            bytes: The file contents

        Raises:
            ValueError: If the field doesn't exist or isn't a file field
            RuntimeError: If there's an error fetching the file
        """
        # Get the field value
        field_value = getattr(self, field)
        if not field_value:
            raise ValueError(f"No file exists in field '{field}'")

        # If it's a FileUpload object, return the file contents directly
        if isinstance(field_value, FileUpload):
            # Get the file object from the FileUpload
            # FileUpload.files is a tuple where the second element is the file
            _, file_obj = field_value.files[0]
            # Seek to start in case file was already read
            file_obj.seek(0)
            return file_obj.read()

        # Otherwise, treat it as a filename and fetch from PocketBase
        collection = self.get_collection()
        client = collection.client
        collection_name = self.get_collection_name()

        # Construct the PocketBase file URL
        file_url = (
            f"{client.base_url}/api/files/{collection_name}/{self.id}/{field_value}"
        )

        try:
            response = httpx.get(file_url)
            response.raise_for_status()
            return response.content
        except Exception as e:
            raise RuntimeError(f"Error fetching file contents: {e}")


class User(PBModel, collection="users"):
    """Model class for PocketBase's built-in users collection."""

    email: EmailStr
    password: str | None = None  # Only used when creating/updating
    passwordConfirm: str | None = None  # Required when creating/updating password
    emailVisibility: bool = False
    verified: bool = False
    name: str | None = None
    avatar: Union[FileUpload, str, None] = None

    @classmethod
    def _create_collection(cls):
        """Override to prevent creation of system collection."""
        raise RuntimeError(
            "Cannot create or modify the users collection as it is a system collection."
        )

    @classmethod
    def _update_collection(cls, existing_collection):
        """Override to prevent modification of system collection."""
        raise RuntimeError(
            "Cannot create or modify the users collection as it is a system collection."
        )
