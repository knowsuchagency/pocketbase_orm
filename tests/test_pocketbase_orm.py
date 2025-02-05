import os
from typing import Union
from pydantic import AnyUrl, EmailStr, Field, field_validator
import pytest
from datetime import datetime, timezone
from pocketbase import PocketBase
from pocketbase.client import FileUpload
from pocketbase_orm import PBModel, User


class RelatedModel(PBModel):
    name: str

    class Meta:
        collection_name = "related_models"


class Example(PBModel):
    text_field: str
    number_field: int
    is_active: bool
    url_field: AnyUrl
    created_at: datetime
    options: list[str]
    email_field: EmailStr | None = None
    related_model: Union[RelatedModel, str] = Field(
        ..., description="Related model reference"
    )
    image: Union[FileUpload, str, None] = Field(
        default=None, description="Image file upload"
    )

    @field_validator("related_model", mode="before")
    def set_related_model(cls, v):
        if isinstance(v, str):
            return v  # If it's already an ID, keep it
        if isinstance(v, PBModel):
            return v.id  # If it's a model instance, return its ID
        return v  # In case it's None

    @field_validator("image", mode="before")
    def validate_image(cls, v):
        if v is None:
            return v  # Allow None values
        if isinstance(v, str):
            return v  # Keep string URLs as-is
        if isinstance(v, FileUpload):
            return v  # Keep FileUpload objects as-is
        return v  # In case it's None


@pytest.fixture
def pb_client():
    """Fixture to provide an authenticated PocketBase client."""
    username = os.getenv("POCKETBASE_USERNAME")
    password = os.getenv("POCKETBASE_PASSWORD")
    url = os.getenv("POCKETBASE_URL")

    if not all([username, password, url]):
        pytest.skip("PocketBase credentials not set in environment")

    client = PocketBase(url)
    client.admins.auth_with_password(username, password)
    return client


@pytest.fixture
def setup_models(pb_client):
    """Fixture to bind the client and sync collections."""
    PBModel.bind_client(pb_client)
    RelatedModel.sync_collection()
    Example.sync_collection()


@pytest.fixture
def related_model(setup_models):
    """Fixture to create and return a test RelatedModel instance."""
    model = RelatedModel(name="Test Related Model")
    model.save()
    yield model
    # Cleanup after test
    try:
        RelatedModel.delete(model.id)
    except Exception:
        pass


def test_create_example_with_file(setup_models, related_model):
    """Test creating an Example record with a file upload."""
    with open("static/image.png", "rb") as f:
        example = Example(
            text_field="Test with image",
            number_field=123,
            is_active=True,
            email_field="test@example.com",
            url_field="http://example.com",
            created_at=datetime.now(timezone.utc),
            options=["option1", "option2"],
            related_model=related_model.id,
            image=FileUpload(("image.png", f)),
        )
        example.save()

        # Verify the record was created
        assert example.id != ""

        # Test retrieval methods
        retrieved = Example.get_one(example.id)
        assert retrieved.text_field == "Test with image"
        assert retrieved.number_field == 123
        assert retrieved.is_active is True

        # Test list retrieval
        examples = Example.get_full_list()
        assert len(examples) > 0
        assert any(e.id == example.id for e in examples)

        # Test filtering
        filtered = Example.get_first_list_item(f"email_field = '{example.email_field}'")
        assert filtered.id

        # Test file contents
        image_bytes = example.get_file_contents("image")
        assert len(image_bytes) > 0

        # Cleanup
        Example.delete(example.id)


def test_related_model_crud(setup_models):
    """Test CRUD operations for RelatedModel."""
    # Create
    model = RelatedModel(name="CRUD Test Model")
    model.save()
    assert model.id != ""

    # Read
    retrieved = RelatedModel.get_one(model.id)
    assert retrieved.name == "CRUD Test Model"

    # Update
    model.name = "Updated Name"
    model.save()
    updated = RelatedModel.get_one(model.id)
    assert updated.name == "Updated Name"

    # Delete
    RelatedModel.delete(model.id)
    with pytest.raises(Exception):
        RelatedModel.get_one(model.id)


