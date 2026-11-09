"""Credential scope/serialization and real Qt state tests with an in-memory OS boundary.

No test calls Windows Credential Manager, reads a user key file, performs OCR,
loads an OPUS model, or sends an HTTP request. Run with unittest alongside the
existing subtitle/capture/voice suites after dependencies have been installed.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import traceback
import unittest
from unittest.mock import patch

import credentials
from app import MainWindow
from backend import TranslationError
from test_subtitles import DualChannelTestCase as _ChannelCase


class _MemoryVault:
    """Model native allocations and account separation, not application behavior."""

    def __init__(self):
        self.account = 'account-a'
        self.records = {}
        self.last_error = 0
        self.allocations = {}
        self.freed = 0
        self.read_failure = None
        self.write_failure = None
        self.read_denied = False
        self.write_denied = False

    def CredWriteW(self, pointer, flags):
        if self.write_failure is not None:
            raise self.write_failure
        if self.write_denied:
            self.last_error = 5
            return False
        value = ctypes.cast(pointer, ctypes.POINTER(credentials._CREDENTIALW)).contents
        self.records[(self.account, value.TargetName)] = {
            'flags': flags,
            'type': value.Type,
            'persist': value.Persist,
            'username': value.UserName,
            'attributes': value.AttributeCount,
            'blob': ctypes.string_at(value.CredentialBlob, value.CredentialBlobSize),
        }
        return True

    def CredReadW(self, target, kind, flags, output):
        if self.read_failure is not None:
            raise self.read_failure
        if self.read_denied:
            self.last_error = 5
            return False
        record = self.records.get((self.account, target))
        if record is None:
            self.last_error = 1168
            return False
        blob = record['blob']
        buffer = (wintypes.BYTE * len(blob)).from_buffer_copy(blob)
        value = credentials._CREDENTIALW()
        value.Type = record['type']
        value.TargetName = target
        value.Persist = record['persist']
        value.CredentialBlobSize = len(blob)
        value.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(wintypes.BYTE))
        pointer = ctypes.pointer(value)
        self.allocations[ctypes.addressof(value)] = (pointer, buffer)
        ctypes.cast(output, ctypes.POINTER(ctypes.POINTER(credentials._CREDENTIALW)))[0] = pointer
        return True

    def CredFree(self, pointer):
        address = ctypes.addressof(ctypes.cast(pointer, ctypes.POINTER(credentials._CREDENTIALW)).contents)
        del self.allocations[address]
        self.freed += 1


def _install_fake_vault(case):
    vault = _MemoryVault()
    boundary = patch('credentials._credential_api', return_value=vault)
    boundary.start()
    case.addCleanup(boundary.stop)
    last_error = patch('credentials.ctypes.get_last_error', side_effect=lambda: vault.last_error, create=True)
    last_error.start()
    case.addCleanup(last_error.stop)
    return vault


class EndpointScopeTests(unittest.TestCase):
    def test_equivalent_spellings_have_one_canonical_endpoint(self):
        cases = {
            'HTTPS://API.OPENAI.COM:443/v1/': 'https://api.openai.com/v1',
            'https://api.openai.com': 'https://api.openai.com',
            'https://api.openai.com/': 'https://api.openai.com',
            'https://example.com/%76%31/': 'https://example.com/v1',
            'https://BÜCHER.example/v1': 'https://xn--bcher-kva.example/v1',
            'https://[2001:0DB8:0:0::1]:443/v1/': 'https://[2001:db8::1]/v1',
            'https://example.com:8443/custom/v2': 'https://example.com:8443/custom/v2',
            'https://example.com/V1': 'https://example.com/V1',
        }
        for original, expected in cases.items():
            with self.subTest(original=original):
                canonical = credentials.normalize_endpoint(original)
                self.assertEqual(canonical, expected)
                self.assertEqual(credentials.normalize_endpoint(canonical), canonical)

    def test_unsafe_or_ambiguous_endpoints_fail_without_echoing_input(self):
        invalid = (
            None, b'https://example.com/v1', '', ' https://example.com/v1',
            'https://example.com/v1 ', 'http://example.com/v1', 'https:///v1',
            'https://private-user:private-password@example.com/v1',
            'https://example.com/v1?private-key=example', 'https://example.com/v1?',
            'https://example.com/v1#private-fragment', 'https://example.com/v1#',
            'https://example.com:0/v1', 'https://example.com:65536/v1',
            'https://example.com:/v1', 'https://example.com:no/v1',
            'https://example.com\\@other.example/v1', 'https://example.com/v1\n',
            'https://bad_host.example/v1', 'https://example.com./v1',
            'https://[::1]unexpected/v1', 'https://[fe80::1%25zone]/v1',
            'https://example.com/a/../v1', 'https://example.com/a/%2e%2e/v1',
            'https://example.com/a//v1', 'https://example.com/a%2fv1',
            'https://example.com/a%5cv1', 'https://example.com/a%00v1',
            'https://example.com/v1%', 'https://example.com/v1%GG',
            'https://example.com/v1/<>',
        )
        for endpoint in invalid:
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(credentials.CredentialError) as caught:
                    credentials.normalize_endpoint(endpoint)
                self.assertNotIn('private-', str(caught.exception))
                self.assertNotIn('example.com', str(caught.exception))

    def test_namespaces_preserve_host_port_path_and_generic_secret_separation(self):
        endpoints = (
            'https://api.openai.com/v1', 'https://other.example/v1',
            'https://api.openai.com:8443/v1', 'https://api.openai.com/v2',
            'https://api.openai.com/V1', 'https://api.openai.com',
        )
        targets = {credentials._translation_target(endpoint) for endpoint in endpoints}
        self.assertEqual(len(targets), len(endpoints))
        self.assertEqual(
            credentials._translation_target('HTTPS://API.OPENAI.COM:443/v1/'),
            credentials._translation_target(endpoints[0]),
        )
        for target in targets:
            self.assertTrue(target.startswith('NIKKETranslator/v1/translation/'))
            self.assertEqual(len(target.rsplit('/', 1)[1]), 64)
            self.assertNotIn('openai', target)
            self.assertNotEqual(target, credentials._secret_target('ai33'))
        for name in ('', '../ai33', 'translation/hash', 'AI33', None):
            with self.subTest(name=name), self.assertRaises(credentials.CredentialError):
                credentials._secret_target(name)


class VaultStorageTests(unittest.TestCase):
    def setUp(self):
        self.vault = _install_fake_vault(self)

    def test_key_round_trip_is_exact_and_never_falls_back_to_other_endpoint(self):
        credentials.store_translation_key('HTTPS://API.OPENAI.COM:443/v1/', 'unit-openai-key')
        credentials.store_translation_key('https://other.example/v1', 'unit-other-key')
        credentials.store_secret('ai33', 'unit-narration-key')
        self.assertEqual(credentials.load_translation_key('https://api.openai.com/v1'), 'unit-openai-key')
        self.assertEqual(credentials.load_translation_key('https://other.example/v1'), 'unit-other-key')
        self.assertEqual(credentials.load_secret('ai33'), 'unit-narration-key')
        self.assertIsNone(credentials.load_translation_key('https://api.openai.com/v2'))
        self.assertIsNone(credentials.load_translation_key('https://api.openai.com:8443/v1'))
        self.assertIsNone(credentials.load_translation_key('https://new.example/v1'))
        self.assertIsNone(credentials.load_secret('missing'))
        self.assertEqual(self.vault.allocations, {})
        self.assertEqual(self.vault.freed, 3)

    def test_native_record_is_current_user_nonroaming_generic_and_not_machine_named(self):
        credentials.store_secret('ai33', 'unit-token-đ')
        record = next(iter(self.vault.records.values()))
        self.assertEqual(record['type'], 1)
        self.assertEqual(record['persist'], 2)  # LOCAL_MACHINE, not ENTERPRISE (3).
        self.assertEqual(record['flags'], 0)
        self.assertEqual(record['attributes'], 0)
        self.assertEqual(record['username'], 'NIKKETranslator')
        self.assertEqual(record['blob'], 'unit-token-đ'.encode('utf-16-le'))
        self.vault.account = 'account-b'
        self.assertIsNone(credentials.load_secret('ai33'))
        credentials.store_secret('ai33', 'second-account-unit-token')
        self.vault.account = 'account-a'
        self.assertEqual(credentials.load_secret('ai33'), 'unit-token-đ')

    def test_value_validation_precedes_any_native_write(self):
        for value in ('', 'space key', 'unit\x00key', '\ud800', 'x' * 1281, None):
            with self.subTest(length=len(value) if isinstance(value, str) else None):
                with self.assertRaises(credentials.CredentialError):
                    credentials.store_secret('ai33', value)
        self.assertEqual(self.vault.records, {})
        credentials.store_secret('ai33', 'x' * 1280)
        self.assertEqual(credentials.load_secret('ai33'), 'x' * 1280)

    def test_corrupt_native_blobs_are_rejected_and_native_allocations_freed(self):
        credentials.store_secret('ai33', 'unit-token')
        record = next(iter(self.vault.records.values()))
        for blob in (b'', b'x', b'\x00\xd8', 'unit\x00token'.encode('utf-16-le'), b'x' * 2562):
            with self.subTest(length=len(blob)):
                record['blob'] = blob
                with self.assertRaises(credentials.CredentialError):
                    credentials.load_secret('ai33')
                self.assertEqual(self.vault.allocations, {})
        self.assertEqual(self.vault.freed, 5)

    def test_access_errors_are_safe_and_not_misreported_as_missing(self):
        poison = 'unit-private-key /private-machine-path raw-native-error'
        for operation in ('read', 'write'):
            setattr(self.vault, operation + '_failure', RuntimeError(poison))
            try:
                with self.assertRaises(credentials.CredentialError) as caught:
                    if operation == 'read':
                        credentials.load_secret('ai33')
                    else:
                        credentials.store_secret('ai33', 'unit-write-token')
                rendered = ''.join(traceback.format_exception(caught.exception))
                self.assertNotIn(poison, rendered)
                self.assertNotIn('unit-write-token', rendered)
            finally:
                setattr(self.vault, operation + '_failure', None)
        self.vault.read_denied = True
        with self.assertRaises(credentials.CredentialError):
            credentials.load_secret('ai33')
        self.vault.write_denied = True
        with self.assertRaises(credentials.CredentialError):
            credentials.store_secret('ai33', 'unit-write-token')


class ChannelCredentialTests(_ChannelCase):
    def setUp(self):
        self.vault = _install_fake_vault(self)
        super().setUp()
        # The legacy suite blocks all vault reads. This suite replaces the OS
        # boundary instead, so actual public credential and Qt state code runs.
        self.vault_patch.stop()

    def test_startup_loads_each_exact_endpoint_and_does_not_serialize_keys(self):
        first_endpoint = 'https://api.openai.com/v1'
        second_endpoint = 'https://other.example/v1'
        credentials.store_translation_key(first_endpoint, 'unit-first-key')
        credentials.store_translation_key(second_endpoint, 'unit-second-key')
        self.settings.write_text(json.dumps({'channels': [
            {'endpoint': first_endpoint, 'key': 'ignored-legacy-secret'},
            {'endpoint': second_endpoint},
        ]}), encoding='utf-8')
        reopened = self.open_window()
        self.assertEqual([channel.key.text() for channel in reopened.channels], ['unit-first-key', 'unit-second-key'])
        reopened._save_settings()
        serialized = self.settings.read_text(encoding='utf-8')
        for private in ('unit-first-key', 'unit-second-key', 'ignored-legacy-secret', '"key"'):
            self.assertNotIn(private, serialized)
        self.assertTrue(all(not channel.enabled for channel in reopened.channels))

    def test_endpoint_edit_clears_before_lookup_and_pauses_only_its_channel(self):
        second_endpoint = 'https://other.example/v1'
        credentials.store_translation_key(second_endpoint, 'unit-other-key')
        self.channel.key.setText('unit-original-key')
        self.channel.enabled = True
        self.enable_offline(self.other, region=[0.1, 0.1, 0.6, 0.3])
        self.channel.endpoint.setText(second_endpoint)
        self.assertEqual(self.channel.key.text(), '')
        self.assertIsNone(self.channel._key_endpoint)
        self.assertFalse(self.channel.enabled)
        self.assertTrue(self.other.enabled)
        self.channel.endpoint.editingFinished.emit()
        self.assertEqual(self.channel.key.text(), 'unit-other-key')
        self.assertEqual(self.channel._key_endpoint, second_endpoint)
        self.channel.endpoint.setText('https://not-saved.example/v1')
        self.channel.endpoint.editingFinished.emit()
        self.assertEqual(self.channel.key.text(), '')
        with self.assertRaises(TranslationError):
            self.channel._config()

    def test_equivalent_endpoint_spelling_retains_key_but_different_path_port_or_host_does_not(self):
        self.channel.key.setText('unit-original-key')
        self.channel.endpoint.setText('HTTPS://API.OPENAI.COM:443/v1/')
        self.assertEqual(self.channel.key.text(), 'unit-original-key')
        config = self.channel._config()
        self.assertEqual(config.api.endpoint, 'https://api.openai.com/v1')
        for endpoint in ('https://api.openai.com/v2', 'https://api.openai.com:8443/v2', 'https://other.example/v2'):
            self.channel.endpoint.setText(endpoint)
            self.assertEqual(self.channel.key.text(), '')
            self.channel.key.setText('unit-new-scope-key')

    def test_invalid_endpoint_cannot_carry_old_or_retyped_key_into_a_valid_scope(self):
        self.channel.key.setText('unit-original-key')
        self.channel.endpoint.setText('http://other.example/v1')
        self.assertEqual(self.channel.key.text(), '')
        self.channel.key.setText('unit-invalid-scope-key')
        with self.assertRaises(TranslationError):
            self.channel._config()
        self.channel.endpoint.setText('https://other.example/v1')
        self.assertEqual(self.channel.key.text(), '')
        # Even a stale programmatic key assignment cannot bypass request setup.
        self.channel._set_key('unit-stale-key', 'https://api.openai.com/v1', 'unit status')
        with self.assertRaises(TranslationError):
            self.channel._config()

    def test_command_line_import_does_not_copy_key_into_a_different_channel_endpoint(self):
        self.settings.write_text(json.dumps({'channels': [
            {'endpoint': 'https://api.openai.com/v1'},
            {'endpoint': 'https://other.example/v1'},
        ]}), encoding='utf-8')
        key_file = self.settings.parent / 'unit-key.txt'
        key_file.write_text('sk-unit-first-channel-only', encoding='utf-8')
        window = MainWindow(key_file)
        self.windows.append(window)
        window.hotkeys.close()
        for channel in window.channels:
            channel.timer.stop()
            channel.panel_save_timer.stop()
        self.assertEqual(window.channels[0].key.text(), 'sk-unit-first-channel-only')
        self.assertEqual(window.channels[1].key.text(), '')
        self.assertEqual(self.vault.records, {})

    def test_explicit_import_is_memory_only_until_save_and_survives_reopen_after_save(self):
        key_file = self.settings.parent / 'unit-key.txt'
        key_file.write_text('sk-unit-only-test-value', encoding='utf-8')
        self.channel._load_key(key_file)
        self.assertEqual(self.channel.key.text(), 'sk-unit-only-test-value')
        self.assertIsNone(credentials.load_translation_key(self.channel.endpoint.text()))
        self.assertEqual(self.other.key.text(), '')
        self.channel.save_key_button.click()
        self.assertEqual(credentials.load_translation_key(self.channel.endpoint.text()), 'sk-unit-only-test-value')
        self.assertEqual(key_file.read_text(encoding='utf-8'), 'sk-unit-only-test-value')
        self.assertEqual(self.other.key.text(), '')
        reopened = self.open_window()
        self.assertEqual(reopened.channels[0].key.text(), 'sk-unit-only-test-value')
        self.assertNotIn('sk-unit-only-test-value', self.settings.read_text(encoding='utf-8'))

    def test_vault_errors_keep_key_in_memory_without_exposing_native_error(self):
        self.channel.key.setText('unit-memory-key')
        self.vault.write_failure = RuntimeError('unit-private-native-detail')
        self.channel.save_key_button.click()
        self.assertEqual(self.channel.key.text(), 'unit-memory-key')
        self.assertNotIn('unit-private-native-detail', self.channel.key_status.text())
        self.assertNotIn('unit-memory-key', self.channel.key_status.text())
        self.assertEqual(self.vault.records, {})
        self.channel.key.clear()
        self.vault.read_failure = RuntimeError('unit-private-native-detail')
        self.channel._restore_saved_key()
        self.assertEqual(self.channel.key.text(), '')
        self.assertNotIn('unit-private-native-detail', self.channel.key_status.text())


if __name__ == '__main__':
    unittest.main()
