import logging
from typing import List, TypeVar, Dict, Any, Union
from pydantic import BaseModel, EmailStr, AnyUrl, Field, field_validator
from pocketbase import PocketBase
from datetime import datetime, timezone

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

T = TypeVar("T", bound="PBModel")


class PBModel(BaseModel):
    """
    Base model class for all PocketBase models.
    Provides methods for schema synchronization and querying the PocketBase database.
    """

    id: str = Field(default="")
    created: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        str_strip_whitespace = True
        str_min_length = 1
        arbitrary_types_allowed = True

    @classmethod
    def bind_client(cls, client: PocketBase):
        """
        Bind the PocketBase client to the model class.
        """
        cls._pb_client = client

    @classmethod
    def collection(cls):
        """
        Returns the collection instance for the model.
        """
        if not hasattr(cls, "_pb_client") or cls._pb_client is None:
            raise RuntimeError(
                "PocketBase client not bound. Call PBModel.bind_client() first."
            )
        return cls._pb_client.collection(cls.Meta.collection_name)

    @classmethod
    def sync_collection(cls):
        """
        Sync the collection schema with PocketBase. Will create or update the collection.
        """
        # Check if collection already exists
        collection_name = cls.Meta.collection_name
        try:
            existing_collection = cls._pb_client.collections.get_one(collection_name)
            logger.info(f"Collection {collection_name} exists. Updating schema...")
            cls._update_collection(existing_collection)
        except Exception as e:
            if "404" in str(e):  # Only create if collection doesn't exist
                logger.info(
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
        indexes = cls._generate_indexes()

        collection_payload = {
            "name": cls.Meta.collection_name,
            "type": "base",
            "fields": fields,
            "indexes": indexes,
        }

        logger.info(f"Creating collection with payload: {collection_payload}")

        try:
            response = cls._pb_client.collections.create(collection_payload)
            logger.info(f"Collection {cls.Meta.collection_name} created successfully.")
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

        indexes = cls._generate_indexes()

        try:
            cls._pb_client.collections.update(
                existing_collection.id,
                {
                    "name": existing_collection.name,
                    "schema": final_fields,
                    "indexes": indexes,
                },
            )
            logger.info(f"Collection {cls.Meta.collection_name} updated successfully.")
        except Exception as e:
            logger.error(f"Error updating collection: {e}")
            raise

    @classmethod
    def _generate_fields(cls) -> List[Dict[str, Any]]:
        """
        Generate the field definitions for the collection based on the Pydantic model.
        """
        fields = []
        model_fields = cls.model_fields

        logger.info(f"Generating fields for {cls.__name__}")

        for name, field in cls.__annotations__.items():
            if name in ["id", "created", "updated"]:  # Skip base model fields
                continue

            field_def = {"name": name, "type": cls._get_field_type(field)}
            logger.info(f"Processing field {name} with type {field_def['type']}")

            # Get field info from Pydantic model
            field_info = model_fields[name]
            field_def["required"] = field_info.is_required()

            # Add additional configuration for relation fields
            if field_def["type"] == "relation":
                logger.info(f"Configuring relation field {name}")
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
                        logger.info(f"Found related model for {name}: {related_model}")

                if related_model and hasattr(related_model, "Meta"):
                    try:
                        logger.info(
                            f"Looking up collection for {related_model.Meta.collection_name}"
                        )
                        collection = cls._pb_client.collections.get_one(
                            related_model.Meta.collection_name
                        )
                        logger.info(f"Found collection for {name}: {collection.id}")

                        # Match the exact RelationField structure from Go
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

                        logger.info(f"Field definition for {name}: {field_def}")
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

        logger.info(f"Final fields configuration: {fields}")
        return fields

    @classmethod
    def _generate_indexes(cls) -> List[str]:
        """
        Generate indexes from the Meta class if defined.
        """
        indexes = []
        if hasattr(cls.Meta, "indexes"):
            for index in cls.Meta.indexes:
                if isinstance(index, tuple):
                    index_fields = ", ".join(index)
                    indexes.append(
                        f"CREATE INDEX idx_{cls.Meta.collection_name}_{index_fields} ON {cls.Meta.collection_name} ({index_fields})"
                    )
                elif isinstance(index, dict):
                    index_fields = ", ".join(index["fields"])
                    unique = "UNIQUE " if index.get("unique", False) else ""
                    indexes.append(
                        f"CREATE {unique}INDEX idx_{cls.Meta.collection_name}_{index_fields} ON {cls.Meta.collection_name} ({index_fields})"
                    )
        return indexes

    @staticmethod
    def _get_field_type(pydantic_field: Any) -> str:
        """
        Convert the Pydantic field type into a PocketBase field type.
        """
        # Handle Union types (typically used for relations)
        if hasattr(pydantic_field, "__origin__") and pydantic_field.__origin__ is Union:
            # If one of the types is str, it's likely a relation field
            if str in pydantic_field.__args__:
                return "relation"
            # For other Union types, default to json
            return "json"

        if hasattr(pydantic_field, "__origin__") and pydantic_field.__origin__ is list:
            return "json"

        if pydantic_field == str:
            return "text"
        elif pydantic_field == int or pydantic_field == float:
            return "number"
        elif pydantic_field == bool:
            return "bool"
        elif pydantic_field == EmailStr:
            return "email"
        elif pydantic_field == AnyUrl:
            return "url"
        elif pydantic_field == datetime:
            return "date"
        elif isinstance(pydantic_field, list):
            return "json"
        elif isinstance(pydantic_field, dict):
            return "json"
        else:
            # Default to json for complex types
            return "json"

    def save(self) -> "PBModel":
        """
        Save the model instance to PocketBase.
        If the model has an ID, it will update the existing record.
        If not, it will create a new record.
        Returns the updated model instance.
        """
        client = self.collection().client
        collection_name = self.Meta.collection_name

        # Prepare data for saving - use model_dump with mode='json' to handle special types
        data = self.model_dump(exclude={"created", "updated"}, mode="json")

        if hasattr(self, "id") and self.id:
            # Update existing record
            result = client.collection(collection_name).update(self.id, data)
            logger.info(f"Updated record with ID: {self.id}")
        else:
            # Create new record
            result = client.collection(collection_name).create(data)
            self.id = result.id
            logger.info(f"Created new record with ID: {self.id}")

        # Update instance with response data
        self.created = (
            datetime.fromisoformat(result.created)
            if result.created and result.created.strip()
            else datetime.now(timezone.utc)
        )
        self.updated = (
            datetime.fromisoformat(result.updated)
            if result.updated and result.updated.strip()
            else datetime.now(timezone.utc)
        )

        return self


class RelatedModel(PBModel):
    name: str

    class Meta:
        collection_name = "related_models"


class Example(PBModel):
    text_field: str
    number_field: int
    is_active: bool
    email_field: EmailStr
    url_field: AnyUrl
    created_at: datetime
    options: List[str]
    file_field: str
    related_model: Union[RelatedModel, str] = Field(
        ..., description="Related model reference"
    )

    class Meta:
        collection_name = "examples"
        # indexes = [
        #     ("text_field",),  # index on text_field
        #     (
        #         "number_field",
        #         "is_active",
        #     ),  # composite index on number_field + is_active
        # ]

    @field_validator("related_model", mode="before")
    def set_related_model(cls, v):
        if isinstance(v, str):
            return v  # If it's already an ID, keep it.
        if isinstance(v, PBModel):
            return v.id  # If it's a model instance, return its ID.
        return v  # In case it's None


# Example usage:
if __name__ == "__main__":
    import os

    username = os.getenv("POCKETBASE_USERNAME")
    password = os.getenv("POCKETBASE_PASSWORD")
    # Initialize PocketBase client and bind it to the ORM
    client = PocketBase("https://pocketbase.knowsuchagency.com")
    client.admins.auth_with_password(username, password)  # Auth as admin
    PBModel.bind_client(client)

    # Sync collections
    RelatedModel.sync_collection()  # Sync the RelatedModel collection schema
    Example.sync_collection()  # Sync the Example collection schema

    related_model = RelatedModel(name="Related Model")
    related_model.save()  # Now using the save() method

    # Create a new record
    example = Example(
        text_field="Test",
        number_field=123,
        is_active=True,
        email_field="test@example.com",
        url_field="http://example.com",
        created_at=datetime.now(timezone.utc),
        options=["option1", "option2"],
        file_field="file1.txt",
        related_model=related_model.id,  # Now using the id from the saved related_model
    )

    # Create the record in the database using the new save() method
    example.save()
    print(f"Created record with ID: {example.id}")