def test_example_validation(setup_models, related_model):
    """Test validation rules for Example model."""
    # Test invalid email
    with pytest.raises(ValueError):
        Example(
            text_field="Test",
            number_field=123,
            is_active=True,
            email_field="invalid-email",  # Invalid email format
            url_field="http://example.com",
            created_at=datetime.now(timezone.utc),
            options=["option1"],
            related_model=related_model.id,
        )

    # Test invalid URL
    with pytest.raises(ValueError):
        Example(
            text_field="Test",
            number_field=123,
            is_active=True,
            email_field="test@example.com",
            url_field="invalid-url",  # Invalid URL format
            created_at=datetime.now(timezone.utc),
            options=["option1"],
            related_model=related_model.id,
        )


def test_get_list_pagination(setup_models, related_model):
    """Test pagination functionality of get_list method."""
    # Create multiple example records
    examples = []
    for i in range(1, 15):  # Create 15 records to test pagination
        example = Example(
            text_field=f"Test {i}",
            number_field=i,
            is_active=True,
            email_field=f"test{i}@example.com",
            url_field="http://example.com",
            created_at=datetime.now(timezone.utc),
            options=["option1"],
            related_model=related_model.id,
        )
        example.save()
        examples.append(example)

    try:
        # Test first page (5 items)
        page1 = Example.get_list(page=1, per_page=5)
        assert len(page1) == 5

        # Test second page (5 items)
        page2 = Example.get_list(page=2, per_page=5)
        assert len(page2) == 5

        # Verify different records on different pages
        page1_ids = {item.id for item in page1}
        page2_ids = {item.id for item in page2}
        assert not page1_ids.intersection(page2_ids)  # No overlap between pages

        # Test with filter
        filtered = Example.get_list(page=1, per_page=3, filter="number_field >= 10")
        assert len(filtered) == 3
        assert all(item.number_field >= 10 for item in filtered)

    finally:
        # Cleanup
        for example in examples:
            try:
                Example.delete(example.id)
            except Exception:
                pass


def test_user_collection_operations(setup_models):
    """Test that User model prevents collection creation/modification."""

    # Test that attempting to create users collection raises error
    with pytest.raises(RuntimeError) as exc_info:
        User._create_collection()
    assert "system collection" in str(exc_info.value)

    # Test that attempting to update users collection raises error
    with pytest.raises(RuntimeError) as exc_info:
        # Create mock collection object with minimal required attributes
        mock_collection = type(
            "MockCollection", (), {"id": "mock_id", "name": "users", "schema": []}
        )
        User._update_collection(mock_collection)
    assert "system collection" in str(exc_info.value)

    # Test that we can still create and work with User instances
    user = User(
        email="test@example.com", password="securepassword123", name="Test User"
    )
    assert user.email == "test@example.com"
    assert user.name == "Test User"


def test_user_crud_operations(setup_models):
    """Test CRUD operations for User model."""
    test_users = []

    try:
        # Test creating a user
        user = User(
            email="test.user@example.com",
            password="securepassword123",
            passwordConfirm="securepassword123",
            name="Test User",
            emailVisibility=True,
        )
        user.save()
        assert user.id, "User should have an ID after saving"
        test_users.append(user)

        # Test get_one
        retrieved = User.get_one(user.id)
        assert retrieved.email == "test.user@example.com"
        assert retrieved.name == "Test User"
        assert retrieved.password is None  # Password should not be returned

        # Create more test users for list operations
        for i in range(1, 4):
            user = User(
                email=f"test.user{i}@example.com",
                password="securepassword123",
                passwordConfirm="securepassword123",
                name=f"Test User {i}",
            ).save()
            test_users.append(user)

        # Test get_list with pagination
        users_page = User.get_list(page=1, per_page=2)
        assert len(users_page) == 2, "Should return 2 users per page"

        # Test get_full_list
        all_users = User.get_full_list()
        assert len(all_users) >= len(test_users), "Should return all test users"

        # Test get_first_list_item with filter
        first_user = User.get_first_list_item('email = "test.user1@example.com"')
        assert first_user.email == "test.user1@example.com"

        # Test updating a user
        user = test_users[0]
        user.name = "Updated Name"
        user.save()

        updated = User.get_one(user.id)
        assert updated.name == "Updated Name"

    finally:
        # Cleanup - delete test users
        for user in test_users:
            try:
                User.delete(user.id)
            except Exception as e:
                print(f"Error cleaning up test user {user.id}: {e}")
