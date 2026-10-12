import uuid
from typing import Union

from pocketbase_orm import PBModel, PBReference


def _fields(pb_client, collection_name):
    return {f.name: f for f in pb_client.collections.get_one(collection_name).fields}


def test_relation_syntaxes(pb_client):
    """PBReference[Model] and the older `Model | str` spellings both map to relations."""
    PBModel.bind_client(pb_client)
    suffix = uuid.uuid4().hex[:8]

    class Target(PBModel, collection=f"rel_target_{suffix}"):
        name: str

    class Source(PBModel, collection=f"rel_source_{suffix}"):
        new_style: PBReference[Target]
        pipe_style: Target | str
        union_style: Union[Target, str]

    try:
        Target.sync_collection()
        Source.sync_collection()
        target_id = pb_client.collections.get_one(Target.get_collection_name()).id

        fields = _fields(pb_client, Source.get_collection_name())
        for name in ("new_style", "pipe_style", "union_style"):
            assert fields[name].type == "relation"
            assert fields[name].collectionId == target_id

        target = Target(name="target")
        target.save()
        source = Source(
            new_style=target.id, pipe_style=target.id, union_style=target.id
        )
        source.save()
        fetched = Source.get_one(source.id)
        assert fetched.new_style == target.id
        assert fetched.pipe_style == target.id
        assert fetched.union_style == target.id
    finally:
        Source.delete_collection()
        Target.delete_collection()


def test_resync_keeps_records(pb_client):
    """Re-syncing (including dropping a field) keeps data in the remaining fields."""
    PBModel.bind_client(pb_client)
    collection_name = f"resync_{uuid.uuid4().hex[:8]}"

    class Before(PBModel, collection=collection_name):
        title: str
        count: int
        note: str

    class After(PBModel, collection=collection_name):
        title: str
        count: int
        extra: bool = False

    try:
        Before.sync_collection()
        record = Before(title="kept", count=3, note="dropped later")
        record.save()

        Before.sync_collection()
        After.sync_collection()
        fetched = After.get_one(record.id)
        assert (fetched.title, fetched.count) == ("kept", 3)
        assert "note" in _fields(pb_client, collection_name)

        After.sync_collection(remove_missing_fields=True)
        fetched = After.get_one(record.id)
        assert (fetched.title, fetched.count) == ("kept", 3)
        assert "note" not in _fields(pb_client, collection_name)
    finally:
        After.delete_collection()
