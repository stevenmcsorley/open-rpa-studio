from __future__ import annotations

import pytest

from openrpa import bridge, credentials


def test_bridge_stores_api_key_in_approved_vault_and_audits_only_reference(monkeypatch):
    replies=[]
    stored=[]
    audits=[]

    class Vault:
        def set_password(self,service,username,secret):
            stored.append((service,username,secret))

    monkeypatch.setattr(bridge,"send",replies.append)
    monkeypatch.setattr(bridge.history,"audit",lambda action,details:audits.append((action,details)))
    monkeypatch.setattr(credentials,"get_safe_keyring",lambda:Vault())
    bridge.handle({"id":1,"method":"credential.store","params":{"service":" openrpa-openai ","username":" production ","secret":"sk-test-sensitive"}})

    assert stored==[("openrpa-openai","production","sk-test-sensitive")]
    assert replies[-1]["result"]=={"stored":True,"service":"openrpa-openai","username":"production"}
    assert audits==[("credential.store",{"service":"openrpa-openai","username":"production","secretStored":True})]
    assert "sk-test-sensitive" not in str(replies+audits)


@pytest.mark.parametrize("params",[
    {"service":"s","username":"u","secret":""},
    {"service":"","username":"u","secret":"secret"},
    {"service":"s","username":"u","secret":"x"*8193},
])
def test_bridge_rejects_invalid_credential_before_vault_access(monkeypatch,params):
    replies=[]
    monkeypatch.setattr(bridge,"send",replies.append)
    monkeypatch.setattr(credentials,"get_safe_keyring",lambda:pytest.fail("must validate before vault access"))
    bridge.handle({"id":2,"method":"credential.store","params":params})
    assert "error" in replies[-1]


def test_bridge_propagates_missing_or_unsafe_os_vault_without_fallback(monkeypatch):
    replies=[]
    monkeypatch.setattr(bridge,"send",replies.append)
    monkeypatch.setattr(credentials,"get_safe_keyring",lambda:(_ for _ in ()).throw(RuntimeError("Refusing credential access through non-approved keyring backend")))
    bridge.handle({"id":3,"method":"credential.store","params":{"service":"s","username":"u","secret":"secret"}})
    assert "non-approved keyring backend" in replies[-1]["error"]["message"]


def test_bridge_does_not_return_keyring_storage_exception_details(monkeypatch):
    replies=[]

    class Vault:
        def set_password(self,*_args):
            raise RuntimeError("backend error included a secret-value sentinel")

    monkeypatch.setattr(bridge,"send",replies.append)
    monkeypatch.setattr(credentials,"get_safe_keyring",lambda:Vault())
    bridge.handle({"id":4,"method":"credential.store","params":{"service":"s","username":"u","secret":"secret-value"}})
    message=replies[-1]["error"]["message"]
    assert "secret-value" not in message
    assert "secret-value sentinel" not in message
    assert "RuntimeError" in message
