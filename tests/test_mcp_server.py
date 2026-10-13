from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

from dex_fixture import make_dex

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from droidasc import mcp_server


class McpToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.apk = str(Path(cls.tmp.name) / 'app.apk')
        with zipfile.ZipFile(cls.apk, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('classes.dex', make_dex())
            archive.writestr('classes2.dex', make_dex())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_getclass_accepts_java_name(self):
        source = mcp_server.getclass(self.apk, 'example.Test')
        self.assertIn('class Test', source)

    def test_getclass_missing_class(self):
        with self.assertRaisesRegex(ValueError, 'not found'):
            mcp_server.getclass(self.apk, 'example.Missing')

    def test_listclass_prefix_and_limit(self):
        self.assertEqual(mcp_server.listclass(self.apk, 'example'), 'Lexample/Test;\nLexample/Test;')
        self.assertEqual(mcp_server.listclass(self.apk, 'nomatch'), '(no matches)')
        truncated = mcp_server.listclass(self.apk, limit=1)
        self.assertTrue(truncated.startswith('Lexample/Test;\n... truncated: showing 1 of 2 lines'))

    def test_findrefs_string(self):
        result = mcp_server.findrefs(self.apk, 'string', 'token')
        self.assertIn('token', result)
        self.assertNotEqual(result, '(no matches)')

    def test_findrefs_bad_arguments(self):
        with self.assertRaises(ValueError):
            mcp_server.findrefs(self.apk, 'string')
        with self.assertRaises(ValueError):
            mcp_server.findrefs(self.apk, 'method')
        with self.assertRaises(ValueError):
            mcp_server.findrefs(self.apk, 'bogus', 'x')


if __name__ == '__main__':
    unittest.main()
