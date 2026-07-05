from platform_auth.models import AuthedKey, ADMIN_SCOPE


def test_has_scope_direct_and_admin_wildcard():
    k = AuthedKey(name="bot", scopes=frozenset({"people:read"}))
    assert k.has_scope("people:read") is True
    assert k.has_scope("people:write") is False

    admin = AuthedKey(name="root", scopes=frozenset({ADMIN_SCOPE}))
    assert admin.has_scope("anything:at:all") is True
