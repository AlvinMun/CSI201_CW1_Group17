import json, tempfile, unittest, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))
from server import load_questions

class QuestionBankTests(unittest.TestCase):
    def setUp(self):
        self.sample = Path(__file__).parents[1] / 'questions.json'
    def test_valid_bank_loads(self):
        quizzes = load_questions(self.sample)
        self.assertEqual(len(quizzes), 2)
        self.assertTrue(all(len(q['questions']) >= 5 for q in quizzes))
    def test_wrong_schema_version_rejected(self):
        data=json.loads(self.sample.read_text(encoding='utf-8')); data['schema_version']=2
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',delete=False) as f:
            json.dump(data,f); name=f.name
        try:
            with self.assertRaises(ValueError): load_questions(name)
        finally: Path(name).unlink()
    def test_empty_file_rejected(self):
        with tempfile.NamedTemporaryFile('wb',delete=False) as f: name=f.name
        try:
            with self.assertRaises(ValueError): load_questions(name)
        finally: Path(name).unlink()

if __name__=='__main__': unittest.main()
