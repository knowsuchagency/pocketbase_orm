import os
import pytest
from datetime import datetime, timezone
from pocketbase import PocketBase
from pocketbase.client import FileUpload
from pocketbase_orm import PBModel, Example, RelatedModel


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
        filtered = Example.get_first_list_item(
            f"email_field = '{example.email_field}'"
        )
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
