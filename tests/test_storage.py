import base64
import unittest
from unittest.mock import Mock
import requests
from core import fresh, changed
from storage import GitHubStore, ConflictError, StorageError, encode, hash_password, verify_password


def response(code, body=None):
    r = Mock(status_code=code)
    r.json.return_value = body or {}
    return r


class StoreTests(unittest.TestCase):
    def store(self, responses):
        session = Mock()
        session.request.side_effect = responses
        return GitHubStore("owner/repo","placeholder",session=session), session

    def test_two_readers_cannot_overwrite_each_other(self):
        state = fresh()
        body = {"content":base64.b64encode(encode(state)).decode(),"sha":"old"}
        store, session = self.store([response(200,{"private":True}),response(200,body),
                                    response(200,{"private":True}),response(200,body),
                                    response(200,{"content":{"sha":"new"}}),response(409)])
        first, sha1 = store.load()
        second, sha2 = store.load()
        self.assertEqual(store.save(changed(first,"A","Premier"),sha1),"new")
        with self.assertRaises(ConflictError):
            store.save(changed(second,"B","Second"),sha2)
        self.assertEqual(session.request.call_args.kwargs["json"]["sha"],"old")

    def test_new_file_requires_private_repo_existing_branch(self):
        store,_ = self.store([response(200,{"private":True}),response(404),response(200)])
        self.assertEqual(store.load(),(fresh(),None))
        for responses in ([response(200,{"private":False})],
                          [response(200,{"private":True}),response(404),response(404)],
                          [response(401)]):
            store,_ = self.store(responses)
            with self.assertRaises(StorageError): store.load()

    def test_corruption_and_network_error_do_not_reset(self):
        store,_ = self.store([response(200,{"private":True}),response(200,{"sha":"old","content":"e30="})])
        with self.assertRaises(StorageError): store.load()
        store,_ = self.store([requests.Timeout()])
        with self.assertRaises(StorageError): store.load()

    def test_first_save_conflict_does_not_retry_without_guard(self):
        store, session = self.store([response(422)])
        with self.assertRaises(ConflictError): store.save(fresh(),None)
        self.assertEqual(session.request.call_count,1)

    def test_password_hashes(self):
        digest = hash_password("Une longue phrase de test")
        self.assertTrue(verify_password("Une longue phrase de test",digest))
        self.assertFalse(verify_password("incorrect",digest))
        self.assertFalse(verify_password("incorrect","not configured"))
        with self.assertRaises(ValueError): hash_password("court")
