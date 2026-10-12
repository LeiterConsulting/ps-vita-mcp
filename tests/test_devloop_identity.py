"""Offline fingerprint regression: stale inputs, headers and ELF cannot be published."""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from devloop_identity import native_identity,native_inputs,verify_native_identity


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        for name in native_inputs(ROOT):
            target=self.root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
        self.build=self.root/'build';self.build.mkdir()
        self.identity,self.sources,self.manifest=native_identity(self.root)
        (self.build/'devloop-native-inputs.sha256').write_text(self.manifest,encoding='utf-8')
        (self.build/'devloop_build_identity.h').write_text(f'#define DEV_BUILD_ID "{self.identity}"\n',encoding='utf-8')
        (self.build/'vita_devloop').write_bytes(b'fixture ELF identity:'+self.identity.encode('ascii'))
    def tearDown(self):self.temp.cleanup()
    def test_exact_canonical_manifest_and_elf_accept(self):
        self.assertEqual(verify_native_identity(self.root,self.build),(self.identity,self.sources))
        self.assertIn('third_party/lua-5.4.9/src/lapi.c',self.sources)
        self.assertNotIn('third_party/lua-5.4.9/src/liolib.c',self.sources)
    def test_changed_native_source_rejects_stale_build(self):
        path=self.root/'devloop/core.c';path.write_bytes(path.read_bytes()+b'\n/* changed native input */\n')
        self.assertNotEqual(native_identity(self.root)[0],self.identity)
        with self.assertRaisesRegex(ValueError,'inputs differ'):verify_native_identity(self.root,self.build)
    def test_changed_generated_header_rejects(self):
        (self.build/'devloop_build_identity.h').write_text('#define DEV_BUILD_ID "'+('0'*64)+'"\n')
        with self.assertRaisesRegex(ValueError,'generated|Generated'):verify_native_identity(self.root,self.build)
    def test_missing_elf_fingerprint_rejects(self):
        (self.build/'vita_devloop').write_bytes(b'fixture lacks native identity')
        with self.assertRaisesRegex(ValueError,'ELF lacks'):verify_native_identity(self.root,self.build)
    def test_missing_manifest_entry_rejects(self):
        (self.build/'devloop-native-inputs.sha256').write_text(self.manifest.split('\n',1)[1])
        with self.assertRaisesRegex(ValueError,'inputs differ'):verify_native_identity(self.root,self.build)
    def test_new_nested_header_rejects_stale_build(self):
        path=self.root/'common/new/nested.h';path.parent.mkdir();path.write_bytes(b'#define NEW_NATIVE_VALUE 1\n')
        self.assertIn('common/new/nested.h',native_inputs(self.root))
        with self.assertRaisesRegex(ValueError,'inputs differ'):verify_native_identity(self.root,self.build)


if __name__=='__main__':unittest.main(verbosity=2)
