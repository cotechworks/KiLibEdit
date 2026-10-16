import tempfile
import unittest
from pathlib import Path
from library import Library, atomic_save

SAMPLE = '''(kicad_symbol_lib (version 20251024) (generator kicad_symbol_editor)
 (symbol "Base" (property "Reference" "U" (at 0 0 0) (effects (font (size 1 1))))
 (property "Value" "Base" (at 1 2 0) (effects (font (size 1 1))))
 (symbol "Base_0_1" (rectangle (start 0 0) (end 2 2))))
 (symbol "Child" (extends "Base") (property "Value" "Child" (at 0 0 0)))
)'''


class LibraryTests(unittest.TestCase):
    def test_lossless(self):
        lib = Library(SAMPLE)
        self.assertEqual(lib.render(), SAMPLE)
        self.assertEqual(lib.names, ['Base', 'Child'])
        self.assertEqual(lib.parents, ['', 'Base'])

    def test_edit_preserves_graphics_and_effects(self):
        lib = Library(SAMPLE)
        value = '日本語 "quoted" \\ path\nline\ttab'
        lib.set(0, 'Value', value)
        result = lib.render()
        self.assertEqual(Library(result).get(0, 'Value'), value)
        self.assertIn('(at 1 2 0) (effects (font (size 1 1)))', result)
        self.assertIn('(symbol "Base_0_1" (rectangle (start 0 0) (end 2 2)))', result)

    def test_add_and_revert(self):
        lib = Library(SAMPLE)
        lib.set(1, 'Manufacturer', 'CoTech')
        self.assertEqual(Library(lib.render()).get(1, 'Manufacturer'), 'CoTech')
        lib.set(1, 'Manufacturer', '')
        self.assertEqual(lib.render(), SAMPLE)

    def test_kicad10_private_property(self):
        source = '(kicad_symbol_lib (version 20251024) (symbol "A" (property private "Note" "secret" (at 0 0 0))))'
        lib = Library(source)
        self.assertEqual(lib.get(0, 'Note'), 'secret')
        lib.set(0, 'Note', 'updated')
        self.assertIn('(property private "Note" "updated"', lib.render())

    def test_malformed(self):
        for text in ['(', '()', '(other)', SAMPLE + ')', '(kicad_symbol_lib (symbol "abc))']:
            with self.assertRaises(ValueError):
                Library(text)

    def test_backup_and_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.kicad_sym'
            path.write_bytes(SAMPLE.encode())
            backup = atomic_save(path, SAMPLE + '\n', SAMPLE.encode())
            self.assertEqual(backup.read_bytes(), SAMPLE.encode())
            with self.assertRaises(ValueError):
                atomic_save(path, SAMPLE, SAMPLE.encode())
            self.assertEqual(path.read_text(), SAMPLE + '\n')


if __name__ == '__main__':
    unittest.main()
