"""Real bundled OPUS integration; skipped when the distributable model is absent."""
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from offline import OpusTranslator

MODEL = Path(__file__).resolve().parent / 'models' / 'opus'


@unittest.skipUnless((MODEL / 'model.bin').is_file(), 'Requires the bundled OPUS model')
class OfflinePortablePathTests(unittest.TestCase):
    def test_unicode_directory_loads_and_preserves_role_switching(self):
        with TemporaryDirectory(prefix='kiểm thử OPUS ', dir=Path(__file__).parent) as directory:
            target = Path(directory) / 'Người chơi' / 'mô hình'
            target.mkdir(parents=True)
            for name in ('config.json', 'model.bin', 'shared_vocabulary.json', 'source.spm', 'target.spm'):
                shutil.copyfile(MODEL / name, target / name)
            translator = OpusTranslator(target)
            try:
                source = 'I trust you. Please stay with me.'
                neutral = translator.translate(source, 'neutral')
                self.assertRegex(neutral.casefold(), r'\btôi\b')
                paired = translator.translate(source, 'nikke')
                self.assertRegex(paired.casefold(), r'\bem\b')
                self.assertRegex(paired.casefold(), r'\banh\b')
                self.assertEqual(translator.translate(source, 'neutral'), neutral)
            finally:
                translator.close()


if __name__ == '__main__':
    unittest.main()
