from pocketbase_orm import PBModel, User, PBReference
import time


def _field_names(pb_client, collection_name):
    return {f.name for f in pb_client.collections.get_one(collection_name).fields}


class Addon(PBModel, collection="addons"):
    name: str
    description: str
    user: PBReference[User]
    tags: list[str]
    price: float
    is_active: bool


class Addon1(PBModel, collection="test_addons"):
    name: str
    description: str
    user: PBReference[User]
    tags: list[str]
    price: float
    is_active: bool
    test: PBReference[Addon]
    test2: PBReference[Addon]


class Addon2(PBModel, collection="test_addons_2"):
    name: str
    description: str
    user: PBReference[User]
    tags: list[str]
    price: float
    is_active: bool
    test: PBReference[Addon1]
    test2: PBReference[Addon1]


def test_collections_resync(pb_client):
    PBModel.bind_client(pb_client)
    Addon.sync_collection()
    time.sleep(
        1
    )  # we need one second sleep as filenames from pocketbase have second timestamps
    Addon1.sync_collection()
    time.sleep(1)
    Addon2.sync_collection()
    time.sleep(1)
    # resync collections
    Addon2.sync_collection()
    time.sleep(1)
    Addon.sync_collection()
    time.sleep(1)
    Addon2.delete_collection()
    time.sleep(1)
    Addon2.sync_collection()
    time.sleep(1)

    # remove a field from the model
    class Addon2Removed(PBModel, collection="test_addons_2"):
        name: str
        description: str
        user: PBReference[User]
        tags: list[str]
        is_active: bool
        test2: PBReference[Addon1]

    # by default a sync keeps fields that are no longer on the model
    Addon2Removed.sync_collection()
    time.sleep(1)
    assert {"price", "test"} <= _field_names(pb_client, "test_addons_2")

    # removal is opt-in
    Addon2Removed.sync_collection(remove_missing_fields=True)
    time.sleep(1)
    Addon2Removed.sync_collection(remove_missing_fields=True)
    names = _field_names(pb_client, "test_addons_2")
    assert "price" not in names
    assert "test" not in names
    assert {"id", "name", "test2", "user"} <= names

    # we could add check here that looks at `pb_migrations` folder
