from src.storage.schema import person_identifiers, providers


def test_providers_table_columns():
    cols = set(providers.c.keys())
    assert cols == {
        "id",
        "label",
        "description",
        "active",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    }


def test_person_identifiers_columns():
    cols = set(person_identifiers.c.keys())
    assert cols == {
        "id",
        "person_id",
        "provider",
        "external_id",
        "handle",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    }


def test_person_identifiers_unique_constraints():
    constraint_cols = {
        tuple(sorted(c.name for c in uc.columns))
        for uc in person_identifiers.constraints
        if uc.__class__.__name__ == "UniqueConstraint"
    }
    assert ("person_id", "provider") in constraint_cols
    assert ("external_id", "provider") in constraint_cols


def test_people_has_access_level_column():
    from src.storage.schema import people

    col = people.c.access_level
    assert col is not None
    assert not col.nullable
