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
    assert ("external_id", "provider") in constraint_cols


def test_person_provider_uniqueness_is_partial_excluding_email():
    from src.storage.schema import person_identifiers

    idx = next(
        ix
        for ix in person_identifiers.indexes
        if ix.name == "uq_person_identifiers_person_provider"
    )
    assert idx.unique is True
    assert "email" in str(idx.dialect_options["postgresql"]["where"])


def test_people_has_access_level_column():
    from src.storage.schema import people

    col = people.c.access_level
    assert col is not None
    assert not col.nullable
